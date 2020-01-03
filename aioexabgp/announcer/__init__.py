#!/usr/bin/env python3
""" Read ExaBGP JSON from STDIN and push commands via STDOUT """

import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from ipaddress import IPv4Address, IPv6Address, IPv4Network, IPv6Network, ip_address
from json import JSONDecodeError, loads
from sys import stdin
from time import time
from typing import Awaitable, Dict, List, Optional, Set, Sequence, TextIO, Union

from aioexabgp.exabgpparser import ExaBGPParser
from .fibs import FibPrefix, prefix_consumer
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

    async def nonblock_print(self, output: str) -> bool:
        """ Lock for one print @ a time + wrap print so we
            don't block and can timeout """
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
        """ Wrap stdin.read() so we can wait for input non-blocking other coroutines """
        stdin_line = await self.loop.run_in_executor(self.executor, input.readline)
        return stdin_line.strip()

    def remove_internal_networks(
        self, bgp_prefixes: List[FibPrefix], ip_version: int = 6
    ) -> List[FibPrefix]:
        """ Check if exabgp has told us about an internal summary
            If so remove it from being internally advertised to our FIBs"""
        if not bgp_prefixes:
            return bgp_prefixes

        current_advertise_networks = set(self.advertise_prefixes.keys())
        valid_redist_networks: Set[FibPrefix] = set()
        for aprefix in bgp_prefixes:
            if aprefix.prefix.version != ip_version:
                LOG.error(
                    f"{aprefix} was passed. We only accept IP version {ip_version}"
                )
                continue

            if aprefix.prefix in current_advertise_networks:
                LOG.debug(
                    f"Not advertising {aprefix} to a FIB. "
                    + "It's a summary we advertise over BGP"
                )
                continue

            is_a_subnet = False
            for advertise_network in current_advertise_networks:
                # `mypy` complains about "_BaseNetwork" has incompatible type "Union[IPv4Network, IPv6Network]"
                # Typeshed even stats overlaps() on _BaseNetwork
                # With the isinstance check above I feel this is safe to merge: Follow Up Issue: #6
                if advertise_network.overlaps(aprefix.prefix):  # type: ignore
                    LOG.debug(
                        f"{aprefix} is a subnet of {advertise_network}. "
                        + "Not advertising to a FIB"
                    )
                    is_a_subnet = True
                    break

            if not is_a_subnet:
                valid_redist_networks.add(aprefix)

        return sorted(valid_redist_networks)

    def validate_next_hop(self, next_hop: str) -> str:
        """ Ensure next hop can ONLY be self of a valid IP Address """
        if next_hop.lower() == "self":
            return next_hop.lower()

        ip_next_hop = ip_address(next_hop)
        return ip_next_hop.compressed

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

    async def coordinator(self) -> None:
        LOG.info(f"Monitoring and announcing {len(self.advertise_prefixes)} prefixes")
        route_coros = [self.advertise()]
        if self.learn_fibs:
            LOG.info(f"Will program learned routes to {' '.join(self.learn_fibs)} FIBs")
            route_coros.append(self.learn())

        try:
            await asyncio.gather(*route_coros)
        except asyncio.CancelledError:
            if self.executor:
                self.executor.shutdown(wait=False)
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

    async def learn(self) -> None:
        """ Read messages from exabgp and act accordinly
            - We only support JSON API """
        ejp = ExaBGPParser()

        fib_names = self.config["learn"].get("fibs", [])
        fib_consumer = self.loop.create_task(
            prefix_consumer(
                self.learn_queue, fib_names, self.config, dry_run=self.dry_run
            )
        )
        LOG.debug(f"Started a FIB operation consumer")

        try:
            while True:
                LOG.debug(f"Waiting for API JSON via stdin")
                bgp_msg = await self.nonblock_read()

                # TODO: Evaluate if we should care and check if we get a done message
                # Ignore done from API calls
                if bgp_msg.strip() == "done":
                    LOG.debug(f"Recieved a 'done' message from exabgp")
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
