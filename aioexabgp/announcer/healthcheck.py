#!/usr/bin/env python3

import asyncio
import logging
from ipaddress import ip_address
from platform import system
from typing import Dict, Sequence


LOG = logging.getLogger(__name__)


class HealthChecker:
    """ Base class for defining base Health Check API """

    TIMEOUT_DEFAULT = 5

    def __init__(self, config: Dict) -> None:
        self.config = config
        self.timeout = config.get("timeout", self.TIMEOUT_DEFAULT)

    async def check(self) -> bool:
        raise NotImplementedError("Implement in subclass")

    async def run_cmd(self, cmd: Sequence[str]) -> bool:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), self.timeout)
        except asyncio.TimeoutError:
            LOG.error(f"{' '.join(cmd)} asyncio timed out")
            return False

        if process.returncode != 0:
            LOG.error(
                f"{' '.join(cmd)} returned {process.returncode}:\n"
                + f"STDERR: {stderr.decode('utf-8')}\nSTDOUT: {stdout.decode('utf-8')}"
            )
            return False

        return True


class PingChecker(HealthChecker):
    """ Send ICMP/ICMPv6 Pings to check reachability
        - Only support IP addresses for now
        - Subprocess so this script + exabgp don't need setuid

        Config Supported:
        - "ping_count": Default 2
        - "ping_timeout": Default 5 (seconds) """

    def __init__(self, config: Dict) -> None:
        self.target_ip = ip_address(config["ping_target"])
        self.count = config.get("ping_count", 2)
        self.timeout = config.get("ping_timeout", self.TIMEOUT_DEFAULT)
        self.wait = config.get("ping_wait", int(self.timeout) - 1)

    def __str__(self):
        return f"PingChecker - Target: {self.target_ip} Count: {self.count} Timeout: {self.timeout}"

    async def do_ping(self) -> bool:
        cmd = ["ping6"] if self.target_ip.version == 6 else ["ping"]
        if system() != "Darwin":
            cmd.extend(["-w", str(self.wait)])
        cmd.extend(["-c", str(self.count), self.target_ip.compressed])
        return await self.run_cmd(cmd)

    async def check(self) -> bool:
        try:
            if await self.do_ping():
                return True
        except Exception:
            LOG.exception(
                f"Uncaught exception from ping of {self.target_ip.compressed}"
            )

        return False


def get_health_checker(class_name: str, kwargs: Dict) -> HealthChecker:
    if class_name == "PingChecker":
        return PingChecker(**kwargs)

    return HealthChecker(**kwargs)
