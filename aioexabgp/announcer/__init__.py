#!/usr/bin/env python3
""" Read ExaBGP JSON from STDIN and push commands via STDOUT """

import asyncio
import logging
from functools import partial
from ipaddress import IPv4Network, IPv6Network
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Dict, Optional, Sequence, Union

# from .health_checks import HealthCheck

LOG = logging.getLogger(__name__)


class Announcer:
    def __init__(
        self,
        config: Dict,
        *,
        # health_checks: Sequence[HealthCheck],
        executor: Optional[Union[ProcessPoolExecutor, ThreadPoolExecutor]] = None,
        print_timeout: float = 5.0,
    ) -> None:
        self.config = config
        self.executor = executor
        self.loop = asyncio.get_event_loop()
        self.print_timeout = print_timeout
        # self.heath_checks = health_checks

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
            LOG.error(f"Timeout: Unable to print {output}")
            return False
        return True

    async def add_routes(
        self,
        prefixes: Sequence[Union[IPv4Network, IPv6Network]],
        *,
        next_hop: str = "self",
    ) -> int:
        success = 0
        for prefix in prefixes:
            output = f"announce route {prefix} next-hop {next_hop}"
            if not await self.nonblock_print(output):
                continue
            success += 1
        return success

    async def withdraw_routes(
        self, prefixes: Sequence[Union[IPv4Network, IPv6Network]]
    ) -> int:
        success = 0
        for prefix in prefixes:
            output = f"withdraw route {prefix}"
            if not await self.nonblock_print(output):
                continue
            success += 1
        return success

    async def advertise(self) -> None:
        raise NotImplementedError("Subclass and implement")

    async def learn(self) -> None:
        raise NotImplementedError("Subclass and implement")
