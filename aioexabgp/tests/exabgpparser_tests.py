#!/usr/bin/env python3.7

import asyncio
import unittest

from aioexabgp.exabgpparser import ExaBGPParser
from aioexabgp.tests.exabgpparser_fixtures import (
    EXABGP_UPDATE_JSON,
    EXPECTED_UPDATE_REPONSE,
    EXABGP_WITHDRAW_JSON,
    EXPECTED_WITHDRAW_REPONSE,
)


class ExabgpParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ebp = ExaBGPParser()
        self.loop = asyncio.get_event_loop()

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
