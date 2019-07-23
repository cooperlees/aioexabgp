#!/usr/bin/env python3.7

import unittest


from aioexabgp.tests.announcer_tests import AnnouncerTests  # noqa: F401
from aioexabgp.tests.fibs_tests import FibsTests  # noqa: F401
from aioexabgp.tests.exabgpparser_tests import ExabgpParserTests  # noqa: F401
from aioexabgp.tests.pipes_tests import ExaBGPPipesTests  # noqa: F401
from aioexabgp.tests.utils_tests import UtilsTests  # noqa: F401


if __name__ == "__main__":
    unittest.main()
