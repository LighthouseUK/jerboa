import os
import codecs
from blinker import signal
from .config import CustomConfigParser
from beaker.middleware import SessionMiddleware
from .app import JerboaApp, CUSTOM_DISPATCHER_REQUEST_INIT_HOOK, CUSTOM_DISPATCHER_POST_PROCESS_RESPONSE_HOOK


def request_init(sender, request, app_instance):
    request.settings = app_instance.app_settings
    request.session = request.environ['beaker.session']
    # We could set request.namespace here, if needed. This can be pulled from the config object or you could
    # set it based on the current user. Note that we do the user loading in the 'pre_request_dispatch' function
    # because we need to set the namespace before invoking any API methods.


def post_request_hook(sender, request, response, **kwargs):
    request.environ['beaker.session'].save()


def default_post_request_hook(sender, request, response, app_instance):
    if request.method == 'GET' and response.status_int == 200:
        app_instance.app_registry.renderers['default'].render(template_name=request.route.method_config['page_template'], response=response)


# This is a useful little handler that allows you to place breakpoints for debugging form errors.
def form_debug(handler, request, response, form_instance, hook_name):
    pass


class SettingsSupportedApp(JerboaApp):
    """
    Suggested config_file_path: os.path.join(os.path.dirname(__file__), 'config.ini')

    """
    def __init__(self, config_file_path, **kwargs):
        super(SettingsSupportedApp, self).__init__(**kwargs)
        try:
            if os.environ['SERVER_SOFTWARE'].startswith('Google'):
                platform = 'Production'
            elif os.environ['SERVER_NAME'] in ['localhost', '127.0.0.1']:
                platform = 'Development'
            elif os.environ['SERVER_NAME'] == 'testbed.example.com':
                platform = 'Testing'
            else:
                platform = 'Testing'
        except KeyError:
            platform = 'Testing'

        if self.debug:
            signal('form_error').connect(form_debug)

        settings = CustomConfigParser(platform=platform, allow_no_value=True)

        with codecs.open(config_file_path, 'r', encoding='utf-8') as f:
            settings.readfp(f)
        settings.read([os.path.join(os.path.dirname(__file__), found_file) for found_file in os.listdir(os.path.dirname(__file__)) if found_file.endswith('.ini')])

        self.app_settings = settings

        CUSTOM_DISPATCHER_REQUEST_INIT_HOOK.connect(request_init, sender=self.router)
        CUSTOM_DISPATCHER_POST_PROCESS_RESPONSE_HOOK.connect(default_post_request_hook, sender=self.router)


class FoundationApp(SessionMiddleware):
    """
    FoundationApp builds upon JerboaApp to add in session management and config file parsing.

    """
    def __init__(self, config_file_path, resource_config, renderer_config=None, default_login=True, add_default_route=True, debug=None, webapp2_config=None, **kwargs):
        app = SettingsSupportedApp(config_file_path=config_file_path, resource_config=resource_config, renderer_config=renderer_config, default_login=default_login, add_default_route=add_default_route, debug=debug, webapp2_config=webapp2_config)

        session_opts = {
            'session.type': app.app_settings.get('session_type'),
            'session.cookie_expires': app.app_settings.getint('session_expires'),
            'session.encrypt_key': app.app_settings.get('session_encryption_key'),
            'session.validate_key': app.app_settings.get('session_validate_key'),
            'session.secure': False if os.environ['SERVER_NAME'] in ['localhost', '127.0.0.1'] else True,
            'session.httponly': True,
        }

        super(FoundationApp, self).__init__(wrap_app=app, **kwargs)