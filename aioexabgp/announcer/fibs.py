#!/usr/bin/env python3

import asyncio
import logging
import re
from enum import Enum
from ipaddress import (
    ip_address,
    ip_network,
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
)
from platform import system
from subprocess import CompletedProcess
from typing import (
    Awaitable,
    Dict,
    List,
    NamedTuple,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

from aioexabgp.utils import run_cmd


IPAddress = Union[IPv4Address, IPv6Address]
IPNetwork = Union[IPv4Network, IPv6Network]
LOG = logging.getLogger(__name__)


# Keep a list of learn routes to be able to re-add to FIBs
BGP_LEARNT_PREFIXES: Dict[IPNetwork, Set[IPAddress]] = {}


class FibOperation(Enum):
    NOTHING = 0
    ADD_ROUTE = 1
    REMOVE_ROUTE = 2
    REMOVE_ALL_ROUTES = 3


class FibPrefix(NamedTuple):
    """Immutable object to place on FIB Queue - Then perform operation"""

    prefix: IPNetwork
    next_hop: Optional[IPAddress]
    operation: FibOperation


class Fib:
    """Base class for all FIB implementations

    Subclass to implement:
    - add_route(prefix, next_hop)
    - check_for_route()
    - check_prefix_limit()
    - del_route(prefix)
    """

    DEFAULT_v4_route = ip_network("0.0.0.0/0")
    DEFAULT_v6_route = ip_network("::/0")
    DEFAULTS = (DEFAULT_v4_route, DEFAULT_v6_route)
    FIB_NAME = "Default"
    IPV4_LL_PREFIX = ip_network("169.254.0.0/16")
    IPV6_LL_PREFIX = ip_network("fe80::/10")
    LINKLOCALS = {4: IPV4_LL_PREFIX, 6: IPV6_LL_PREFIX}

    def __init__(self, config: Dict, timeout: float = 2.0) -> None:
        self.default_allowed = config["learn"].get("allow_default", True)
        self.allow_ll_nexthop = config["learn"].get("allow_ll_nexthop", False)
        self.prefix_limit = config["learn"].get("prefix_limit", 0)
        self.timeout = timeout
        self.use_sudo = config["learn"].get("use_sudo", True)

    def check_prefix_limit(self) -> int:
        if not self.prefix_limit:
            LOG.debug(f"{self.FIB_NAME} has no prefix limit")
            return 0

        raise NotImplementedError(
            f"{self.FIB_NAME} configuration has a prefix limit set"
            f" ({self.prefix_limit}) set and has no `check_prefix_limit` method"
        )

    def is_default(self, prefix: IPNetwork) -> bool:
        LOG.debug(f"Checking if {prefix} is a default")
        return prefix in self.DEFAULTS

    def is_link_local(self, prefix: Union[IPAddress, IPNetwork]) -> bool:
        LOG.debug(f"Checking if {prefix} is link local")
        if isinstance(prefix, (IPv4Address, IPv6Address)):
            return prefix in self.LINKLOCALS[prefix.version]
        return bool(self.LINKLOCALS[prefix.version].overlaps(prefix))

    ## To be implemented in child classes + make mypy happy
    async def add_route(self, prefix: IPNetwork, next_hop: IPAddress) -> bool:
        if not self.default_allowed and self.is_default(prefix):
            LOG.info(
                f"[{self.FIB_NAME}] Not adding IPv{prefix.version} "
                + "default route due to config"
            )
            return False

        if next_hop and not self.allow_ll_nexthop and self.is_link_local(next_hop):
            LOG.info(
                f"[{self.FIB_NAME}] Link Local next-hop addresses are disabled. "
                + f"Skipping {prefix} via {next_hop}"
            )
            return False

        return True

    async def check_for_route(self, prefix: IPNetwork, next_hop: IPAddress) -> bool:
        raise NotImplementedError("Please implement in sub class")

    async def del_all_routes(self, next_hop: Optional[IPAddress]) -> bool:
        raise NotImplementedError("Please implement in sub class")

    async def del_route(self, prefix: IPNetwork, next_hop: IPAddress) -> bool:
        raise NotImplementedError("Please implement in sub class")


class LinuxFib(Fib):
    """Adding and taking routes out of the Linux (or Mac OS X) Routing Table"""

    IP_CMD = "/usr/local/bin/ip" if system() == "Darwin" else "/sbin/ip"
    FIB_NAME = "Linux FIB"
    # Hack to identify routes we add
    METRIC = 31337
    SUDO_CMD = "/usr/sbin/sudo" if system() == "Darwin" else "/usr/bin/sudo"

    async def add_route(self, prefix: IPNetwork, next_hop: IPAddress) -> bool:
        if not await super().add_route(prefix, next_hop):
            return False

        LOG.info(f"[{self.FIB_NAME}] Adding route to {str(prefix)} via {str(next_hop)}")
        cp = await run_cmd(
            self.gen_route_command("add", prefix, next_hop), self.timeout
        )
        return cp.returncode == 0

    async def get_route_table(self, ip_version: int) -> CompletedProcess:
        return await run_cmd((self.IP_CMD, f"-{ip_version}", "route", "show"))

    async def check_for_route(self, prefix: IPNetwork, next_hop: IPAddress) -> bool:
        route_regex = (
            rf"{prefix.compressed} via.*{next_hop.compressed}.*metric {self.METRIC}.*"
        )
        route_table = await self.get_route_table(prefix.version)
        if re.search(route_regex, route_table.stdout):
            return True
        return False

    async def del_all_routes(self, next_hop: Optional[IPAddress]) -> bool:
        del_route_count = 0
        v4_route_table = await self.get_route_table(4)
        v6_route_table = await self.get_route_table(6)
        remove_regex = (
            rf"(.*) via.*{next_hop.compressed}.*metric {self.METRIC}.*"
            if next_hop
            else rf"(.*) via (.*) dev .*metric {self.METRIC}"
        )
        for route_table in v4_route_table, v6_route_table:
            for line in route_table.stdout.splitlines():
                if prefix_match := re.match(remove_regex, line):
                    prefix_network = ip_network(prefix_match.group(1))
                    del_next_hop = (
                        next_hop
                        if next_hop
                        else ip_address(prefix_match.group(2).replace("inet6 ", ""))
                    )
                    if not await self.del_route(prefix_network, del_next_hop):
                        LOG.error(
                            f"Failed to delete {prefix_network.compressed} in del_all_routes"
                        )
                    else:
                        del_route_count += 1
        LOG.info(f"del_all_routes deleted {del_route_count} routes")
        return bool(del_route_count)

    async def del_route(self, prefix: IPNetwork, next_hop: IPAddress) -> bool:
        LOG.info(f"[{self.FIB_NAME}] Deleting route to {str(prefix)}")
        cp = await run_cmd(
            self.gen_route_command("delete", prefix, next_hop),
            self.timeout,
        )
        return cp.returncode == 0

    def gen_route_command(
        self,
        op: str,
        prefix: IPNetwork,
        next_hop: IPAddress,
    ) -> List[str]:
        cmd = [self.SUDO_CMD] if self.use_sudo else []
        cmd.extend(
            [
                self.IP_CMD,
                f"-{prefix.version}",
                "route",
                op,
                "default" if self.is_default(prefix) else str(prefix),
                "via",
            ]
        )
        if prefix.version == 4 and next_hop.version == 6:
            cmd.append("inet6")
        cmd.append(str(next_hop))
        cmd.extend(["metric", str(self.METRIC)])
        return cmd


def _update_learnt_routes(  # noqa: C901
    fib_operations: Sequence[FibPrefix],
) -> Tuple[int, int]:
    """Take fib operations and keep BGP_LEARNT_PREFIXES in sync"""
    global BGP_LEARNT_PREFIXES
    add_count = 0
    del_count = 0

    LOG.debug(
        "[update_learnt_routes] Attempting to update BGP Learnt Prefixes dictionary"
    )
    for fib_op in fib_operations:
        if fib_op.operation == FibOperation.ADD_ROUTE:
            if fib_op.prefix not in BGP_LEARNT_PREFIXES:
                if fib_op.next_hop:
                    BGP_LEARNT_PREFIXES[fib_op.prefix] = {fib_op.next_hop}
                else:
                    BGP_LEARNT_PREFIXES[fib_op.prefix] = set()
            elif fib_op.next_hop:
                BGP_LEARNT_PREFIXES[fib_op.prefix].add(fib_op.next_hop)
            else:
                LOG.error(
                    "[update_learnt_routes] Got a learnt route with no nethop:"
                    f" {fib_op}"
                )
                continue
            add_count += 1
        elif fib_op.operation == FibOperation.REMOVE_ROUTE:
            if fib_op.prefix not in BGP_LEARNT_PREFIXES:
                LOG.error(
                    f"[update_learnt_routes] {fib_op.prefix} not foud in BGP Learnt "
                    + "Prefixes - Not deleted"
                )
                continue

            del_ops = 0
            if fib_op.next_hop in BGP_LEARNT_PREFIXES[fib_op.prefix]:
                BGP_LEARNT_PREFIXES[fib_op.prefix].remove(fib_op.next_hop)
                del_ops += 1

            if not BGP_LEARNT_PREFIXES[fib_op.prefix]:
                del BGP_LEARNT_PREFIXES[fib_op.prefix]
                del_ops += 1

            if del_ops:
                del_count += 1
            else:
                LOG.error(f"[update_learnt_routes] No deletion took place for {fib_op}")
        elif fib_op.operation == FibOperation.REMOVE_ALL_ROUTES:
            del_count = del_count + len(BGP_LEARNT_PREFIXES)
            # Had to make copy of keys and delete prefixes 1 by 1 for unittests to pass
            for key in list(BGP_LEARNT_PREFIXES.keys()):
                del BGP_LEARNT_PREFIXES[key]
            LOG.info(
                "[update_learnt_routes] Resettting BGP Learnt Prefixes due to "
                + "REMOVE_ALL_ROUTES being received"
            )
        else:
            LOG.error(f"[update_learnt_routes] Unknown operation: {fib_op} - Ignoring")

    LOG.info(f"[update_learnt_routes] Completed {add_count} adds / {del_count} removes")
    return (add_count, del_count)


def get_fib(fib_name: str, config: Dict) -> Fib:
    if fib_name == "Linux":
        return LinuxFib(config)

    raise ValueError(f"{fib_name} is not a valid option")


async def prefix_consumer(
    prefix_queue: asyncio.Queue,
    fib_names: Sequence[str],
    config: Dict,
    *,
    dry_run: bool = False,
) -> None:
    """Watch the queue for FibPrefix and apply the FibOperation to all FIBs"""
    fibs = {f: get_fib(f, config) for f in fib_names}
    LOG.debug(f"prefix_consumer got {len(fibs)} FIBS")

    while True:
        LOG.debug("[prefix_consumer] Waiting for FIB prefix to consume")
        try:
            fib_operations = await prefix_queue.get()
            LOG.info(
                f"[prefix_consumer] Prefix Queue has {prefix_queue.qsize()} tasks"
                " queued"
            )
            await fib_operation_runner(fibs, fib_operations, dry_run)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            LOG.exception(f"[prefix_consumer] Got a {type(e)} exception")


async def fib_operation_runner(
    fibs: Dict[str, Fib], fib_operations: Sequence[FibPrefix], dry_run: bool
) -> None:
    lprefix = "[fib_operation_runner] "
    for fib_operation in fib_operations:
        route_tasks: List[Awaitable] = []
        if not fib_operation.prefix:
            LOG.error(f"Invalid Fib Operation. Invalid data: {fib_operation}")
            continue

        for fib_name, fib in fibs.items():
            if fib_operation.operation == FibOperation.ADD_ROUTE:
                LOG.debug(
                    f"{lprefix}Adding {fib_operation.prefix} route "
                    + f"via {fib_operation.next_hop} to {fib_name}"
                )
                if not fib_operation.next_hop:
                    LOG.error(
                        f"{lprefix}Can't add {fib_operation.prefix} with no next-hop"
                    )
                    continue
                route_tasks.append(
                    fib.add_route(fib_operation.prefix, fib_operation.next_hop)
                )
            elif fib_operation.operation == FibOperation.REMOVE_ROUTE:
                if not fib_operation.next_hop:
                    LOG.error(
                        f"{lprefix}Can't remove {fib_operation.prefix} with no next-hop"
                    )
                    continue
                LOG.debug(
                    f"{lprefix}Removing {fib_operation.prefix} "
                    + f"route via {fib_operation.next_hop} from {fib_name}"
                )
                route_tasks.append(
                    fib.del_route(fib_operation.prefix, fib_operation.next_hop)
                )
            elif fib_operation.operation == FibOperation.REMOVE_ALL_ROUTES:
                LOG.debug(
                    f"{lprefix}Removing ALL routes via "
                    + f"{fib_operation.next_hop} from {fib_name}"
                )
                route_tasks.append(fib.del_all_routes(fib_operation.next_hop))
            else:
                LOG.error(f"{lprefix}{fib_operation.operation} operation is unhandled")

        if not route_tasks:
            LOG.error(f"{lprefix}No route tasks generated for update")
            continue

        log_msg = (
            f"{lprefix}Running {len(route_tasks)} "
            + f"FIB operations for {fib_operation}"
        )
        if dry_run:
            LOG.info(f"{lprefix}[DRY RUN] {log_msg}")
            continue

        LOG.info(log_msg)
        update_success = await asyncio.gather(*route_tasks)
        if not all(update_success):
            LOG.error(
                f"{lprefix}There was a FIB operation failure. Please investigate!"
            )
        else:
            _update_learnt_routes(fib_operations)
