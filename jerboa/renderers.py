import types
import webapp2
import logging
import jinja2
from blinker import signal

__author__ = 'Matt'


ADD_RESPONSE_VARS_HOOK = signal('add_response_vars_hook')

JINJA2_ENGINE_CONFIG_KEY = 'jinja2_engine_config'
SIMPLE_ENGINE_CONFIG_KEY = 'simple_engine_config'
GLOBAL_TEMPLATE_VARS_KEY = 'global_renderer_vars'


CONTENT_TYPE_HEADERS = {
    'text/html': {
        'X-UA-Compatible': 'IE=Edge,chrome=1',
    },
    'txt': {
        'Content-Type': 'text/plain',
    },
    'xml': {
        'Content-Type': 'application/xml',
    }
}


class ScratchSpace(object):
    """
        Scratch space for handlers to output data to. This data will be used by the template engine.

        Use case in a Response Class:
            response.raw.var1 = "hello"
            response.raw.array = [1, 2, 3]
            response.raw.dict = dict(a="abc", b="bcd")

        Can be accessed in the template by just using the variables like {{var1}} or {{dict.b}}
    """
    pass


class Renderer(object):
    template_name = None
    template_engine = None
    raw = None

    def __init__(self, template_engine=None, template_name=None):
        self.raw = ScratchSpace()
        self.template_name = template_name
        self.template_engine = template_engine

    def __unicode__(self):
        return self.__str__()

    def __str__(self):
        text_version = self.render()
        return unicode(text_version).encode(encoding='utf-8')

    def __getattr__(self, name):
        if name not in ("template_name", "template_engine", "render", "raw"):
            return getattr(self.raw, name, None)
        else:
            raise AttributeError

    def __setattr__(self, name, value):
        if name in ("template_name", "template_engine", "raw"):
            object.__setattr__(self, name, value)
        else:
            self.raw.__setattr__(name, value)

    def render(self):
        if not self.template_engine and not self.template_name or not self.template_name:
            return unicode(str(self.raw.__dict__))

        params = {}

        if hasattr(self, 'raw') and self.raw:
            params = self.raw.__dict__

        return self.template_engine.render_template(self.template_name, **params)


def response_render_function(self):
    """
    This function gets bound to response objects and renders the scratch space data as configured by the route def.

    """
    if not self.body:
        # self.clear()
        self.write(self.raw.__str__())

    if self.content_type:
        headers = CONTENT_TYPE_HEADERS.get(self.content_type, None)
        for header in headers:
            self.headers.add_header(header[0], header[1])


def retrofit_response(sender, request, response):
    """
    Designed to be used via a blinker signal, hence the 'sender' arg. Assigns the necessary attributes to the response
    object to support the renderers defined in this module.

    :param sender:
    :param request:
    :param response:
    :return:
    """
    postprocessing_engine = None
    postprocessing_template = None

    try:
        desired_engine = request.route.template_engine
    except AttributeError:
        logging.debug(u'No template_engine specified for route')
    else:
        try:
            engine_loader = template_engine_map.get(desired_engine)
        except KeyError:
            logging.debug(u'"{}" is not a valid template engine'.format(desired_engine))
        else:
            postprocessing_engine = engine_loader()

    try:
        postprocessing_template = request.route.page_template
    except AttributeError:
        logging.debug(u'No page_template specified for template engine')

    response.raw = Renderer(template_engine=postprocessing_engine, template_name=postprocessing_template)

    ADD_RESPONSE_VARS_HOOK.send(sender, request=request, response=response)

    try:
        response.render = types.MethodType(response_render_function, response)
        # This is done because the render method needs to access 'self' in order to work correctly. The types.MethodType
        # function binds the render function to the response object.
    except Exception:
        logging.error(u'Failed to add render() method to response instance.')

    try:
        response.content_type = request.route.content_type
    except AttributeError:
        logging.debug(u'No content_type specified for route')


class SimpleTemplateEngine(object):
    template_path = None
    global_template_variables = {}

    def __init__(self, engine_config=None):
        self.template_path = engine_config['theme_base_template_path']

    @staticmethod
    def parse_simple_template(template, params=None):
        params.pop("request", None)

        def set_variables(text, key):
            return text.replace("{{ %s }}" % key, str(params[key]))
        return reduce(set_variables, params, template) if params else template

    def simple_template_path(self, template_name):
        import os
        return os.path.join(self.template_path, template_name)

    def render_template(self, template_name, relative=True, *args, **kwargs):
        if relative:
            # this is where we would build the theme template path instead of an absolute one
            template_path = self.simple_template_path(template_name=template_name)
        else:
            template_path = template_name
        return self.parse_simple_template(open(template_path).read(), params=kwargs)


def simple_template_engine_factory(engine_config, global_vars):
    s = SimpleTemplateEngine(engine_config=engine_config)
    s.global_template_variables.update(global_vars)
    return s


def simple_template_engine_loader(engine_config=None, global_vars=None):
    registry_key = 'template_engine.simple'

    try:
        webapp2_instance = webapp2.get_app()
    except AssertionError:
        logging.debug('No webapp2 global set; skipping registry lookup for simple template engine.')

        if not engine_config:
            engine_config = {}
        if not global_vars:
            global_vars = {}

        simple_instance = simple_template_engine_factory(engine_config=engine_config, global_vars=global_vars)
    else:
        simple_instance = webapp2_instance.registry.get(registry_key)
        if not simple_instance:
            # Try to load engine config from webapp2 before defaulting to empty dict
            if not engine_config:
                engine_config = webapp2_instance.config.get(SIMPLE_ENGINE_CONFIG_KEY) or {}
            if not global_vars:
                global_vars = webapp2_instance.config.get(GLOBAL_TEMPLATE_VARS_KEY) or {}

            simple_instance = webapp2_instance.registry[registry_key] = simple_template_engine_factory(
                engine_config=engine_config, global_vars=global_vars)

    return simple_instance


class Jinja2TemplateEngine(object):
    """Wrapper for Jinja2 environment. Based on webapp2_extras.jinja2
    """

    config = None

    def __init__(self, engine_config, global_vars=None, filters=None, tests=None):
        """Initializes the Jinja2 object.
        """

        self.global_template_variables = global_vars

        env_config = engine_config['environment_args'].copy()
        env_config['loader'] = jinja2.FileSystemLoader(engine_config['theme_base_template_path'])

        # Initialize the environment.
        env = jinja2.Environment(**env_config)

        if global_vars:
            env.globals.update(global_vars)

        if filters:
            env.filters.update(filters)

        if engine_config['enable_i18n']:
            # Install i18n.
            from webapp2_extras import i18n
            env.install_gettext_callables(
                lambda x: i18n.gettext(x),
                lambda s, p, n: i18n.ngettext(s, p, n),
                newstyle=True)
            env.filters.update({
                'format_date':      i18n.format_date,
                'format_time':      i18n.format_time,
                'format_datetime':  i18n.format_datetime,
                'format_timedelta': i18n.format_timedelta,
            })

        self.environment = env

    def render_template(self, _filename, **context):
        """Renders a template and returns a response object.

        :param _filename:
            The template filename, related to the templates directory.
        :param context:
            Keyword arguments used as variables in the rendered template.
            These will override values set in the request context.
        :returns:
            A rendered template.
        """
        return self.environment.get_template(_filename).render(**context)

    def get_template_attribute(self, filename, attribute):
        """Loads a macro (or variable) a template exports.  This can be used to
        invoke a macro from within Python code.  If you for example have a
        template named `_foo.html` with the following contents:

        .. sourcecode:: html+jinja

           {% macro hello(name) %}Hello {{ name }}!{% endmacro %}

        You can access this from Python code like this::

            hello = get_template_attribute('_foo.html', 'hello')
            return hello('World')

        This function comes from `Flask`.

        :param filename:
            The template filename.
        :param attribute:
            The name of the variable of macro to acccess.
        """
        template = self.environment.get_template(filename)
        return getattr(template.module, attribute)


# TODO refactor the initialisation of jinja2 to not use the webapp2.extras module
def jinja2_template_engine_factory(engine_config, global_vars):
    j = Jinja2TemplateEngine(engine_config=engine_config)
    j.environment.filters.update({
        # Set filters.
        # ...
    })
    j.environment.globals.update({'uri_for': webapp2.uri_for, 'getattr': getattr})
    j.environment.globals.update(global_vars)
    j.environment.tests.update({
        # Set test.
        # ...
    })
    return j


def jinja2_template_engine_loader(engine_config=None, global_vars=None):
    registry_key = 'template_engine.jinja2'

    try:
        webapp2_instance = webapp2.get_app()
    except AssertionError:
        logging.debug('No webapp2 global set; skipping registry lookup for jinja2 template engine.')

        if not engine_config:
            engine_config = {}
        if not global_vars:
            global_vars = {}

        jinja2_instance = jinja2_template_engine_factory(engine_config=engine_config, global_vars=global_vars)
    else:
        jinja2_instance = webapp2_instance.registry.get(registry_key)
        if not jinja2_instance:
            # Try to load engine config from webapp2 before defaulting to empty dict
            if not engine_config:
                engine_config = webapp2_instance.config.get(JINJA2_ENGINE_CONFIG_KEY) or {}
            if not global_vars:
                global_vars = webapp2_instance.config.get(GLOBAL_TEMPLATE_VARS_KEY) or {}

            jinja2_instance = webapp2_instance.registry[registry_key] = jinja2_template_engine_factory(
                engine_config=engine_config, global_vars=global_vars)

    return jinja2_instance


# When you don't need to load a full render environment e.g. rendering an email template
def mini_renderer(template_path, template_vars, desired_engine='jinja2'):
    engine_loader = template_engine_map.get(desired_engine)
    template_engine = engine_loader()
    return template_engine.render_template(template_path, **template_vars)


template_engine_map = {
    'simple': simple_template_engine_loader,
    'jinja2': jinja2_template_engine_loader,
}
