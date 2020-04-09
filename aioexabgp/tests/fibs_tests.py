#!/usr/bin/env python3.7

import unittest
from unittest.mock import patch
from ipaddress import ip_address, ip_network
from typing import List, Sequence

from aioexabgp.announcer.fibs import (
    BGP_LEARNT_PREFIXES,
    Fib,
    FibOperation,
    FibPrefix,
    _update_learnt_routes,
    get_fib,
)


# TODO: Get a better test config + test more of the Fib class
FAKE_CONFIG = {"learn": {"allow_default": True, "prefix_limit": 10}}
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
