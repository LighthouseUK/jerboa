# test that config is parsed correctly and that we end up with component and handlers; check names and attributes
# TODO: test that the handlers operate without any receivers being registered; allows fast prototyping (must check with connected hook that triggers the page render)
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
import webapp2
from webapp2 import Route
from webapp2_extras.routes import MultiRoute
from blinker import signal
from jerboa.exceptions import FormDuplicateValue, UIFailed, CallbackFailed
from jerboa.renderers import retrofit_response
from jerboa.dispatcher import custom_dispatcher, custom_adapter, CUSTOM_DISPATCHER_PRE_PROCESS_RESPONSE_HOOK
from jerboa.extra import crud_handler_definition_generator, StandardFormHandler, SearchHandler, parse_component_config, AppRegistry, StandardUIHandler

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

    def hook_subscriber(self, sender, hook_name='undefined', **kwargs):
        try:
            self.hook_activations[sender]
        except KeyError:
            self.hook_activations[sender] = {}
        try:
            self.hook_activations[sender][hook_name] += 1
        except KeyError:
            self.hook_activations[sender][hook_name] = 1


test_handler_config = {
    'home': {
        'title': 'Home',
        'handler_definitions': [
            {
                'type': StandardUIHandler,
                'config': {
                    'component_name': 'home',
                    'handler_code_name': 'dashboard',
                },
            },
        ]
    },
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


def add_routes(app_instance, route_list):
    for item in route_list:
        if isinstance(item, (Route, MultiRoute)):
            app_instance.router.add(item)
        else:
            add_routes(app_instance=app_instance, route_list=item)


class TestUIHandlerHooks(unittest.TestCase):
    def setUp(self):
        AppRegistry.reset()
        parse_component_config(component_config=test_handler_config)

        routes = [component.get_routes() for component_name, component in AppRegistry.components.iteritems()]

        app = webapp2.WSGIApplication(debug=True)
        app.router.set_dispatcher(custom_dispatcher)
        app.router.set_adapter(custom_adapter)

        add_routes(app_instance=app, route_list=routes)
        self.app = app

        self.testbed = testbed.Testbed()
        self.testbed.activate()

    def tearDown(self):
        self.testbed.deactivate()

    def test_ui(self):
        handler = AppRegistry.handlers['home_dashboard']
        signal_tester = SignalTester()
        # Subscribe to signals
        handler.ui_hook.connect(signal_tester.hook_subscriber, sender=handler)

        request = webapp2.Request.blank('/home/dashboard')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 200)
        self.assertEquals(len(signal_tester.hook_activations[handler]), 1, u'Handler should trigger 1 hook(s)')
        self.assertEquals(signal_tester.hook_activations[handler]['ui'], 1, u'Handler should trigger `ui` hook 1 time(s)')

    def test_ui_failure(self):
        handler = AppRegistry.handlers['home_dashboard']
        signal_tester = SignalTester()
        handler.ui_failed_hook.connect(signal_tester.hook_subscriber, sender=handler)

        # In order to test this hook we need to raise an exception. To do that we need to connect to the ui hook
        def raise_ui_failed_exception(sender, **kwargs):
            raise UIFailed('Testing ui failed exception hook')

        handler.ui_hook.connect(raise_ui_failed_exception, sender=handler)

        request = webapp2.Request.blank('/home/dashboard')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 302)   # The exception should trigger a redirect
        self.assertEquals(signal_tester.hook_activations[handler]['ui_failed'], 1,
                          u'Handler should trigger `ui_failed` hook 1 time(s)')


class TestFormHandlerHooks(unittest.TestCase):
    def setUp(self):
        AppRegistry.reset()
        user_crud_handlers = crud_handler_definition_generator(component_name='user')
        crud_handler_config = {
            'user': {
                'title': 'User',
                'handler_definitions': user_crud_handlers
            }
        }
        parse_component_config(component_config=crud_handler_config)

        routes = [component.get_routes() for component_name, component in AppRegistry.components.iteritems()]

        app = webapp2.WSGIApplication(debug=True)
        app.router.set_dispatcher(custom_dispatcher)
        app.router.set_adapter(custom_adapter)
        CUSTOM_DISPATCHER_PRE_PROCESS_RESPONSE_HOOK.connect(retrofit_response, sender=app.router)

        add_routes(app_instance=app, route_list=routes)
        self.app = app

        self.testbed = testbed.Testbed()
        self.testbed.activate()

    def tearDown(self):
        self.testbed.deactivate()

    def test_form_ui(self):
        handler = AppRegistry.handlers['user_create']
        signal_tester = SignalTester()
        handler.ui_hook.connect(signal_tester.hook_subscriber, sender=handler)

        request = webapp2.Request.blank('/user/create')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 200)
        self.assertEquals(len(signal_tester.hook_activations[handler]), 1, u'Handler should trigger 1 hook(s)')
        self.assertEquals(signal_tester.hook_activations[handler]['ui'], 1,
                          u'Handler should trigger `ui` hook 1 time(s)')

    def test_form_config(self):
        handler = AppRegistry.handlers['user_create']
        signal_tester = SignalTester()
        handler.form_config_hook.connect(signal_tester.hook_subscriber, sender=handler)

        request = webapp2.Request.blank('/user/create')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 200)
        self.assertEquals(len(signal_tester.hook_activations[handler]), 1, u'Handler should trigger 1 hook(s)')
        self.assertEquals(signal_tester.hook_activations[handler]['form_config'], 1,
                          u'Handler should trigger `form_config` hook 1 time(s)')

    def test_form_customization(self):
        handler = AppRegistry.handlers['user_create']
        signal_tester = SignalTester()
        handler.customize_form_hook.connect(signal_tester.hook_subscriber, sender=handler)

        request = webapp2.Request.blank('/user/create')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 200)
        self.assertEquals(len(signal_tester.hook_activations[handler]), 1, u'Handler should trigger 1 hook(s)')
        self.assertEquals(signal_tester.hook_activations[handler]['customize_form'], 1,
                          u'Handler should trigger `customize_form` hook 1 time(s)')

    def test_form_valid(self):
        handler = AppRegistry.handlers['user_create']
        signal_tester = SignalTester()
        # Subscribe to signals
        handler.valid_form_hook.connect(signal_tester.hook_subscriber, sender=handler)

        request = webapp2.Request.blank('/user/create/callback', POST={'required_input': 'Test Input'})
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 302)
        self.assertEquals(len(signal_tester.hook_activations[handler]), 1, u'Handler should trigger 1 hook(s)')
        self.assertEquals(signal_tester.hook_activations[handler]['valid_form'], 1,
                          u'Handler should trigger `valid_form` hook 1 time(s)')

    def test_form_error(self):
        handler = AppRegistry.handlers['user_create']
        signal_tester = SignalTester()
        handler.form_error_hook.connect(signal_tester.hook_subscriber, sender=handler)

        request = webapp2.Request.blank('/user/create/callback')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 302)
        self.assertEquals(len(signal_tester.hook_activations[handler]), 1, u'Handler should trigger 1 hook(s)')
        self.assertEquals(signal_tester.hook_activations[handler]['form_error'], 1,
                          u'Handler should trigger `form_error` hook 1 time(s)')

    def test_form_duplicate_values(self):
        handler = AppRegistry.handlers['user_create']
        signal_tester = SignalTester()
        handler.duplicate_value_hook.connect(signal_tester.hook_subscriber, sender=handler)

        # In order to test this hook we need to raise an exception. To do that we need to connect to the valid_form hook
        def raise_duplicate_value_exception(sender, **kwargs):
            raise FormDuplicateValue('Testing duplicate value exception hook')
        handler.valid_form_hook.connect(raise_duplicate_value_exception, sender=handler)

        request = webapp2.Request.blank('/user/create/callback', POST={'required_input': 'Test Input'})
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 302)
        self.assertEquals(signal_tester.hook_activations[handler]['duplicate_value'], 1,
                          u'Handler should trigger `duplicate_value` hook 1 time(s)')

    def test_form_callback_failure(self):
        handler = AppRegistry.handlers['user_create']
        signal_tester = SignalTester()
        handler.callback_failed_hook.connect(signal_tester.hook_subscriber, sender=handler)

        # In order to test this hook we need to raise an exception. To do that we need to connect to the valid_form hook
        def raise_callback_failed_exception(sender, **kwargs):
            raise CallbackFailed('Testing callback failed exception hook')

        handler.valid_form_hook.connect(raise_callback_failed_exception, sender=handler)

        request = webapp2.Request.blank('/user/create/callback', POST={'required_input': 'Test Input'})
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 302)
        self.assertEquals(signal_tester.hook_activations[handler]['callback_failed'], 1,
                          u'Handler should trigger `callback_failed` hook 1 time(s)')

    def test_form_ui_failure(self):
        handler = AppRegistry.handlers['user_create']
        signal_tester = SignalTester()
        handler.ui_failed_hook.connect(signal_tester.hook_subscriber, sender=handler)

        # In order to test this hook we need to raise an exception. To do that we need to connect to the ui hook
        def raise_ui_failed_exception(sender, **kwargs):
            raise UIFailed('Testing ui failed exception hook')

        handler.ui_hook.connect(raise_ui_failed_exception, sender=handler)

        request = webapp2.Request.blank('/user/create')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 302)
        self.assertEquals(signal_tester.hook_activations[handler]['ui_failed'], 1,
                          u'Handler should trigger `ui_failed` hook 1 time(s)')


class TestSearchFormHandlerHooks(unittest.TestCase):
    def setUp(self):
        AppRegistry.reset()
        parse_component_config(component_config=test_handler_config)

        routes = [component.get_routes() for component_name, component in AppRegistry.components.iteritems()]

        app = webapp2.WSGIApplication(debug=True)
        app.router.set_dispatcher(custom_dispatcher)
        app.router.set_adapter(custom_adapter)
        CUSTOM_DISPATCHER_PRE_PROCESS_RESPONSE_HOOK.connect(retrofit_response, sender=app.router)

        add_routes(app_instance=app, route_list=routes)
        self.app = app

        self.testbed = testbed.Testbed()
        self.testbed.activate()

    def tearDown(self):
        self.testbed.deactivate()

    def test_form_ui(self):
        handler = AppRegistry.handlers['user_search']
        signal_tester = SignalTester()
        handler.ui_hook.connect(signal_tester.hook_subscriber, sender=handler)

        request = webapp2.Request.blank('/user/search')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 200)
        self.assertEquals(len(signal_tester.hook_activations[handler]), 1, u'Handler should trigger 1 hook(s)')
        self.assertEquals(signal_tester.hook_activations[handler]['ui'], 1,
                          u'Handler should trigger `ui` hook 1 time(s)')

    def test_form_config(self):
        handler = AppRegistry.handlers['user_search']
        signal_tester = SignalTester()
        handler.form_config_hook.connect(signal_tester.hook_subscriber, sender=handler)

        request = webapp2.Request.blank('/user/search')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 200)
        self.assertEquals(len(signal_tester.hook_activations[handler]), 1, u'Handler should trigger 1 hook(s)')
        self.assertEquals(signal_tester.hook_activations[handler]['form_config'], 1,
                          u'Handler should trigger `form_config` hook 1 time(s)')

    def test_form_customization(self):
        handler = AppRegistry.handlers['user_search']
        signal_tester = SignalTester()
        handler.customize_form_hook.connect(signal_tester.hook_subscriber, sender=handler)

        request = webapp2.Request.blank('/user/search')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 200)
        self.assertEquals(len(signal_tester.hook_activations[handler]), 1, u'Handler should trigger 1 hook(s)')
        self.assertEquals(signal_tester.hook_activations[handler]['customize_form'], 1,
                          u'Handler should trigger `customize_form` hook 1 time(s)')

    def test_form_valid(self):
        handler = AppRegistry.handlers['user_search']
        signal_tester = SignalTester()
        # Subscribe to signals
        handler.valid_form_hook.connect(signal_tester.hook_subscriber, sender=handler)

        request = webapp2.Request.blank('/user/search?query=test')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 302)
        self.assertEquals(len(signal_tester.hook_activations[handler]), 1, u'Handler should trigger 1 hook(s)')
        self.assertEquals(signal_tester.hook_activations[handler]['valid_form'], 1,
                          u'Handler should trigger `valid_form` hook 1 time(s)')

    def test_form_error(self):
        handler = AppRegistry.handlers['user_search']
        signal_tester = SignalTester()
        handler.form_error_hook.connect(signal_tester.hook_subscriber, sender=handler)

        request = webapp2.Request.blank('/user/search')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 302)
        self.assertEquals(len(signal_tester.hook_activations[handler]), 1, u'Handler should trigger 1 hook(s)')
        self.assertEquals(signal_tester.hook_activations[handler]['form_error'], 1,
                          u'Handler should trigger `form_error` hook 1 time(s)')

    def test_form_callback_failure(self):
        handler = AppRegistry.handlers['user_search']
        signal_tester = SignalTester()
        handler.callback_failed_hook.connect(signal_tester.hook_subscriber, sender=handler)

        # In order to test this hook we need to raise an exception. To do that we need to connect to the valid_form hook
        def raise_callback_failed_exception(sender, **kwargs):
            raise CallbackFailed('Testing callback failed exception hook')

        handler.valid_form_hook.connect(raise_callback_failed_exception, sender=handler)

        request = webapp2.Request.blank('/user/search?query=test')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 302)
        self.assertEquals(signal_tester.hook_activations[handler]['callback_failed'], 1,
                          u'Handler should trigger `callback_failed` hook 1 time(s)')

    def test_form_ui_failure(self):
        handler = AppRegistry.handlers['user_search']
        signal_tester = SignalTester()
        handler.ui_failed_hook.connect(signal_tester.hook_subscriber, sender=handler)

        # In order to test this hook we need to raise an exception. To do that we need to connect to the ui hook
        def raise_ui_failed_exception(sender, **kwargs):
            raise UIFailed('Testing ui failed exception hook')

        handler.ui_hook.connect(raise_ui_failed_exception, sender=handler)

        request = webapp2.Request.blank('/user/search')
        response = request.get_response(self.app)

        self.assertEqual(response.status_int, 302)
        self.assertEquals(signal_tester.hook_activations[handler]['ui_failed'], 1,
                          u'Handler should trigger `ui_failed` hook 1 time(s)')
