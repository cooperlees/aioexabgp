#!/usr/bin/env python3

import unittest
from asyncio import get_event_loop
from unittest.mock import patch
from ipaddress import ip_address, ip_network
from typing import List, Sequence

from aioexabgp.announcer.fibs import (
    BGP_LEARNT_PREFIXES,
    Fib,
    FibOperation,
    FibPrefix,
    LinuxFib,
    _update_learnt_routes,
    get_fib,
)


# TODO: Get a better test config + test more of the Fib class
FAKE_CONFIG = {
    "learn": {"allow_default": True, "allow_ll_nexthop": True, "prefix_limit": 10}
}
NETWORK_PREFIXES = (ip_network("::/0"), ip_network("69::/64"))


def gen_fib_operations(
    operation: FibOperation, errors: bool = False
) -> Sequence[FibPrefix]:
    fib_ops: List[FibPrefix] = []
    next_hop = ip_address("2469::1")

    for prefix in NETWORK_PREFIXES:
        if errors:
            fib_ops.append(FibPrefix(prefix, None, operation))
            continue
        fib_ops.append(FibPrefix(prefix, next_hop, operation))

    return fib_ops


class FibsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.afib = Fib(FAKE_CONFIG)
        self.loop = get_event_loop()

    def test_is_defualt(self) -> None:
        self.assertTrue(self.afib.is_default(ip_network("::/0")))
        self.assertFalse(self.afib.is_default(ip_network("69::/32")))
        self.assertFalse(self.afib.is_default(None))

    def test_is_link_local(self) -> None:
        # v6
        self.assertTrue(self.afib.is_link_local(ip_address("fe80::69")))
        self.assertTrue(self.afib.is_link_local(ip_network("fe80::/64")))
        self.assertFalse(self.afib.is_link_local(ip_address("69::69")))
        self.assertFalse(self.afib.is_link_local(ip_network("69::/64")))
        # v4
        self.assertTrue(self.afib.is_link_local(ip_address("169.254.69.69")))
        self.assertTrue(self.afib.is_link_local(ip_network("169.254.69.0/24")))
        self.assertFalse(self.afib.is_link_local(ip_address("6.9.6.9")))
        self.assertFalse(self.afib.is_link_local(ip_network("6.9.6.0/24")))

    def test_add_route(self) -> None:
        default_prefix = ip_network("::/0")
        valid_next_hop = ip_address("69::69")
        self.assertTrue(
            self.loop.run_until_complete(
                self.afib.add_route(default_prefix, valid_next_hop)
            )
        )

        # Ensure we don't allow a default
        self.afib.default_allowed = False
        self.assertFalse(
            self.loop.run_until_complete(
                self.afib.add_route(default_prefix, valid_next_hop)
            )
        )

        # Ensure we don't allow link local next hop
        self.afib.default_allowed = True
        self.afib.allow_ll_nexthop = False
        link_local_next_hop = ip_address("fe80::69")
        self.assertFalse(
            self.loop.run_until_complete(
                self.afib.add_route(default_prefix, link_local_next_hop)
            )
        )

        # Restore default allow ll
        self.afib.allow_ll_nexthop = True

    def test_get_fib(self) -> None:
        # Here we on purpose do not use FAKE_CONFIG
        bs_config = {"learn": {}}
        lf = get_fib("Linux", bs_config)
        self.assertTrue(isinstance(lf, Fib))

        with self.assertRaises(ValueError):
            get_fib("JunOS", bs_config)

    def test_update_learnt_routes(self) -> None:
        # Make sure dict is empty
        self.assertFalse(BGP_LEARNT_PREFIXES)
        # Add some prefixes
        adds, dels = _update_learnt_routes(gen_fib_operations(FibOperation.ADD_ROUTE))
        self.assertEqual(adds, 2)
        self.assertEqual(dels, 0)
        self.assertTrue(BGP_LEARNT_PREFIXES)
        # Delete some prefixes
        adds, dels = _update_learnt_routes(
            gen_fib_operations(FibOperation.REMOVE_ROUTE)
        )
        self.assertEqual(adds, 0)
        self.assertEqual(dels, 2)
        # Make sure dict is empty again
        self.assertFalse(BGP_LEARNT_PREFIXES)

        with patch("aioexabgp.announcer.fibs.LOG.error") as mocked_err_log:
            adds, dels = _update_learnt_routes(
                gen_fib_operations(FibOperation.REMOVE_ROUTE, errors=True)
            )
            self.assertEqual(mocked_err_log.call_count, 2)
        self.assertEqual(adds, 0)
        self.assertEqual(dels, 0)
        self.assertFalse(BGP_LEARNT_PREFIXES)

        # Add and remove all
        adds, dels = _update_learnt_routes(gen_fib_operations(FibOperation.ADD_ROUTE))
        adds, dels = _update_learnt_routes(
            [
                FibPrefix(
                    ip_network("69::/64"),
                    ip_address("2469::1"),
                    FibOperation.REMOVE_ALL_ROUTES,
                )
            ]
        )
        self.assertEqual(dels, 2)
        self.assertFalse(BGP_LEARNT_PREFIXES)


class LinuxFibsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lfib = LinuxFib(FAKE_CONFIG)
        self.loop = get_event_loop()

    def test_gen_route_cmd(self) -> None:
        # test v4 via v6
        default_v4_prefix = ip_network("0.0.0.0/0")
        v6_next_hop = ip_address("69::69")
        self.assertEqual(
            [
                self.lfib.SUDO_CMD,
                self.lfib.IP_CMD,
                "-4",
                "route",
                "add",
                "default",
                "via",
                "inet6",
                "69::69",
            ],
            self.lfib.gen_route_cmd("add", default_v4_prefix, v6_next_hop),
        )

        # test v4
        sixty_nine_prefix = ip_network("69.0.0.0/8")
        v4_next_hop = ip_address("6.9.6.9")
        self.assertEqual(
            [
                self.lfib.SUDO_CMD,
                self.lfib.IP_CMD,
                "-4",
                "route",
                "add",
                sixty_nine_prefix.compressed,
                "via",
                "6.9.6.9",
            ],
            self.lfib.gen_route_cmd("add", sixty_nine_prefix, v4_next_hop),
        )

        # test v6
        sixty_nine_prefix = ip_network("69::/64")
        v6_next_hop = ip_address("70::69")
        self.assertEqual(
            [
                self.lfib.SUDO_CMD,
                self.lfib.IP_CMD,
                "-6",
                "route",
                "delete",
                sixty_nine_prefix.compressed,
                "via",
                "6.9.6.9",
            ],
            self.lfib.gen_route_cmd("delete", sixty_nine_prefix, v6_next_hop),
        )
