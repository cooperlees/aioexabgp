#!/usr/bin/env python3

import logging
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from platform import system
from typing import Dict, List, Union

from aioexabgp.utils import run_cmd


IPNetwork = Union[IPv4Network, IPv6Network]
LOG = logging.getLogger(__name__)


class HealthChecker:
    """ Base class for defining base Health Check API """

    TIMEOUT_DEFAULT = 5

    def __init__(self, config: Dict) -> None:
        self.config = config
        self.timeout = config.get("timeout", self.TIMEOUT_DEFAULT)

    async def check(self) -> bool:
        raise NotImplementedError("Implement in subclass")


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
        return (
            f"PingChecker - Target: {self.target_ip} Count: {self.count}"
            + f" Timeout: {self.timeout}"
        )

    async def do_ping(self) -> bool:
        cmd = ["ping6"] if self.target_ip.version == 6 else ["ping"]
        if system() != "Darwin":
            cmd.extend(["-w", str(self.wait)])
        cmd.extend(["-c", str(self.count), self.target_ip.compressed])
        return await run_cmd(cmd, self.timeout)

    async def check(self) -> bool:
        try:
            if await self.do_ping():
                return True
        except Exception:
            LOG.exception(
                f"Uncaught exception from ping of {self.target_ip.compressed}"
            )

        return False


def gen_advertise_prefixes(config: Dict) -> Dict:
    advertise_prefixes: Dict[IPNetwork, List[HealthChecker]] = {}
    for prefix, checkers in config["advertise"]["prefixes"].items():
        try:
            network_prefix = ip_network(prefix)
        except ValueError:
            LOG.error(f"{prefix} ignored - Invalid IP Network")
            continue

        advertise_prefixes[network_prefix] = []

        if not checkers:
            continue

        for checker in checkers:
            advertise_prefixes[network_prefix].append(
                get_health_checker(checker["class"], checker["kwargs"])
            )

    return advertise_prefixes


def get_health_checker(checker_name: str, kwargs: Dict) -> HealthChecker:
    if checker_name == "PingChecker":
        return PingChecker(**kwargs)

    raise ValueError(f"{checker_name} is not a valid option")
