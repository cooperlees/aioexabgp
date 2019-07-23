#!/usr/bin/env python3.7

import unittest

from aioexabgp.announcer.fibs import Fib, get_fib


class FibsTests(unittest.TestCase):
    def test_get_fib(self) -> None:
        bs_config = {"learn": {}}
        lf = get_fib("Linux", bs_config)
        self.assertTrue(isinstance(lf, Fib))

        with self.assertRaises(ValueError):
            get_fib("JunOS", bs_config)


if __name__ == "__main__":
    unittest.main()
