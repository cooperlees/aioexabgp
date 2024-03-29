#!/usr/bin/env python3
""" Read ExaBGP JSON from STDIN and push commands via STDOUT """

import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from ipaddress import (
    ip_address,
    ip_network,
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
)
from json import JSONDecodeError, loads
from sys import stdin
from time import time
from typing import Awaitable, Dict, List, Optional, Sequence, Set, TextIO, Union

from aioexabgp.exabgpparser import ExaBGPParser
from .fibs import FibOperation, FibPrefix, prefix_consumer
from .healthcheck import HealthChecker

IPNetwork = Union[IPv4Network, IPv6Network]
IPAddress = Union[IPv4Address, IPv6Address]
LOG = logging.getLogger(__name__)


class Announcer:
    def __init__(
        self,
        config: Dict,
        advertise_prefixes: Dict[IPNetwork, List[HealthChecker]],
        *,
        executor: Optional[Union[ProcessPoolExecutor, ThreadPoolExecutor]] = None,
        print_timeout: float = 5.0,
        dry_run: bool = False,
    ) -> None:
        self.advertise_prefixes = advertise_prefixes
        self.config = config
        self.dry_run = dry_run
        self.learn_fibs = config["learn"].get("fibs", [])
        self.learn_queue: asyncio.Queue = asyncio.Queue()
        self.loop = asyncio.get_event_loop()
        self.next_hop = self.validate_next_hop(
            config["advertise"].get("next_hop", "self")
        )
        self.print_timeout = print_timeout

        self.executor = executor
        if not executor:
            self.executor = ThreadPoolExecutor(
                max_workers=8, thread_name_prefix="AnnouncerDefault"
            )

        # State table to add all healthy prefixes in so
        # we know what to reannounce # when a new peer is established
        self.healthy_prefixes: Set[IPNetwork] = set()

        # Lock to ensure we're only printing one command at a time
        # GIL will prob ensure this, but lets explicitly lock
        self.print_lock = asyncio.Lock()

    # TODO: Test to see if we still need this
    def _cleanup_executor(self, wait: bool = False) -> None:
        if not self.executor:
            LOG.debug(f"Executor is falsey. Not cleaning up executor {self.executor}")
            return

        if isinstance(self.executor, ThreadPoolExecutor):
            for thread in self.executor._threads:
                try:
                    thread._tstate_lock.release()  # type: ignore
                except Exception as e:
                    LOG.debug(f"Problem with releasing a thread: {e}")
                    pass

        LOG.info("Shutting down executor pool")
        self.executor.shutdown(wait=wait)

    async def nonblock_print(self, output: str) -> bool:
        """Lock for one print @ a time + wrap print so we
        don't block and can timeout"""
        try:
            async with self.print_lock:
                LOG.debug(f"Attempting to print '{output}' to STDOUT")
                await asyncio.wait_for(
                    self.loop.run_in_executor(
                        self.executor, partial(print, output, flush=True)
                    ),
                    self.print_timeout,
                )
        except asyncio.TimeoutError:
            LOG.error(f"Timeout: Unable to print '{output}'")
            return False
        return True

    async def nonblock_read(self, input: TextIO = stdin) -> str:
        """Wrap stdin.read() so we can wait for input non-blocking other coroutines"""
        stdin_line = await self.loop.run_in_executor(self.executor, input.readline)
        return stdin_line.strip()

    def remove_internal_networks(
        self, bgp_prefixes: List[FibPrefix]
    ) -> List[FibPrefix]:
        """Check if exabgp has told us about an internal summary
        If so remove it from being internally advertised to our FIBs"""
        if not bgp_prefixes:
            return bgp_prefixes

        current_advertise_networks = set(self.advertise_prefixes.keys())
        default_prefixes = {ip_network("0.0.0.0/0"), ip_network("::/0")}
        valid_redist_networks: Dict[int, Set[FibPrefix]] = {4: set(), 6: set()}

        allow_default = self.config["learn"].get("allow_default", False)
        for aprefix in bgp_prefixes:
            if allow_default and aprefix.prefix in default_prefixes:
                valid_redist_networks[aprefix.prefix.version].add(aprefix)
                continue

            if aprefix.prefix in current_advertise_networks:
                LOG.debug(
                    f"Not advertising {aprefix} to a FIB. "
                    + "It's a summary we advertise over BGP"
                )
                continue

            is_a_subnet = False
            for advertise_network in current_advertise_networks:
                if advertise_network.version != aprefix.prefix.version:
                    continue
                if advertise_network.overlaps(aprefix.prefix):
                    LOG.debug(
                        f"{aprefix} is a subnet of {advertise_network}. "
                        + "Not advertising to a FIB"
                    )
                    is_a_subnet = True
                    break

            if not is_a_subnet:
                valid_redist_networks[aprefix.prefix.version].add(aprefix)

        return sorted(valid_redist_networks[4]) + sorted(valid_redist_networks[6])

    def validate_next_hop(self, next_hop: str) -> str:
        """Ensure next hop can ONLY be self of a valid IP Address"""
        if next_hop.lower() == "self":
            return next_hop.lower()

        ip_next_hop = ip_address(next_hop)
        return str(ip_next_hop.compressed)

    async def add_routes(self, prefixes: Sequence[IPNetwork]) -> int:
        success = 0
        for prefix in prefixes:
            output = f"announce route {prefix} next-hop {self.next_hop}"
            print_success = await self.nonblock_print(output)
            if not print_success:
                continue
            LOG.info(f"Advertising {prefix} prefix: {output}")
            success += 1
        return success

    async def withdraw_routes(self, prefixes: Sequence[IPNetwork]) -> int:
        success = 0
        for prefix in prefixes:
            output = f"withdraw route {prefix} next-hop {self.next_hop}"
            print_success = await self.nonblock_print(output)
            if not print_success:
                continue
            LOG.info(f"Withdrawing {prefix} prefix: {output}")
            success += 1
        return success

    async def withdraw_all_routes(self) -> int:
        """Withdraw all routes in self.advertise_prefixes"""
        all_prefixes = sorted(self.advertise_prefixes.keys())
        if not all_prefixes:
            return 0

        LOG.info(f"Sending withdraws for all {len(all_prefixes)} prefixes")
        successful_count = await self.withdraw_routes(all_prefixes)
        if successful_count != len(all_prefixes):
            LOG.error(
                "Did not sucessfully send withdraws for all prefixes "
                + f"({successful_count} / {len(all_prefixes)})"
            )
        return successful_count

    async def coordinator(self) -> None:
        LOG.info(f"Monitoring and announcing {len(self.advertise_prefixes)} prefixes")
        route_coros = [self.advertise()]
        if self.learn_fibs:
            LOG.info(f"Will program learned routes to {' '.join(self.learn_fibs)} FIBs")
            route_coros.append(self.learn())

        try:
            await asyncio.gather(*route_coros)
        except asyncio.CancelledError:
            if self.config["advertise"].get("withdraw_on_exit", False):
                # Lets cleanly tell peer(s) to withdraw as we're going down if set
                await self.withdraw_all_routes()
            self._cleanup_executor()
            raise

    async def advertise(self) -> None:
        while True:
            interval = self.config["advertise"]["interval"]
            start_time = time()

            healthcheck_coros: List[Awaitable] = []
            for prefix, checks in self.advertise_prefixes.items():
                LOG.debug(f"Scheduling health check(s) for {prefix}")
                for check in checks:
                    healthcheck_coros.append(check.check())

            # TODO: Create consumer worker pool
            healthcheck_results = await asyncio.gather(*healthcheck_coros)

            start_at = 0
            advertise_routes: List[IPNetwork] = []
            withdraw_routes: List[IPNetwork] = []
            for prefix, checks in self.advertise_prefixes.items():
                end_results = start_at + len(checks)
                my_results = healthcheck_results[start_at:end_results]

                if map(lambda r: isinstance(r, Exception), my_results) and all(
                    my_results
                ):
                    advertise_routes.append(prefix)
                else:
                    withdraw_routes.append(prefix)

                start_at += 1

            if advertise_routes:
                if not await self.add_routes(advertise_routes):
                    LOG.error(f"Failed to announce {advertise_routes}")
                    self.healthy_prefixes = set()
                else:
                    self.healthy_prefixes = set(advertise_routes)
            if withdraw_routes:
                if not await self.withdraw_routes(withdraw_routes):
                    LOG.error(f"Failed to withdraw {withdraw_routes}")
                if not advertise_routes:
                    self.healthy_prefixes = set()

            run_time = time() - start_time
            sleep_time = interval - run_time
            if sleep_time < 0:
                LOG.debug(f"Sleep time was negative: {sleep_time}s. Setting to 0")
                sleep_time = 0
            LOG.info(f"Route checks complete. Sleeping for {sleep_time}s")
            await asyncio.sleep(sleep_time)

    async def learn(self) -> None:  # noqa: C901
        """Read messages from exabgp and act accordinly
        - We only support JSON API"""
        ejp = ExaBGPParser()

        fib_names = self.config["learn"].get("fibs", [])
        fib_consumer = self.loop.create_task(
            prefix_consumer(
                self.learn_queue, fib_names, self.config, dry_run=self.dry_run
            )
        )
        LOG.debug("Started a FIB operation consumer")

        try:
            while True:
                LOG.debug("Waiting for API JSON via stdin")
                bgp_msg = await self.nonblock_read()

                # TODO: Evaluate if we should care and check if we get a done message
                # Ignore done from API calls
                if bgp_msg.strip() == "done":
                    LOG.debug("Recieved a 'done' message from exabgp")
                    continue

                try:
                    bgp_json = await self.loop.run_in_executor(
                        self.executor, loads, bgp_msg
                    )
                except JSONDecodeError as jde:
                    LOG.error(f"Invalid API JSON (skipping): '{bgp_msg}' ({jde})")
                    continue

                # TODO: Work out if this needs to go for close / disconnect messages
                if "neighbor" not in bgp_json:
                    LOG.debug(f"Ignoring non neighbor JSON: {bgp_json}")
                    continue

                fib_operations = await ejp.parse(bgp_json, self.healthy_prefixes)
                if not fib_operations:
                    LOG.error(
                        f"Didn't parse a valid fib operation from API JSON: {bgp_json}"
                    )
                    continue

                # Check if we're only FibOperation.REMOVE_ALL_ROUTES
                remove_all_routes_only = True
                for op in fib_operations:
                    if op.operation != FibOperation.REMOVE_ALL_ROUTES:
                        remove_all_routes_only = False
                        break

                if not remove_all_routes_only:
                    fib_operations = self.remove_internal_networks(fib_operations)
                    if not fib_operations:
                        LOG.debug(
                            f"Did not get an external prefix from API JSON: {bgp_json}"
                        )
                        continue

                LOG.debug(f"Adding {fib_operations} to learn_queue")
                await self.learn_queue.put(fib_operations)
        except asyncio.CancelledError:
            fib_consumer.cancel()
            raise
