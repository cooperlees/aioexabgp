#!/usr/bin/env python3
""" Read ExaBGP JSON from STDIN and push commands via STDOUT """

import asyncio
import logging
from functools import partial
from ipaddress import IPv4Network, IPv6Network
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Dict, Optional, Sequence, Union

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
        """ asyncio Task to monitor which prefixes to advertise """
        raise NotImplementedError("Subclass and implement")

    async def learn(self) -> None:
        """ asyncio Task to monitor and program routes into some route store
            - e.g. Linux routing table or VPP FIB """
        raise NotImplementedError("Subclass and implement")
