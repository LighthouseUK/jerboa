# TODO: test that config is parsed correctly and that we end up with component and handlers; check names and attributes
# TODO: test that the handlers operate without any receivers being registered; allows fast prototyping
# TODO: test customizing form config
# TODO: test customizing form elements
# TODO: test customizing read/search properties
# TODO: test disabling form fields e.g. csrf in config and uid in form
# TODO: test default csrf config receiver
# TODO: test default recaptcha config receiver
# TODO: test default search results ui receiver
# -*- coding: utf-8 -*-
"""
    jerboa.test_extra
    ~~~~~~~~~~~~~~~~~~


    :copyright: (c) 2015 Lighthouse
    :license: LGPL
"""
import unittest
from google.appengine.ext import testbed
from blinker import signal
from jerboa.extra import crud_handler_definition_generator, StandardFormHandler, SearchHandler

__author__ = 'Matt Badger'


class SignalTester(object):
    """
    signal_tester = SignalTester()

    signal.connect(signal_tester.hook_subscriber, sender=SENDER)

    Do code execution
    ...

    self.assertEquals(len(signal_tester.hook_activations[SENDER]), 1, u'Get should trigger 1 hook')

    """
    def __init__(self):
        self.hook_activations = {}
        self.filter_activations = {}

    def hook_subscriber(self, sender, **kwargs):
        self.hook_activations[sender] = kwargs


user_crud_handlers = crud_handler_definition_generator(component_name='user',
                                                       route_customizations={
                                                           'read': {
                                                               'route_name': 'profile',
                                                               'route_title': 'User Account',
                                                               'page_template': 'extra/read.html'
                                                           },
                                                           'update': {
                                                               'route_title': 'Edit User Account',
                                                               'page_template': 'extra/update.html'
                                                           },
                                                       })

test_handler_config = {
    'user': {
        'title': 'User',
        'handler_definitions': [
            {
                'type': SearchHandler,
                'config': {
                    'component_name': 'user',
                    'handler_code_name': 'search',
                },
                'route_customizations': {
                    'search': {
                        'page_template': 'extra/search.html'
                    },
                },
            },
        ] + user_crud_handlers
    }
}


class TestCRUDConfigGenerator(unittest.TestCase):
    def setUp(self):
        # First, create an instance of the Testbed class.
        self.testbed = testbed.Testbed()
        # Then activate the testbed, which prepares the service stubs for use.
        self.testbed.activate()
        # Next, declare which service stubs you want to use.
        # self.testbed.init_datastore_v3_stub()
        # self.testbed.init_memcache_stub()
        # self.testbed.init_search_stub()
        # Remaining setup needed for test cases

    def tearDown(self):
        self.testbed.deactivate()

    def test_crud_generator(self):
        # TODO: test that the returned config definition is valid, and that there is one for each of the CRUD operations
        pass


class TestComponentConfigParser(unittest.TestCase):
    def setUp(self):
        # First, create an instance of the Testbed class.
        self.testbed = testbed.Testbed()
        # Then activate the testbed, which prepares the service stubs for use.
        self.testbed.activate()
        # Next, declare which service stubs you want to use.
        # self.testbed.init_datastore_v3_stub()
        # self.testbed.init_memcache_stub()
        # self.testbed.init_search_stub()
        # Remaining setup needed for test cases

    def tearDown(self):
        self.testbed.deactivate()

    def test_config_parser(self):
        # TODO: test that a component is created, handlers are setup, and routes added to the component using the
        # created handlers
        pass
