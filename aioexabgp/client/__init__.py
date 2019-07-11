#!/usr/bin/env python3
""" Read ExaBGP JSON from STDIN and push commands vis STDOUT """

import logging
from typing import Dict

# from .health_checks import HealthCheck

LOG = logging.getLogger(__name__)


class ExaBGPClient:
    # def __init__(self, config: Dict, health_checks: Sequence[HealthCheck]) -> None:
    def __init__(self, config: Dict) -> None:
        self.config = config
        # self.heath_checks = health_checks

    async def add_routes(self) -> bool:
        return False

    async def withdraw_routes(self) -> bool:
        return False

    async def monitor(self) -> None:
        raise NotImplementedError("Subclass and implement")
