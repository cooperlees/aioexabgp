#!/usr/bin/env python3
""" Read ExaBGP JSON from STDIN and push commands via STDOUT """

import asyncio
import logging
from functools import partial
from ipaddress import IPv4Network, IPv6Network
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from time import time
from typing import Awaitable, Dict, List, Optional, Sequence, Union

from .healthcheck import HealthChecker

IPNetwork = Union[IPv4Network, IPv6Network]
LOG = logging.getLogger(__name__)


class Announcer:
    def __init__(
        self,
        config: Dict,
        advertise_prefixes: Dict[IPNetwork, Sequence[HealthChecker]],
        learn_fibs: Sequence[str],
        *,
        executor: Optional[Union[ProcessPoolExecutor, ThreadPoolExecutor]] = None,
        print_timeout: float = 5.0,
    ) -> None:
        self.advertise_prefixes = advertise_prefixes
        self.config = config
        self.executor = executor
        self.learn_fibs = learn_fibs
        self.loop = asyncio.get_event_loop()
        self.print_timeout = print_timeout

    async def nonblock_print(self, output: str) -> bool:
        """ Wrap print so we can timeout """
        try:
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

    async def add_routes(
        self, prefixes: Sequence[IPNetwork], *, next_hop: str = "self"
    ) -> int:
        success = 0
        for prefix in prefixes:
            output = f"announce route {prefix} next-hop {next_hop}"
            if not await self.nonblock_print(output):
                continue
            success += 1
        return success

    async def withdraw_routes(self, prefixes: Sequence[IPNetwork]) -> int:
        success = 0
        for prefix in prefixes:
            output = f"withdraw route {prefix}"
            if not await self.nonblock_print(output):
                continue
            success += 1
        return success

    async def coordinator(self, *, dry_run: bool = False) -> None:
        LOG.info(f"Monitoring and announcing {len(self.advertise_prefixes)} prefixes")
        route_coros = [self.advertise()]
        if self.learn_fibs:
            LOG.info(f"Will program learned routes to {' '.join(self.learn_fibs)} FIBs")
            route_coros.append(self.learn())

        await asyncio.gather(*route_coros)

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
                    LOG.info(f"Advertising {prefix} prefix")
                    advertise_routes.append(prefix)
                else:
                    LOG.info(f"Withdrawing {prefix} prefix")
                    withdraw_routes.append(prefix)

                start_at += 1

            if advertise_routes:
                await self.add_routes(advertise_routes)
            if withdraw_routes:
                await self.withdraw_routes(withdraw_routes)

            run_time = time() - start_time
            sleep_time = interval - run_time
            LOG.debug(f"Route check original sleep_time = {sleep_time}s")
            if sleep_time < 0:
                sleep_time = 0
            LOG.info(f"Route checks complete. Sleeping for {sleep_time}s")
            await asyncio.sleep(sleep_time)

    async def learn(self) -> None:
        """ asyncio Task to monitor and program routes into some route store
            - e.g. Linux routing table or VPP FIB """
        raise NotImplementedError("Subclass and implement")
