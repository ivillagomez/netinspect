import re
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict

from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

from backend.config import FortiGateConfig

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=4)


class FortiGateSSH:
    def __init__(self, config: FortiGateConfig):
        self.config = config
        self._conn = None

    @property
    def available(self) -> bool:
        return bool(self.config.ssh_username and self.config.ssh_password)

    def _connect(self):
        self._conn = ConnectHandler(
            device_type="fortinet",
            host=self.config.host,
            username=self.config.ssh_username,
            password=self.config.ssh_password,
            port=self.config.ssh_port,
            timeout=15,
            session_timeout=15,
        )

    def _disconnect(self):
        if self._conn:
            try:
                self._conn.disconnect()
            except Exception:
                pass
            self._conn = None

    def _cmd(self, command: str) -> str:
        return self._conn.send_command(command, read_timeout=15)

    async def _run(self, fn, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, fn, *args)

    async def gather(self, interface: str = "") -> Dict:
        """Connect once, get platform info + interface stats. Returns {} if SSH not configured."""
        if not self.available:
            return {}

        result = {}

        def _work():
            try:
                self._connect()
                result.update(self._get_platform_info())
                if interface:
                    stats = self._get_interface_stats(interface)
                    if stats:
                        result["interface_stats"] = stats
            except (NetmikoTimeoutException, NetmikoAuthenticationException) as e:
                logger.warning(f"FortiGate SSH auth/timeout: {e}")
            except Exception as e:
                logger.warning(f"FortiGate SSH error: {e}")
            finally:
                self._disconnect()
            return result

        return await self._run(_work)

    # ------------------------------------------------------------------

    def _get_platform_info(self) -> Dict:
        try:
            out = self._cmd("get system status")
            info = {}
            # "Version: FortiGate-60F v7.4.3,build2573,240202"
            m = re.search(r"Version:\s*(FortiGate[\w-]*)\s+v([\d.]+)", out, re.IGNORECASE)
            if m:
                info["model"]   = m.group(1)
                info["version"] = "v" + m.group(2)
            m = re.search(r"Serial-Number:\s*(\S+)", out)
            if m:
                info["serial"] = m.group(1)
            m = re.search(r"Hostname:\s*(\S+)", out)
            if m:
                info["hostname"] = m.group(1)
            return info
        except Exception as e:
            logger.debug(f"FortiGate SSH platform_info error: {e}")
            return {}

    def _resolve_effective_interface(self, interface: str, iface_output: str) -> str:
        """
        If the interface is a LAG member (master=<non-zero>), return the name of the
        parent aggregate interface so callers can query stats from it instead.
        Uses the full 'diagnose netlink interface list' output to look up by index.
        Returns the original interface name if it is not a LAG member.
        """
        m = re.search(r'\bmaster=(\d+)\b', iface_output)
        if not m or m.group(1) == '0':
            return interface   # standalone interface — no LAG

        parent_idx = m.group(1)
        logger.info("[FG SSH] %s is a LAG member (master index %s) — locating parent", interface, parent_idx)
        try:
            all_out = self._cmd("diagnose netlink interface list")
            # Each block has fields on one line: name=agg1 family=0 type=778 index=5 mtu=... master=0
            for line in all_out.splitlines():
                if f"index={parent_idx}" in line and "master=0" in line:
                    nm = re.search(r'name=(\S+)', line)
                    if nm:
                        parent = nm.group(1)
                        logger.info("[FG SSH] LAG parent for %s → %s", interface, parent)
                        return parent
        except Exception as e:
            logger.debug("[FG SSH] LAG parent lookup failed: %s", e)

        return interface   # couldn't resolve parent — fall back to original

    def _get_interface_stats(self, interface: str) -> Dict:
        """
        diagnose netlink interface list <iface>
        Returns RX/TX packet+byte+error+drop counters and MTU.

        FortiOS uses abbreviated field names (rxpkt/txpkt/rxbyt/txbyt/rxerr/txerr/rxdrp/txdrp)
        but some versions use the full form (rxpackets etc.).  Parse each field individually.

        If the interface is a LAG member port, transparently queries the parent aggregate
        interface so the counters represent real traffic (member ports carry no useful stats).
        """
        if not re.match(r'^[\w\-./]+$', interface):
            logger.warning("Skipping interface stats: invalid interface name")
            return {}
        try:
            out = self._cmd(f"diagnose netlink interface list {interface}")
            logger.debug("[FG SSH] interface list output for %s:\n%s", interface, out[:600])

            # If this port is a LAG member, switch to the parent aggregate for real stats
            effective = self._resolve_effective_interface(interface, out)
            lag_parent = None
            if effective != interface:
                lag_parent = effective
                out = self._cmd(f"diagnose netlink interface list {effective}")
                logger.debug("[FG SSH] LAG parent %s output:\n%s", effective, out[:600])

            def _pstat(key_re: str) -> int:
                m = re.search(key_re + r'=(\d+)', out, re.IGNORECASE)
                return int(m.group(1)) if m else 0

            stats = {
                # FortiOS 7.x abbreviated:  rxpkt / txpkt
                # Older / full form:        rxpackets / txpackets
                "rx_packets": _pstat(r"rxpkt(?:s|ets?)?"),
                "tx_packets": _pstat(r"txpkt(?:s|ets?)?"),
                "rx_bytes":   _pstat(r"rxbyt(?:es?)?"),
                "tx_bytes":   _pstat(r"txbyt(?:es?)?"),
                "rx_errors":  _pstat(r"rxerr(?:ors?)?"),
                "tx_errors":  _pstat(r"txerr(?:ors?)?"),
                "rx_drops":   _pstat(r"rxdrp(?:s)?|rxdrop(?:s)?"),
                "tx_drops":   _pstat(r"txdrp(?:s)?|txdrop(?:s)?"),
            }

            m = re.search(r"mtu=(\d+)", out, re.IGNORECASE)
            if m:
                stats["mtu"] = int(m.group(1))

            if lag_parent:
                stats["lag_parent"] = lag_parent   # UI can annotate the section header

            # Return empty dict only if nothing was parsed (SSH ran but output was unrecognised)
            if all(v == 0 for k, v in stats.items() if k not in ("mtu", "lag_parent")):
                logger.debug("[FG SSH] interface stats: no counters parsed from output")
                return {}
            return stats
        except Exception as e:
            logger.debug(f"FortiGate SSH interface_stats error: {e}")
            return {}
