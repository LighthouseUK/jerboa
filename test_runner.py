"""
This file is just a helper for running unittests in PyCharm.
"""

import unittest
from jerboa.tests.test_app import TestCRUDConfigGenerator
from jerboa.tests.test_app import TestComponentConfigParser
from jerboa.tests.test_app import TestUIHandlerHooks
from jerboa.tests.test_app import TestFormHandlerHooks
from jerboa.tests.test_app import TestSearchFormHandlerHooks

__author__ = 'Matt'


class TestApex(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass
