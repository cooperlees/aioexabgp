#!/usr/bin/env python3

import logging
from ipaddress import ip_address, ip_network
from typing import Dict, List, Sequence

from aioexabgp.announcer.fibs import FibOperation, FibPrefix


# TODO: Plumb up to config
DEFAULT_FAMALIES = ["ipv4 unicast", "ipv6 unicast"]
LOG = logging.getLogger(__name__)


class ExaBGPParser:
    """ Class to parse ExaBGP JSON and return FibPrefix """

    SUPPORTED_API_VERSION = "4.0.1"

    async def parse(self, exa_json: Dict) -> List[FibPrefix]:
        # TODO: Handle peer disappearing / closing
        if exa_json["type"] == "update":
            return await self.parse_update(exa_json)
        else:
            LOG.error(f"neighbor JSON not parsed: {exa_json}")

        return []

    # TODO: Split this function - To complex and not clean
    async def parse_update(
        self, exa_json: Dict, wanted_families: Sequence[str] = DEFAULT_FAMALIES
    ) -> List[FibPrefix]:
        fib_prefixes: List[FibPrefix] = []
        try:
            update_json = exa_json["neighbor"]["message"]["update"]
            peer = exa_json["neighbor"]["address"]["peer"]

            for operation, prefixes in update_json.items():
                if operation == "attribute":
                    continue

                for family, peers in prefixes.items():
                    if family not in wanted_families:
                        LOG.debug(f"Ignoring {family} routes from {peer}")
                        continue

                    if operation == "announce":
                        for next_hop, prefixes in peers.items():
                            for prefix in prefixes:
                                fib_prefixes.append(
                                    FibPrefix(
                                        ip_network(prefix["nlri"]),
                                        ip_address(next_hop),
                                        FibOperation.ADD_ROUTE,
                                    )
                                )
                    elif operation == "withdraw":
                        for prefix in peers:
                            fib_prefixes.append(
                                FibPrefix(
                                    ip_network(prefix["nlri"]),
                                    None,
                                    FibOperation.REMOVE_ROUTE,
                                )
                            )
        except (KeyError, ValueError) as ve:
            LOG.error(f"Unable to parse BGP update: {exa_json} ({ve})")

        return fib_prefixes
