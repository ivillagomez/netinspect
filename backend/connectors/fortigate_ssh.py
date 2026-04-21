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

    def _get_interface_stats(self, interface: str) -> Dict:
        """
        diagnose netlink interface list <iface>
        Returns RX/TX packet+byte+error+drop counters and MTU.
        """
        if not re.match(r'^[\w\-./]+$', interface):
            logger.warning("Skipping interface stats: invalid interface name")
            return {}
        try:
            out = self._cmd(f"diagnose netlink interface list {interface}")
            stats = {}
            # stat line: rxpackets=N txpackets=N rxbytes=N txbytes=N rxerrors=N txerrors=N rxdrops=N txdrops=N
            m = re.search(
                r"rxpackets=(\d+)\s+txpackets=(\d+)\s+rxbytes=(\d+)\s+txbytes=(\d+)"
                r"\s+rxerrors=(\d+)\s+txerrors=(\d+)\s+rxdrops=(\d+)\s+txdrops=(\d+)",
                out,
            )
            if m:
                stats = {
                    "rx_packets": int(m.group(1)),
                    "tx_packets": int(m.group(2)),
                    "rx_bytes":   int(m.group(3)),
                    "tx_bytes":   int(m.group(4)),
                    "rx_errors":  int(m.group(5)),
                    "tx_errors":  int(m.group(6)),
                    "rx_drops":   int(m.group(7)),
                    "tx_drops":   int(m.group(8)),
                }
            m = re.search(r"mtu=(\d+)", out)
            if m:
                stats["mtu"] = int(m.group(1))
            return stats
        except Exception as e:
            logger.debug(f"FortiGate SSH interface_stats error: {e}")
            return {}
