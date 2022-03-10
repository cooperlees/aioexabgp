#!/usr/bin/env python3

import asyncio
import unittest
from unittest.mock import Mock, patch

from aioexabgp.exabgpparser import ExaBGPParser
from aioexabgp.tests.exabgpparser_fixtures import (
    EXABGP_BAD_VERSION_JSON,
    EXABGP_CONNECTED_JSON,
    EXABGP_DOWN_JSON,
    EXPECTED_DOWN_RESPONSE,
    EXABGP_UP_JSON,
    EXPECTED_UP_RESPONSE,
    EXABGP_UPDATE_JSON,
    EXPECTED_UPDATE_REPONSE,
    EXABGP_UPDATE_SEND_JSON,
    EXABGP_WITHDRAW_JSON,
    EXPECTED_WITHDRAW_REPONSE,
    FAKE_HEALTHY_PREFIXES,
)


class ExabgpParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ebp = ExaBGPParser()
        self.loop = asyncio.get_event_loop()

    def test_parse_bad_api_version(self) -> None:
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(self.ebp.parse(EXABGP_BAD_VERSION_JSON))

    @patch("aioexabgp.exabgpparser.LOG.info")
    def test_parse_state_connected(self, mock_info: Mock) -> None:
        self.loop.run_until_complete(self.ebp.parse(EXABGP_CONNECTED_JSON))
        self.assertEqual(1, mock_info.call_count)

    @patch("aioexabgp.exabgpparser.LOG.error")
    def test_parse_state_down(self, mock_error: Mock) -> None:
        self.assertEqual(
            EXPECTED_DOWN_RESPONSE,
            self.loop.run_until_complete(self.ebp.parse(EXABGP_DOWN_JSON)),
        )
        self.assertEqual(1, mock_error.call_count)

    def test_parse_state_up(self) -> None:
        self.assertEqual(
            EXPECTED_UP_RESPONSE,
            self.loop.run_until_complete(
                self.ebp.parse(EXABGP_UP_JSON, FAKE_HEALTHY_PREFIXES)
            ),
        )
        self.assertFalse(self.loop.run_until_complete(self.ebp.parse(EXABGP_UP_JSON)))

    def test_parse_update_announce(self) -> None:
        self.assertEqual(
            EXPECTED_UPDATE_REPONSE,
            self.loop.run_until_complete(self.ebp.parse(EXABGP_UPDATE_JSON)),
        )

    def test_parse_update_withdraw(self) -> None:
        self.assertEqual(
            EXPECTED_WITHDRAW_REPONSE,
            self.loop.run_until_complete(self.ebp.parse(EXABGP_WITHDRAW_JSON)),
        )

    def test_parse_update_direction_send(self) -> None:
        self.assertEqual(
            [],
            self.loop.run_until_complete(self.ebp.parse(EXABGP_UPDATE_SEND_JSON)),
        )
