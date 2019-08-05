#!/usr/bin/env python3.7

import unittest
from ipaddress import ip_network

from aioexabgp.announcer.fibs import Fib, get_fib


# TODO: Get a better test config + test more of the Fib class
FAKE_CONFIG = {"learn": {"allow_default": True, "prefix_limit": 10}}


class FibsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.afib = Fib(FAKE_CONFIG)

    def test_is_defualt(self) -> None:
        self.assertTrue(self.afib.is_default(ip_network("::/0")))
        self.assertFalse(self.afib.is_default(ip_network("69::/32")))
        self.assertFalse(self.afib.is_default(None))

    def test_get_fib(self) -> None:
        # Here we on purpose do not use FAKE_CONFIG
        bs_config = {"learn": {}}
        lf = get_fib("Linux", bs_config)
        self.assertTrue(isinstance(lf, Fib))

        with self.assertRaises(ValueError):
            get_fib("JunOS", bs_config)
