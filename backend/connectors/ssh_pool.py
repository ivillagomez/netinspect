"""
Thread-safe SSH connection pool for Netmiko.

Keeps idle connections alive between trace calls so each trace does not pay
the full SSH handshake cost (~1-2 s per switch on typical IOS/ArubaOS devices).

Design notes:
  • Connections are keyed by (host, username, device_type).
  • At most MAX_PER_KEY connections are pooled per key.
  • acquire() runs inside a ThreadPoolExecutor thread — NO asyncio primitives.
  • Stale connections (Paramiko transport gone) are detected and replaced.
  • Connections idle for > IDLE_TIMEOUT seconds are closed by cleanup_idle().
  • close_all() is called on FastAPI shutdown to release all SSH sessions cleanly.
"""

import threading
import logging
import time
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Optional

from netmiko import ConnectHandler

logger = logging.getLogger(__name__)

MAX_PER_KEY     = 2      # max pooled connections per (host, user, driver) key
IDLE_TIMEOUT    = 300    # seconds — close connections idle longer than this
WAIT_TIMEOUT    = 30     # seconds — max wait before creating an over-limit connection
WAIT_POLL       = 0.25   # seconds — polling interval while waiting for a free slot
STUCK_TIMEOUT   = 300    # seconds — L4: forcibly reclaim in_use conns held this long


@dataclass
class _PoolEntry:
    conn:          Any
    key:           Tuple
    in_use:        bool  = False
    last_released: float = field(default_factory=time.monotonic)
    last_acquired: float = field(default_factory=time.monotonic)  # L4: leak detection


class SshConnectionPool:
    """Singleton SSH connection pool.  Use the module-level ``_pool`` instance."""

    def __init__(self) -> None:
        self._lock:  threading.Lock                     = threading.Lock()
        self._pools: Dict[Tuple, List[_PoolEntry]]     = defaultdict(list)

    # ── Public API ─────────────────────────────────────────────────────────────

    def acquire(self, config: Any) -> Any:
        """Return a live ConnectHandler for this switch config.

        Tries (in order):
          1. Idle pooled connection that is still alive.
          2. New connection if under MAX_PER_KEY cap.
          3. Wait up to WAIT_TIMEOUT s for a slot to free up.
          4. Create an over-limit temporary connection (not retained in pool).
        """
        key      = _make_key(config)
        deadline = time.monotonic() + WAIT_TIMEOUT

        while True:
            with self._lock:
                pool = self._pools[key]

                # 1. Reuse a live idle connection
                for entry in pool:
                    if not entry.in_use:
                        if _is_alive(entry.conn):
                            entry.in_use       = True
                            entry.last_acquired = time.monotonic()  # L4
                            logger.debug("[pool] reused conn → %s", key[0])
                            return entry.conn
                        else:
                            # Dead connection — close and remove it
                            _safe_disconnect(entry.conn)
                            pool.remove(entry)
                            logger.debug("[pool] removed dead conn → %s", key[0])
                            break

                # 2. Open a new connection if under cap
                if len(pool) < MAX_PER_KEY:
                    conn  = _open(config)
                    entry = _PoolEntry(conn=conn, key=key, in_use=True,
                                       last_acquired=time.monotonic())  # L4
                    pool.append(entry)
                    logger.debug("[pool] new conn → %s (size=%d)", key[0], len(pool))
                    return conn

                # 3. Check deadline — create over-limit if expired
                if time.monotonic() >= deadline:
                    logger.warning("[pool] cap=%d hit for %s — over-limit conn", MAX_PER_KEY, key[0])
                    conn  = _open(config)
                    entry = _PoolEntry(conn=conn, key=key, in_use=True,
                                       last_acquired=time.monotonic())  # L4
                    pool.append(entry)   # tracked so release() can find it
                    return conn

            # 4. Wait and retry
            time.sleep(WAIT_POLL)

    def release(self, config: Any, conn: Any) -> None:
        """Return a connection to the pool (marks it idle).
        Over-limit entries are disconnected and removed instead.
        """
        key = _make_key(config)
        with self._lock:
            pool = self._pools[key]
            # Find the entry
            for entry in pool:
                if entry.conn is conn:
                    if len(pool) > MAX_PER_KEY:
                        # We're over-limit — discard rather than keep
                        _safe_disconnect(conn)
                        pool.remove(entry)
                        logger.debug("[pool] discarded over-limit conn → %s", key[0])
                    else:
                        entry.in_use       = False
                        entry.last_released = time.monotonic()
                        logger.debug("[pool] released conn → %s", key[0])
                    return
            # Entry not found (shouldn't happen) — just disconnect
            _safe_disconnect(conn)

    def cleanup_idle(self) -> None:
        """Close connections idle for > IDLE_TIMEOUT seconds.
        Also forcibly reclaims connections that have been in_use for longer
        than STUCK_TIMEOUT — these are leaked connections whose callers crashed
        without calling release().
        Should be called periodically (e.g. from a background task).
        """
        now = time.monotonic()
        idle_cutoff  = now - IDLE_TIMEOUT
        stuck_cutoff = now - STUCK_TIMEOUT   # L4
        with self._lock:
            for key, pool in list(self._pools.items()):
                # Close genuinely idle connections
                to_close = [e for e in pool if not e.in_use and e.last_released < idle_cutoff]
                for entry in to_close:
                    _safe_disconnect(entry.conn)
                    pool.remove(entry)
                    logger.info("[pool] closed idle conn → %s", key[0])
                # L4: forcibly reclaim connections stuck in_use beyond STUCK_TIMEOUT
                stuck = [e for e in pool if e.in_use and e.last_acquired < stuck_cutoff]
                for entry in stuck:
                    logger.warning(
                        "[pool] forcibly closing stuck in-use conn → %s "
                        "(held %.0fs, limit %ds)",
                        key[0], now - entry.last_acquired, STUCK_TIMEOUT,
                    )
                    _safe_disconnect(entry.conn)
                    pool.remove(entry)

    def close_all(self) -> None:
        """Forcibly disconnect all pooled connections.  Called on app shutdown."""
        with self._lock:
            for pool in self._pools.values():
                for entry in pool:
                    _safe_disconnect(entry.conn)
            self._pools.clear()
        logger.info("[pool] all SSH connections closed")

    # ── Diagnostics ────────────────────────────────────────────────────────────

    def stats(self) -> Dict:
        with self._lock:
            return {
                host: {
                    "total":   len(pool),
                    "in_use":  sum(1 for e in pool if e.in_use),
                    "idle":    sum(1 for e in pool if not e.in_use),
                }
                for (host, *_), pool in self._pools.items()
            }


# ── Module-level helpers ──────────────────────────────────────────────────────

def _make_key(config: Any) -> Tuple:
    return (
        config.host,
        config.username or "",
        getattr(config, "device_type", getattr(config, "os_type", "cisco_ios")),
    )


def _is_alive(conn: Any) -> bool:
    """Check whether the underlying Paramiko transport is still active."""
    try:
        transport = conn.remote_conn.get_transport()
        return transport is not None and transport.is_active()
    except Exception:
        return False


def _safe_disconnect(conn: Any) -> None:
    try:
        conn.disconnect()
    except Exception:
        pass


def _open(config: Any) -> Any:
    """Create a new Netmiko ConnectHandler — called inside executor thread."""
    return ConnectHandler(
        device_type=getattr(config, "device_type", getattr(config, "os_type", "cisco_ios")),
        host=config.host,
        username=config.username or "",
        password=config.password or "",
        timeout=config.timeout,
        session_timeout=config.timeout,
        global_delay_factor=1,
    )


# ── Singleton ─────────────────────────────────────────────────────────────────
_pool = SshConnectionPool()
