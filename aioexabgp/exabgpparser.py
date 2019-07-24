#!/usr/bin/env python3

import logging
from ipaddress import ip_address, ip_network
from json import dumps
from typing import Dict, List, Sequence

from aioexabgp.announcer.fibs import FibOperation, FibPrefix


# TODO: Plumb up to config
DEFAULT_FAMALIES = ["ipv4 unicast", "ipv6 unicast"]
LOG = logging.getLogger(__name__)


class ExaBGPParser:
    """ Class to parse ExaBGP JSON and return FibPrefix """

    SUPPORTED_API_VERSION = "4.0.1"

    async def parse(self, exa_json: Dict) -> List[FibPrefix]:
        if exa_json["exabgp"] != self.SUPPORTED_API_VERSION:
            raise ValueError(
                f"Exabgp JSON version has changed from know tested version. Investigate"
            )

        if exa_json["type"].lower() == "state":
            peer = exa_json["neighbor"]["address"]["peer"]
            state = exa_json["neighbor"]["state"]
            if state.lower() == "connected":
                LOG.info(f"Peer {peer}: BGP has reached 'connected' state")
            elif state.lower() == "down":
                reason = exa_json["neighbor"]["reason"]
                LOG.error(
                    f"Peer {peer}: BGP has reached 'down' state. Reason: {reason}"
                )
                return [
                    FibPrefix(
                        ip_network("::/0"),
                        ip_address(peer),
                        FibOperation.REMOVE_ALL_ROUTES,
                    )
                ]
            else:
                LOG.info(f"Peer {peer}: BGP has gone to '{state}' state.")
        elif exa_json["type"].lower() == "update":
            return await self.parse_update(exa_json)
        else:
            LOG.error(f"exabgp JSON not parsed:\n{dumps(exa_json)}")

        return []

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
                        LOG.info(
                            f"Peer {peer}: Sent {len(fib_prefixes)} to add to fibs"
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
                        LOG.info(
                            f"Peer {peer}: Sent {len(fib_prefixes)} to remove from fibs"
                        )
        except (KeyError, ValueError) as ve:
            LOG.error(f"Unable to parse BGP update: {exa_json} ({ve})")

        return fib_prefixes
