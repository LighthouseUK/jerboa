import types
import webapp2
import logging
import jinja2
from blinker import signal

__author__ = 'Matt'


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


def retrofit_response(sender, request, response):
    """
    Designed to be used via a blinker signal, hence the 'sender' arg.

    Adds `raw` attribute that is used by jerboa handlers to store data needed to generate the response.
        For example: forms, app info, and variables

    Also adds the content type to the headers. If you want to override this you should change the config that is
    applied to the route. The value supplied in the route config must be a string that can be used for the
    `Content-Type` header.

    :param sender:
    :param request:
    :param response:
    :return:
    """
    response.raw = ScratchSpace()

    try:
        response.headers.add_header('Content-Type', request.route.method_config['content_type'])
    except KeyError:
        # No content type set
        pass


def custom_response_headers(sender, request, response):
    """
    Designed to be used via a blinker signal, hence the 'sender' arg.

    This is an example of adding custom headers to all routes. Here we set the 'X-UA-Compatible' header, if the content
    type is set to html. You can create your own version of this to add any headers you like.

    If you need to make changes on an individual route level then you can do this in the handlers.

    :param sender:
    :param request:
    :param response:
    :return:
    """
    try:
        if request.route.config['content_type'] == 'text/html':
            response.headers.add_header('X-UA-Compatible', 'IE=Edge,chrome=1')
    except KeyError:
        # Config value does not exist
        pass


class SimpleRenderer(object):
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


class Jinja2Renderer(object):
    """Wrapper for Jinja2 environment. Based on webapp2_extras.jinja2
    """
    def __init__(self, config):
        """Initializes the Jinja2 object.
        """
        config = {
            'environment_args': {'extensions': JINJA2_EXTENSIONS,
                                 'autoescape': config.settings.getboolean('jinja2_env_autoescape',
                                                                          section=FRONTEND),},
            'theme_base_template_path': config.settings.getlist('theme_base_template_path', section=FRONTEND),
            'enable_i18n': 'jinja2.ext.i18n' in JINJA2_EXTENSIONS,
            'global_vars': {},
            'filters': {},
            'tests': {},
        }

        config['environment_args']['loader'] = jinja2.FileSystemLoader(config['theme_base_template_path'])

        # Initialize the environment.
        self.environment = jinja2.Environment(**config['environment_args'])

        self.environment.globals.update({'getattr': getattr})
        if isinstance(config['global_vars'], dict):
            self.environment.globals.update(config['global_vars'])

        if isinstance(config['filters'], dict):
            self.environment.filters.update(config['filters'])

        if isinstance(config['tests'], dict):
            self.environment.filters.update(config['tests'])

        if config['enable_i18n']:
            # Install i18n.
            from webapp2_extras import i18n
            self.environment.install_gettext_callables(
                lambda x: i18n.gettext(x),
                lambda s, p, n: i18n.ngettext(s, p, n),
                newstyle=True)
            self.environment.filters.update({
                'format_date':      i18n.format_date,
                'format_time':      i18n.format_time,
                'format_datetime':  i18n.format_datetime,
                'format_timedelta': i18n.format_timedelta,
            })

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

    def render(self, template_name, response):
        # propably just need to pass request.route.config['page_template']
        response.write(self.render_template(template_name, **response.raw.__dict__))
