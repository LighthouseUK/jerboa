import os
from blinker import signal
from beaker.middleware import SessionMiddleware
import webapp2
from .config import NoSectionError, NoOptionError, load_config
from .renderers import Jinja2Renderer
from .app import JerboaApp, CUSTOM_DISPATCHER_REQUEST_INIT_HOOK, CUSTOM_DISPATCHER_RESPONSE_INIT_HOOK, CUSTOM_DISPATCHER_POST_PROCESS_RESPONSE_HOOK, RENDERER_CONFIG_HOOK


def request_init(sender, request, app_instance):
    request.settings = app_instance.app_settings
    request.session = request.environ['beaker.session']
    # We could set request.namespace here, if needed. This can be pulled from the config object or you could
    # set it based on the current user. Note that we do the user loading in the 'pre_request_dispatch' function
    # because we need to set the namespace before invoking any API methods.


def response_init(sender, response, app_instance):
    response.default_renderer = app_instance.app_registry.renderers['default']


def post_request_hook(sender, request, response, **kwargs):
    request.environ['beaker.session'].save()


def default_post_request_hook(sender, request, response, app_instance):
    if request.method == 'GET' and response.status_int == 200:
        response.default_renderer.render(template_name=request.route.method_config['page_template'], response=response)


# This is a useful little handler that allows you to place breakpoints for debugging form errors.
def form_debug(handler, request, response, form_instance, hook_name):
    pass


class SettingsSupportedApp(JerboaApp):
    """
    Suggested config_file_path: os.path.join(os.path.dirname(__file__), 'config.ini')

    """
    def __init__(self, config_file_path, **kwargs):
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

        self.app_settings = load_config(config_file_path=config_file_path, platform=platform)

        default_renderer_config = {
            'type': Jinja2Renderer,
            'environment_args': {},
            'global_vars': {
                'version': os.environ['CURRENT_VERSION_ID'],
            },
        }

        if bool(RENDERER_CONFIG_HOOK.receivers):
            RENDERER_CONFIG_HOOK.send(self, renderer_config=default_renderer_config, settings=self.app_settings)

        renderer_type = default_renderer_config['type']
        del default_renderer_config['type']

        kwargs['default_renderer'] = renderer_type(config=default_renderer_config)

        # We need to setup the config parser before calling init on super; some receivers may depend on app_settings
        # being available
        super(SettingsSupportedApp, self).__init__(**kwargs)


def default_renderer_config_loader(sender, renderer_config, settings):
    try:
        renderer_config['environment_args']['extensions'] = settings.getlist('jinja2_extensions')
    except (NoSectionError, NoOptionError):
        renderer_config['environment_args']['extensions'] = 'jinja2.ext.autoescape,jinja2.ext.with_,jinja2.ext.i18n,jinja2.ext.do'

    try:
        renderer_config['environment_args']['autoescape'] = settings.getboolean('jinja2_env_autoescape')
    except (NoSectionError, NoOptionError):
        renderer_config['environment_args']['autoescape'] = False

    try:
        renderer_config['enable_i18n'] = settings.getboolean('jinja2_enable_i18n')
    except (NoSectionError, NoOptionError):
        renderer_config['enable_i18n'] = False

    try:
        renderer_config['theme_base_template_path'] = settings.getlist('theme_base_template_path')
    except (NoSectionError, NoOptionError):
        pass

    try:
        renderer_config['global_vars']['theme'] = settings.get('theme')
    except (NoSectionError, NoOptionError):
        pass

    try:
        renderer_config['global_vars']['base_url'] = settings.get('theme_url')
    except (NoSectionError, NoOptionError):
        pass

    try:
        renderer_config['global_vars']['css_url'] = settings.get('theme_css_url')
    except (NoSectionError, NoOptionError):
        pass

    try:
        renderer_config['global_vars']['js_url'] = settings.get('theme_js_url')
    except (NoSectionError, NoOptionError):
        pass

    try:
        renderer_config['global_vars']['common_assets_url'] = settings.get('theme_common_assets_url')
    except (NoSectionError, NoOptionError):
        pass

    try:
        renderer_config['global_vars']['css_ext'] = settings.get('css_ext')
    except (NoSectionError, NoOptionError):
        renderer_config['global_vars']['css_ext'] = '.css'

    try:
        renderer_config['global_vars']['js_ext'] = settings.get('js_ext')
    except (NoSectionError, NoOptionError):
        renderer_config['global_vars']['js_ext'] = '.js'

    try:
        renderer_config['global_vars']['main_css'] = settings.get('theme_main_css_url')
    except (NoSectionError, NoOptionError):
        renderer_config['global_vars']['main_css'] = 'app'

    try:
        renderer_config['global_vars']['base_layout'] = settings.get('theme_base_layout')
    except (NoSectionError, NoOptionError):
        renderer_config['global_vars']['base_layout'] = 'base.html'

    try:
        renderer_config['global_vars']['home_route'] = settings.get('home_route')
    except (NoSectionError, NoOptionError):
        renderer_config['global_vars']['home_route'] = 'default'

    if 'app_info' not in renderer_config['global_vars']:
        renderer_config['global_vars']['app_info'] = {}

    try:
        renderer_config['global_vars']['app_info']['app_name'] = settings.get('app_name')
    except (NoSectionError, NoOptionError):
        pass

    try:
        renderer_config['global_vars']['app_info']['title'] = settings.get('title')
    except (NoSectionError, NoOptionError):
        pass

    renderer_config['global_vars']['uri_for'] = webapp2.uri_for


class DefaultApp(SettingsSupportedApp):
    """
    Automatically connects to some default handlers to avoid boilerplate code

    """
    def __init__(self, **kwargs):
        RENDERER_CONFIG_HOOK.connect(default_renderer_config_loader, sender=self)

        super(DefaultApp, self).__init__(**kwargs)

        CUSTOM_DISPATCHER_REQUEST_INIT_HOOK.connect(request_init, sender=self.router)
        CUSTOM_DISPATCHER_RESPONSE_INIT_HOOK.connect(response_init, sender=self.router)
        CUSTOM_DISPATCHER_POST_PROCESS_RESPONSE_HOOK.connect(default_post_request_hook, sender=self.router)


class FoundationApp(SessionMiddleware):
    """
    FoundationApp builds upon JerboaApp to add in session management and config file parsing.

    """
    def __init__(self, config_file_path, resource_config, default_login=True, add_default_route=True, debug=None, webapp2_config=None, **kwargs):
        app = DefaultApp(config_file_path=config_file_path, resource_config=resource_config, default_login=default_login, add_default_route=add_default_route, debug=debug, webapp2_config=webapp2_config)

        session_opts = {
            'session.type': app.app_settings.get('session_type'),
            'session.cookie_expires': app.app_settings.getint('session_expires'),
            'session.encrypt_key': app.app_settings.get('session_encryption_key'),
            'session.validate_key': app.app_settings.get('session_validate_key'),
            'session.secure': False if os.environ['SERVER_NAME'] in ['localhost', '127.0.0.1'] else True,
            'session.httponly': True,
        }

        super(FoundationApp, self).__init__(wrap_app=app, config=session_opts, **kwargs)