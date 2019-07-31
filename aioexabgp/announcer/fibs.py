#!/usr/bin/env python3

import asyncio
import logging
from enum import Enum
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_network
from platform import system
from typing import Awaitable, Dict, List, NamedTuple, Optional, Sequence, Union

from aioexabgp.utils import run_cmd


IPAddress = Union[IPv4Address, IPv6Address]
IPNetwork = Union[IPv4Network, IPv6Network]
LOG = logging.getLogger(__name__)


class FibOperation(Enum):
    NOTHING = 0
    ADD_ROUTE = 1
    REMOVE_ROUTE = 2
    REMOVE_ALL_ROUTES = 3


class FibPrefix(NamedTuple):
    """ Immutable object to place on FIB Queue - Then perform operation """

    prefix: IPNetwork
    next_hop: Optional[IPAddress]
    operation: FibOperation


class Fib:
    """ Base class for all FIB implementations

        Subclass to implement:
        - add_route(prefix, next_hop)
        - check_prefix_limit()
        - del_route(prefix)
    """

    DEFAULT_v4_route = ip_network("0.0.0.0/0")
    DEFAULT_v6_route = ip_network("::/0")
    DEFAULTS = (DEFAULT_v4_route, DEFAULT_v6_route)
    FIB_NAME = "Default"

    def __init__(self, config: Dict, timeout: float = 2.0) -> None:
        self.default_allowed = config["learn"].get("allow_default", True)
        self.prefix_limit = config["learn"].get("prefix_limit", 0)
        self.timeout = timeout

    def check_prefix_limit(self) -> int:
        if not self.prefix_limit:
            LOG.debug(f"{self.FIB_NAME} has no prefix limit")
            return 0

        raise NotImplementedError(
            f"{self.FIB_NAME} configuration has a prefix limit set ({self.prefix_limit}) "
            + f"set and has no `check_prefix_limit` method"
        )

    def is_default(self, prefix: IPNetwork) -> bool:
        return prefix in self.DEFAULTS

    ## To be implemented in child classes + make mypy happy
    async def add_route(self, prefix: IPNetwork, next_hop: IPAddress) -> bool:
        raise NotImplementedError("Please implement in sub class")

    async def check_for_route(self, prefix: IPNetwork, next_hop: IPAddress) -> bool:
        raise NotImplementedError("Please implement in sub class")

    async def del_all_routes(self, next_hop: IPNetwork) -> bool:
        raise NotImplementedError("Please implement in sub class")

    async def del_route(self, prefix: IPNetwork) -> bool:
        raise NotImplementedError("Please implement in sub class")


class LinuxFib(Fib):
    """ Adding and taking routes out of the Linux (or Mac OS X) Routing Table """

    IP_CMD = "/usr/local/bin/ip" if system() == "Darwin" else "/sbin/ip"
    FIB_NAME = "Linux FIB"

    async def add_route(self, prefix: IPNetwork, next_hop: IPAddress) -> bool:
        LOG.info(f"[{self.FIB_NAME}] Adding route to {str(prefix)} via {str(next_hop)}")

        if not self.default_allowed:
            is_default = self.is_default(prefix)
            if is_default:
                LOG.info(f"Not adding IPv{prefix.version} default route due to config")
                return False

        return await run_cmd(
            (
                self.IP_CMD,
                f"-{prefix.version}",
                "route",
                "add",
                str(prefix) if is_default else "default",
                "via",
                str(next_hop),
            ),
            self.timeout,
        )

    async def del_all_routes(self, next_hop: IPNetwork) -> bool:
        LOG.error(f"[{self.FIB_NAME}] does not have del_all_routes implemented")
        # TODO: Implement removal of all routes for next_hop
        # return await run_cmd()
        return False

    async def del_route(self, prefix: IPNetwork) -> bool:
        LOG.info(f"[{self.FIB_NAME}] Deleting route to {str(prefix)}")
        return await run_cmd(
            (self.IP_CMD, f"-{prefix.version}", "route", "del", str(prefix)),
            self.timeout,
        )


def get_fib(fib_name: str, config: Dict) -> Fib:
    if fib_name == "Linux":
        return LinuxFib(config)

    raise ValueError(f"{fib_name} is not a valid option")


async def prefix_consumer(  # noqa: C901
    prefix_queue: asyncio.Queue,
    fib_names: Sequence[str],
    config: Dict,
    *,
    dry_run: bool = False,
) -> None:
    """ Watch the queue for FibPrefix and apply the FibOperation to all FIBs """
    fibs = {f: get_fib(f, config) for f in fib_names}
    LOG.debug(f"prefix_consumer got {len(fibs)} FIBS")

    while True:
        LOG.debug(f"[prefix_consumer] Waiting for FIB prefix to consume")
        try:
            fib_operations = await prefix_queue.get()
            LOG.info(
                f"[prefix_consumer] Prefix Queue has {prefix_queue.qsize()} tasks queued"
            )

            route_tasks: List[Awaitable] = []
            for fib_operation in fib_operations:
                for fib_name, fib in fibs.items():
                    if fib_operation.operation == FibOperation.ADD_ROUTE:
                        LOG.debug(
                            f"[prefix_consumer] Adding {fib_operation.prefix} route via {fib_operation.next_hop} to {fib_name}"
                        )
                        route_tasks.append(
                            fib.add_route(fib_operation.prefix, fib_operation.next_hop)
                        )
                    elif fib_operation.operation == FibOperation.REMOVE_ROUTE:
                        LOG.debug(
                            f"[prefix_consumer] Removing {fib_operation.prefix} route via {fib_operation.next_hop} from {fib_name}"
                        )
                        route_tasks.append(fib.del_route(fib_operation.next_hop))
                    elif fib_operation.operation == FibOperation.REMOVE_ALL_ROUTES:
                        LOG.debug(
                            f"[prefix_consumer] Removing ALL routes via {fib_operation.next_hop} from {fib_name}"
                        )
                        route_tasks.append(fib.del_route(fib_operation.next_hop))
                    else:
                        LOG.error(
                            f"[prefix_consumer] {fib_operation.operation} operation is unhandled"
                        )

                if not route_tasks:
                    LOG.error(f"[prefix_consumer] No route tasks generated for update")
                    continue

                log_msg = f"[prefix_consumer] Running all {len(route_tasks)} FIB operations for {fib_operation}"
                if dry_run:
                    LOG.info(f"[DRY RUN] {log_msg}")
                    del route_tasks
                    continue

                LOG.info(log_msg)
                update_success = await asyncio.gather(*route_tasks)
                if not all(update_success):
                    LOG.error(
                        f"[prefix_consumer] There was a FIB operation failure. Please investigate!"
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            LOG.exception(f"[prefix_consumer] Got a {type(e)} exception")
