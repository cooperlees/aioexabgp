#!/usr/bin/env python3

import asyncio
import unittest

from unittest.mock import Mock, patch

from aioexabgp import utils


class UtilsTests(unittest.TestCase):
    @patch("aioexabgp.utils.LOG.error")
    def test_run_cmd(self, mock_log: Mock):
        loop = asyncio.get_event_loop()
        # Success
        self.assertEqual(
            0,
            loop.run_until_complete(utils.run_cmd(("echo", "Hello World"))).returncode,
        )
        # Fail
        self.assertEqual(
            1,
            loop.run_until_complete(
                utils.run_cmd(("grep", "CatDog69", "/etc/hosts"))
            ).returncode,
        )
        # Timeout
        self.assertEqual(
            -1, loop.run_until_complete(utils.run_cmd(("sleep", "6.9"), 0.5)).returncode
        )
        # Show we logged each failure
        self.assertEqual(mock_log.call_count, 2)
