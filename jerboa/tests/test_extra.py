# TODO: test that config is parsed correctly and that we end up with component and handlers; check names and attributes
# TODO: test that the handlers operate without any receivers being registered; allows fast prototyping
# TODO: test customizing form config + overrides
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
from jerboa.extra import crud_handler_definition_generator, StandardFormHandler, SearchHandler, parse_component_config, AppRegistry

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
                    'ui': {
                        'page_template': 'extra/search.html'
                    },
                },
            },
        ]
    }
}


class TestCRUDConfigGenerator(unittest.TestCase):
    def setUp(self):
        self.testbed = testbed.Testbed()
        self.testbed.activate()

    def tearDown(self):
        self.testbed.deactivate()

    def test_crud_generator(self):
        read_route_config = {
            'ui': {
                'route_title': 'User Account',
                'page_template': 'extra/read.html'
            },
            'action': {
            },

        }
        update_route_config = {
            'ui': {
                'route_title': 'Edit User Account',
                'page_template': 'extra/update.html'
            },
        }
        # TODO: test that the returned config definition is valid, and that there is one for each of the CRUD operations
        user_crud_handlers = crud_handler_definition_generator(component_name='user',
                                                               route_customizations={
                                                                   'read': read_route_config,
                                                                   'update': update_route_config,
                                                               })
        self.assertEqual(len(user_crud_handlers), 4, 'Invalid number of generated handler configurations')
        self.assertEqual(user_crud_handlers[0]['route_customizations'], {}, 'Create route customization not applied')
        self.assertEqual(user_crud_handlers[1]['route_customizations'], read_route_config,
                         'Read route customization not applied')
        self.assertEqual(user_crud_handlers[2]['route_customizations'], update_route_config,
                         'Update route customization not applied')
        self.assertEqual(user_crud_handlers[3]['route_customizations'], {}, 'Delete route customization not applied')

    def test_custom_route_name(self):
        read_route_config = {
            'ui': {
                'route_name': 'profile',
                'route_title': 'User Account',
                'page_template': 'extra/read.html'
            },
            'action': {
                'route_name': 'profile',
            },

        }
        user_crud_handlers = crud_handler_definition_generator(component_name='user',
                                                               route_customizations={
                                                                   'read': read_route_config,
                                                               })
        self.assertEqual(len(user_crud_handlers), 4, 'Invalid number of generated handler configurations')
        self.assertEqual(user_crud_handlers[0]['route_customizations'], {}, 'Create route customization not applied')
        self.assertEqual(user_crud_handlers[1]['route_customizations'], read_route_config,
                         'Read route customization not applied')
        self.assertEqual(user_crud_handlers[2]['route_customizations'], {}, 'Update route customization not applied')
        self.assertEqual(user_crud_handlers[3]['route_customizations'], {}, 'Delete route customization not applied')
        # Check custom route name
        self.assertEqual(user_crud_handlers[1]['config']['route_map']['read.ui'], u'component.user.profile.ui')


class TestComponentConfigParser(unittest.TestCase):
    def setUp(self):
        self.testbed = testbed.Testbed()
        self.testbed.activate()

    def tearDown(self):
        self.testbed.deactivate()

    def test_config_parser(self):
        AppRegistry.reset()
        parse_component_config(component_config=test_handler_config)
        self.assertEqual(len(AppRegistry.components), 1, 'Invalid number of components')
        self.assertEqual(len(AppRegistry.handlers), 1, 'Invalid number of handlers')
        self.assertEqual(len(AppRegistry.components['user'].get_routes()), 1, 'Invalid number of component routes')

    def test_config_parser_with_crud_generator_output(self):
        AppRegistry.reset()
        read_route_config = {
            'ui': {
                'route_name': 'profile',
                'route_title': 'User Account',
                'page_template': 'extra/read.html'
            },
            'action': {
                'route_name': 'profile',
            },

        }
        user_crud_handlers = crud_handler_definition_generator(component_name='user',
                                                               route_customizations={
                                                                   'read': read_route_config,
                                                               })
        crud_handler_config = {
            'user': {
                'title': 'User',
                'handler_definitions': user_crud_handlers
            }
        }

        parse_component_config(component_config=crud_handler_config)
        self.assertEqual(len(AppRegistry.components), 1, 'Invalid number of components')
        self.assertEqual(len(AppRegistry.handlers), 4, 'Invalid number of handlers')
        self.assertEqual(len(AppRegistry.components['user'].raw_routes_prefix), 7, 'Invalid number of component routes')
