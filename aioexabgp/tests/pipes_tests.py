#!/usr/bin/env python3

import os
import unittest
from asyncio import get_event_loop, TimeoutError
from pathlib import Path
from tempfile import gettempdir
from time import sleep
from unittest.mock import patch

from aioexabgp import pipes


def sleep_1_second(*args, **kwargs) -> None:
    sleep(1)


class ExaBGPPipesTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp_dir = Path(gettempdir())
        self.in_pipe = tmp_dir / f"test_in_pipe.{os.getpid()}"
        self.out_pipe = tmp_dir / f"test_out_pipe.{os.getpid()}"
        self._make_pipes()
        self.exabgppipes = pipes.ExaBGPPipes(self.in_pipe, self.out_pipe)
        self.loop = get_event_loop()

    def tearDown(self) -> None:
        for a_pipe in (self.in_pipe, self.out_pipe):
            try:
                a_pipe.unlink()
            except IOError:  # pragma: nocover
                pass  # pragma: nocover

    def _make_pipes(self) -> None:
        for a_pipe in (self.in_pipe, self.out_pipe):
            if not a_pipe.exists():
                os.mkfifo(a_pipe, 0o600)

    def test_check_pipe(self) -> None:
        self.assertTrue(self.loop.run_until_complete(self.exabgppipes.check_pipes()))

    @patch("aioexabgp.pipes.ExaBGPPipes._write", sleep_1_second)
    def test_write_timeout(self) -> None:
        with self.assertRaises(TimeoutError):
            self.loop.run_until_complete(self.exabgppipes.write("s", timeout=0.5))
