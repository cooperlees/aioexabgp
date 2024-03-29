#!/usr/bin/env python3

import asyncio
import unittest
from contextlib import redirect_stdout
from io import StringIO
from ipaddress import ip_network
from unittest.mock import patch

from aioexabgp.announcer import Announcer
from aioexabgp.announcer.fibs import FibOperation, FibPrefix
from aioexabgp.announcer.healthcheck import gen_advertise_prefixes

# TODO: EXABGP_ANNOUNCE_JSON, WITHDRAW_JSON
from aioexabgp.tests.announcer_fixtures import ANNOUNCER_CONFIG, NEXT_HOP


class AnnouncerTests(unittest.TestCase):
    def setUp(self) -> None:
        advertise_prefixes = gen_advertise_prefixes(ANNOUNCER_CONFIG)
        self.aa = Announcer(ANNOUNCER_CONFIG, advertise_prefixes)
        self.loop = asyncio.get_event_loop()

    def test_cleanup_executor(self) -> None:
        aa = Announcer(ANNOUNCER_CONFIG, gen_advertise_prefixes(ANNOUNCER_CONFIG))
        with patch("aioexabgp.announcer.LOG.info") as mock_log:
            aa._cleanup_executor(wait=True)
            self.assertTrue(mock_log.called)

        # Test falsey executor
        aa.executor = None
        with patch("aioexabgp.announcer.LOG.debug") as mock_log:
            aa._cleanup_executor()
            self.assertTrue(mock_log.called)

    def test_validate_next_hop(self) -> None:
        self.assertEqual("self", self.aa.validate_next_hop("sELf"))
        self.assertEqual(
            "69::1",
            self.aa.validate_next_hop("0069:0000:0000:0000:0000:0000:0000:0001"),
        )
        with self.assertRaises(ValueError):
            self.aa.validate_next_hop("cooper69")

    def test_add_routes(self) -> None:
        prefix = sorted(self.aa.advertise_prefixes.keys()).pop()
        expected_output = f"announce route {prefix} next-hop {NEXT_HOP}"
        with StringIO() as buf, redirect_stdout(buf):
            added_count = self.loop.run_until_complete(self.aa.add_routes([prefix]))
            output = buf.getvalue().strip()
        self.assertEqual(added_count, 1)
        self.assertEqual(expected_output, output)

    def test_withdraw_routes(self) -> None:
        prefix = sorted(self.aa.advertise_prefixes.keys()).pop()
        expected_output = f"withdraw route {prefix} next-hop {NEXT_HOP}"
        with StringIO() as buf, redirect_stdout(buf):
            added_count = self.loop.run_until_complete(
                self.aa.withdraw_routes([prefix])
            )
            output = buf.getvalue().strip()
        self.assertEqual(added_count, 1)
        self.assertEqual(expected_output, output)

    def test_withdraw_all_routes(self) -> None:
        expected_output = (
            "withdraw route 69::/32 next-hop 2000:69::1\n"
            + "withdraw route 70::/32 next-hop 2000:69::1"
        )
        with StringIO() as buf, redirect_stdout(buf):
            successful_withdraws = self.loop.run_until_complete(
                self.aa.withdraw_all_routes()
            )
            output = buf.getvalue().strip()
        self.assertEqual(successful_withdraws, 2)
        self.assertEqual(expected_output, output)

    def test_nonblock_print(self) -> None:
        expected_output = "Hello World!"
        with StringIO() as buf, redirect_stdout(buf):
            self.loop.run_until_complete(self.aa.nonblock_print(expected_output))
            output = buf.getvalue().strip()
        self.assertEqual(expected_output, output)

    def test_nonblock_read(self) -> None:
        line1 = "Line 1\n"
        fake_stdin = StringIO(f"{line1}line2\n")
        self.assertEqual(
            self.loop.run_until_complete(self.aa.nonblock_read(fake_stdin)),
            line1.strip(),
        )

    def test_remove_internal_networks(self) -> None:
        potential_networks = [
            FibPrefix(ip_network("69::/32"), None, FibOperation.ADD_ROUTE),
            FibPrefix(ip_network("69::/64"), None, FibOperation.ADD_ROUTE),
            FibPrefix(ip_network("6.9.6.0/24"), None, FibOperation.ADD_ROUTE),
            FibPrefix(ip_network("14:69::/64"), None, FibOperation.ADD_ROUTE),
            FibPrefix(ip_network("11:69::/64"), None, FibOperation.ADD_ROUTE),
        ]
        # Making list in specific way to ensure return is sorted()
        self.assertEqual(
            self.aa.remove_internal_networks(potential_networks),
            [potential_networks[2], potential_networks[-1], potential_networks[-2]],
        )

    def test_ensure_default_remove_internal_networks(self) -> None:
        potential_networks = [
            FibPrefix(ip_network("::/0"), None, FibOperation.ADD_ROUTE)
        ]
        self.assertEqual(
            self.aa.remove_internal_networks(potential_networks), potential_networks
        )
