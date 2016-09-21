import logging
from blinker import signal
from .routes import Component
from .statusmanager import StatusManager, parse_request_status_code
from .utils import decode_unicode_request_params, filter_unwanted_params, set_url_query_parameter
from .forms import DeleteModelForm, BaseSearchForm, PlaceholderForm
from .exceptions import UIFailed, CallbackFailed, FormDuplicateValue, ClientError, InvalidResourceUID, ApplicationError
import webapp2
from urlparse import urlparse
from datetime import datetime

__author__ = 'Matt'


class AppRegistry(object):
    handlers = {}

    @classmethod
    def reset(cls):
        cls.handlers = {}


default_redirect_route_kwargs = {
    'template': template,
    'handler': None,
    'name': None,
    'defaults': None,
    'build_only': False,
    'handler_method': None,
    'methods': None,
    'schemes': None,
    'redirect_to': None,
    'redirect_to_name': None,
    'strict_slash': True
}

default_method_definition = {
    'method': {
        'title': None,
        'code_name': None,
        'page_template': None,
        'login_required': False,
        'prefix_route': True,
    },
    'route': None,
    'handler': {
        'type': StandardUIHandler,
    }
}


def parse_component_config(resource_config):
    # TODO: set the default content type to html, if not in config
    for resource, config in resource_config.iteritems():

        for method_definition in config['method_definitions']:
            handler_name = '{}_{}'.format(resource, method_definition['method']['code_name'])

            # Parse the default method config
            default_method_config = {
                'title': None,
                'code_name': None,
                'page_template': None,
                'login_required': False,
                'prefix_route': True,
            }

            try:
                default_method_config.update(method_definition['method'])
            except KeyError:
                pass

            # Parse the default route config
            default_route_config = {
                'template': None,
                'handler': None,
                'name': None,
                'defaults': None,
                'build_only': False,
                'handler_method': None,
                'methods': None,
                'schemes': None,
                'redirect_to': None,
                'redirect_to_name': None,
                'strict_slash': True
            }

            try:
                default_route_config.update(method_definition['route'])
            except KeyError:
                pass

            # TODO: delete template key and pass value as arg
            # TODO: setup the route

            # Parse the default handler config
            default_handler_config = {
                'title': default_method_config['title'],
                'code_name': handler_name,
                'type': StandardUIHandler,
                'success_route': None,
                'failure_route': None,
            }

            try:
                default_handler_config.update(method_definition['handler'])
            except KeyError:
                pass

            handler_type = default_handler_config['type']
            del default_handler_config['type']

            AppRegistry.handlers[handler_name] = handler_type(**default_handler_config)

            # TODO: connect the handler to the signals that are sent from the route


def crud_handler_definition_generator(component_name, form=PlaceholderForm, delete_form=DeleteModelForm, route_customizations=None, route_map=None):
    """
    `route_customizations` is a dict of the formate:

    customizations = {
        'ui': {...}
        'action': {...}
    }

    The contents of the `ui` and `action` dicts are the same as the kwargs for adding a component route. However,
    because we are generating the config for crud handlers, you should not set the `route_type` key unless you really
    know what you are doing. Chances are, using a different type will cause unexpected behaviour.

    Note: If you set `route_name`, only the value from the `ui` dict will be used. So if you set `route_name` in the UI
    dict to 'register' and then set it in the `action` dict as 'update', the component will be called 'register', and
    so will the route. You can obviously change this by modifying the output of this function.

    `route_map` is a dict of name/id => route mappings (either webapp2 route name or full url). We use
    dict.update to merge these with the route map. Therefore, if you want to completely override a particular route, for
    example to redirect back to a home page after login, you could overwrite one of the mappings.


    :param component_name:
    :param form:
    :param delete_form:
    :param route_map:
    :param route_customizations:
    :type component_name: str
    :type form: object
    :type delete_form: object
    :type route_map: dict
    :type route_customizations: dict
    :return:
    """
    # Generate handler definitions for each crud route to avoid having to type them out in full each time
    if route_customizations is None:
        route_customizations = {}

    try:
        create_name = route_customizations['create']['ui']['route_name']
    except KeyError:
        create_name = 'create'

    try:
        read_name = route_customizations['read']['ui']['route_name']
    except KeyError:
        read_name = 'read'

    try:
        update_name = route_customizations['update']['ui']['route_name']
    except KeyError:
        update_name = 'update'

    try:
        delete_name = route_customizations['delete']['ui']['route_name']
    except KeyError:
        delete_name = 'delete'

    route_map = {u'create.ui': u'component.{}.{}.ui'.format(component_name, create_name),
                 u'read.ui': u'component.{}.{}.ui'.format(component_name, read_name),
                 u'update.ui': u'component.{}.{}.ui'.format(component_name, update_name),
                 u'delete.ui': u'component.{}.{}.ui'.format(component_name, delete_name),
                 u'create.action': u'component.{}.{}.action'.format(component_name, create_name),
                 u'update.action': u'component.{}.{}.action'.format(component_name, update_name),
                 u'delete.action': u'component.{}.{}.action'.format(component_name, delete_name),
                 u'create.success': u'component.{}.{}.ui'.format(component_name, create_name),
                 u'update.success': u'component.{}.{}.ui'.format(component_name, update_name),
                 u'delete.success': u'component.{}.{}.ui'.format(component_name, delete_name)}

    if route_map is not None:
        route_map.update(route_map)

    # We explicitly set the routes below so that they apply any overrides that may have been specified. They don't need
    # to be set is you are instantiating the StandardFormHandler class directly
    return [
        {
            'type': StandardFormHandler,
            'config': {
                'form': form,
                'component_name': component_name,
                'handler_code_name': create_name,
                'route_map': {
                    u'create.ui': route_map[u'create.ui'],
                    u'create.action': route_map[u'create.action'],
                    u'create.success': route_map[u'create.success'],
                }
            },
            'route_customizations': route_customizations.get('create', {})
        },
        {
            'type': StandardUIHandler,
            'config': {
                'form': form,
                'component_name': component_name,
                'handler_code_name': read_name,
                'route_map': {
                    u'read.ui': route_map[u'read.ui'],
                }
            },
            'route_customizations': route_customizations.get('read', {})
        },
        {
            'type': StandardFormHandler,
            'config': {
                'form': form,
                'component_name': component_name,
                'handler_code_name': update_name,
                'route_map': {
                    u'update.ui': route_map[u'update.ui'],
                    u'update.action': route_map[u'update.action'],
                    u'update.success': route_map[u'update.success'],
                }
            },
            'route_customizations': route_customizations.get('update', {})
        },
        {
            'type': StandardFormHandler,
            'config': {
                'form': delete_form,
                'component_name': component_name,
                'handler_code_name': delete_name,
                'route_map': {
                    u'delete.ui': route_map[u'delete.ui'],
                    u'delete.action': route_map[u'delete.action'],
                    u'delete.success': route_map[u'delete.success'],
                }
            },
            'route_customizations': route_customizations.get('delete', {})
        },
    ]


def default_route_signaler(request, response, **kwargs):
    handler_hook_name = u'{}_{}'.format(request.route.name, request.method)
    handler_signal = signal(handler_hook_name)

    if bool(handler_signal.receivers):
        # We send request as an arg to avoid having to use a separate 'sender', which would affect the method signatures
        handler_signal.send(request, response=response, hook_name=handler_hook_name)


class BaseHandlerMixin(object):
    """
    The route handling is a little complicated. We want the allow the routes to be configurable via the handler config.
    However, at the time of init, webapp2 has not yet been initialized. This means that we have to accept the webapp2
    route names in the config and then parse them on demand (we cache the result so the overhead is minimal).

    The route_map is a dict of route ID/name => route values. The route ID/name is just a short name used internally by
    the handler - it has nothing to do with webapp2 routes.

    You *must* register all desired routes for the handler if you want to use the built in redirect handling. Should
    you need to use a route that is not registered you will have to override it using the appropriate hooks.

    The route_map config parameter will accept either a webapp2 route name or a full url. So as an example you could:

     - Change the `app_default` route to `component.user.read.ui`, which is the name of a webapp2 route. This would then
        be parsed to `/user/read` internally and used for any redirects that use the `app_default` id

     - Change the `app_default` route to `http://test.com`. This would then be used whenever the `app_default` id is
        passed to `set_redirect_url`

    """
    def __init__(self, code_name, title, success_route=None, failure_route=None, **kwargs):
        self.code_name = code_name
        self.title = title
        self._route_cache = {}
        self.status_manager = StatusManager

        if success_route is None:
            success_route = self.code_name

        if failure_route is None:
            failure_route = self.code_name

        self.success_route = success_route
        self.failure_route = failure_route

    @staticmethod
    def decode_unicode_uri_params(kwargs):
        return decode_unicode_request_params(kwargs)

    @staticmethod
    def parse_status_code(request, response):
        return parse_request_status_code(request=request, response=response)

    @staticmethod
    def filter_unwanted_params(request_params, unwanted):
        return filter_unwanted_params(request_params=request_params, unwanted=unwanted)

    def _get_route(self, route_name):
        try:
            return self._route_cache[route_name]
        except KeyError:
            if not self.valid_url(route_name):
                # If the value is not a full url then we assume it is a webapp2 route name and try to build the url
                try:
                    route_url = webapp2.uri_for(route_name)
                except KeyError:
                    # By default, we will redirect to '/' unless `default` is explicitly set in the app. This
                    # allows us to show friendly error messages instead of returning a http 500 error
                    if route_name != 'default':
                        raise
                    else:
                        route_url = '/'
            else:
                route_url = route_name

            self._route_cache[route_name] = route_url
            return route_url

    def get_route_url(self, request, route_name, follow_continue=False, **kwargs):
        if request.GET.get('continue_url', False) and follow_continue:
            return str(self.set_url_query_parameter(request.GET['continue_url'], kwargs))
        else:
            if request.GET.get('continue_url', False) and not kwargs.get('continue_url', False):
                kwargs['continue_url'] = request.GET['continue_url']

            return str(self.set_url_query_parameter(self._get_route(route_name=route_name), kwargs))

    def set_redirect_url(self, response, **kwargs):
        response.redirect_to = self.get_route_url(response=response, **kwargs)

    set_url_query_parameter = staticmethod(set_url_query_parameter)

    @staticmethod
    def _initiate_redirect(request, response):
        webapp2.redirect(uri=response.redirect_to, request=request, response=response)

    @staticmethod
    def valid_url(url):
        """
        Credit to: http://stackoverflow.com/a/38020041
        :param url:
        :return:
        """
        try:
            result = urlparse(url)
            return True if [result.scheme, result.netloc, result.path] else False
        except:
            return False


class BaseFormHandler(BaseHandlerMixin):
    def __init__(self, form, form_method='post', request_config_keys=None, filter_params=None,
                 validation_trigger_codes=None, **kwargs):
        super(BaseFormHandler, self).__init__(**kwargs)

        self.filter_params = filter_params

        if request_config_keys is None:
            self.request_config_keys = ['csrf_config']
        else:
            self.request_config_keys = request_config_keys

        self.success_status_code = self.status_manager.DEFAULT_SUCCESS_CODE
        self.failure_status_code = self.status_manager.DEFAULT_FORM_FAILURE_CODE
        self.key_required_status_code = self.status_manager.add_status(
            message='You must supply a {} key.'.format(self.title), status_type='alert')
        self.key_invalid_status_code = self.status_manager.add_status(
            message='You must supply a valid {} key.'.format(self.title), status_type='alert')

        self.validation_trigger_codes = [self.failure_status_code]
        self.form = form
        self.form_method = form_method

        if validation_trigger_codes:
            self.validation_trigger_codes += validation_trigger_codes

    @staticmethod
    def _build_form_config(request, action_url=None, csrf=True, method='POST', formdata=None, data=None):
        """
        Here we build the base config needed to generate a form instance. It includes some sane defaults but you should
        use the `*_customization` signal to modify this to you needs.

        For example, a common situation would be to provide an existing object to the form. Use the appropriate signal
        and modify the form config to include `existing_obj`.

        You could also force the use of GET data in order to re-validate a form on the UI side. Simply set `formdata`
         to request.GET

        :param request:
        :param action_url:
        :param csrf:
        :param method:
        :param data:
        :return:
        """

        return {
            'request': request,
            'csrf': csrf,
            'formdata': formdata,
            'data': data,
            'action_url': action_url if action_url is not None else '',
            'method': method,
        }


def default_form_csrf_config(sender, request, response, form_config):
    form_config['csrf_context'] = request.secrets.getbyteliteral('csrf_secret')
    form_config['csrf_secret'] = request.environ['beaker.session']
    form_config['csrf_time_limit'] = datetime.timedelta(minutes=request.secrets.getint('csrf_time_limit'))


def default_form_recaptcha_config(sender, request, response, form_config):
    form_config['recaptcha_site_key'] = request.secrets.get('recaptcha_site_key')
    form_config['recaptcha_site_secret'] = request.secrets.get('recaptcha_site_secret')


class StandardUIHandler(BaseHandlerMixin):
    UI_HOOK_NAME = 'ui'
    UI_FAILED_HOOK_NAME = 'ui_failed'

    def __init__(self, **kwargs):
        super(StandardUIHandler, self).__init__(**kwargs)
        self.failure_status_code = self.status_manager.DEFAULT_FORM_FAILURE_CODE

        self.ui_hook = signal(self.UI_HOOK_NAME)
        self.ui_failed_hook = signal(self.UI_FAILED_HOOK_NAME)

    @property
    def _ui_hook_enabled(self):
        return bool(self.ui_hook.receivers)

    @property
    def _ui_failed_hook_enabled(self):
        return bool(self.ui_failed_hook.receivers)

    def ui_handler(self, request, response):
        """
        Very simple UI handler. Use `_ui_hook` to modify the response as necessary. Raise ClientError or UIFailed to
        interrupt the UI render and redirect to the default route. You may also set a custom redirect by setting
        `response.redirect_to` before raising the aforementioned exceptions.

        :param request:
        :param response:
        :return:
        """
        self.parse_status_code(request=request, response=response)
        self.set_redirect_url(request=request, response=response, route_name=self.failure_route,
                              status_code=self.failure_status_code)
        try:
            if self._ui_hook_enabled:
                self.ui_hook.send(self, request=request, response=response, hook_name=self.UI_HOOK_NAME)
        except (ClientError, UIFailed), e:
            logging.exception(u'{} when processing {}.ui'.format(e.message, self.code_name))

            if self._ui_failed_hook_enabled:
                self.ui_failed_hook.send(self, request=request, response=response, hook_name=self.UI_FAILED_HOOK_NAME)

            self._initiate_redirect(request, response)


class StandardFormHandler(BaseFormHandler):
    UI_HOOK_NAME = 'ui'
    FORM_CONFIG_HOOK_NAME = 'form_config'
    CUSTOMIZE_FORM_HOOK_NAME = 'customize_form'
    VALID_FORM_HOOK_NAME = 'valid_form'
    FORM_ERROR_HOOK_NAME = 'form_error'
    DUPLICATE_VALUE_HOOK_NAME = 'duplicate_value'
    CALLBACK_FAILED_HOOK_NAME = 'callback_failed'
    UI_FAILED_HOOK_NAME = 'ui_failed'

    def __init__(self, form=PlaceholderForm, success_message=None, failure_message=None, suppress_success_status=False,
                 force_ui_get_data=False, force_callback_get_data=False, **kwargs):
        super(StandardFormHandler, self).__init__(form=form, **kwargs)

        self.force_ui_get_data = force_ui_get_data
        self.force_callback_get_data = force_callback_get_data

        if not suppress_success_status and success_message:
            self.success_status_code = self.status_manager.add_status(message=success_message, status_type='success')
        elif not suppress_success_status:
            self.success_status_code = self.status_manager.DEFAULT_SUCCESS_CODE
        else:
            self.success_status_code = None

        if failure_message:
            self.failure_status_code = self.status_manager.add_status(message=failure_message, status_type='alert')
        else:
            self.failure_status_code = self.failure_status_code

        self.ui_hook = signal(self.UI_HOOK_NAME)
        self.form_config_hook = signal(self.FORM_CONFIG_HOOK_NAME)
        self.customize_form_hook = signal(self.CUSTOMIZE_FORM_HOOK_NAME)
        self.valid_form_hook = signal(self.VALID_FORM_HOOK_NAME)
        self.form_error_hook = signal(self.FORM_ERROR_HOOK_NAME)
        self.duplicate_value_hook = signal(self.DUPLICATE_VALUE_HOOK_NAME)
        self.callback_failed_hook = signal(self.CALLBACK_FAILED_HOOK_NAME)
        self.ui_failed_hook = signal(self.UI_FAILED_HOOK_NAME)

    @property
    def _ui_hook_enabled(self):
        return bool(self.ui_hook.receivers)

    @property
    def _form_config_hook_enabled(self):
        return bool(self.form_config_hook.receivers)

    @property
    def _customize_form_hook_enabled(self):
        return bool(self.customize_form_hook.receivers)

    @property
    def _valid_form_hook_enabled(self):
        return bool(self.valid_form_hook.receivers)

    @property
    def _form_error_hook_enabled(self):
        return bool(self.form_error_hook.receivers)

    @property
    def _duplicate_value_hook_enabled(self):
        return bool(self.duplicate_value_hook.receivers)

    @property
    def _callback_failed_hook_enabled(self):
        return bool(self.callback_failed_hook.receivers)

    @property
    def _ui_failed_hook_enabled(self):
        return bool(self.ui_failed_hook.receivers)

    def ui_handler(self, request, response):
        """
        You must set `form` in the handler config. This should be the class definition and not an instance of the form.

        If you really need to use a different form at run time, you can override the form instance via
        `_customize_form_hook`.

        Note: if you need to customise the form in some way, e.g. to remove a field, then use the
        `_customize_form_hook` hook. The callback will be passed the form instance for you to modify.

        Note: by default we will trigger a form validation if the status code is in the list of triggers. In order to
        do this the form needs data, so we automatically fill this with the request.GET data.

        :param request:
        :param response:
        :return:
        """
        try:
            if self._ui_hook_enabled:
                self.ui_hook.send(self, request=request, response=response, hook_name=self.UI_HOOK_NAME)
        except (ClientError, UIFailed), e:
            logging.exception(u'{} when processing {}.ui'.format(e.message, self.code_name))
            self.set_redirect_url(request=request, response=response, route_name=self.failure_route,
                                  status_code=self.failure_status_code)

            if self._ui_failed_hook_enabled:
                self.ui_failed_hook.send(self, request=request, response=response, hook_name=self.UI_FAILED_HOOK_NAME)

            self._initiate_redirect(request, response)
        else:
            self.parse_status_code(request=request, response=response)
            validate = response.raw.status_code in self.validation_trigger_codes
            formdata = request.GET if validate else None

            form_config = self._build_form_config(request=request, action_url=self.get_route_url(request=request, route_name=self.code_name), formdata=formdata)

            if self._form_config_hook_enabled:
                self.form_config_hook.send(self, request=request, response=response, form_config=form_config, hook_name=self.FORM_CONFIG_HOOK_NAME)

            form_instance = self.form(**form_config)

            if self._customize_form_hook_enabled:
                self.customize_form_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.CUSTOMIZE_FORM_HOOK_NAME)

            response.raw.form = form_instance

            if validate:
                response.raw.form.validate()

    def callback_handler(self, request, response):
        """
        If form validation passes the `_valid_form_hook` will be triggered. You can use this to do whatever you need
        to do after receiving valid data.

        If the form does not validate then the `_form_error_hook` will be triggered. By default we set the redirect url
        in the response object to go back to the ui handler with the form data as GET attributes. This can be overridden.

        If the form validates but you raise either CallbackFailed or UIFailed then we will trigger
        `_callback_failed_hook`. If there are no receivers for this signal then we will redirect to the ui handler in
        the same manner as a form validation failure. If there are receivers then by default we parse a redirect which
        is determined by the `response.raw.redirect_to` value. If none is set then an exception will be raised.

        Note: if you need to customise the form in some way, e.g. to remove a field, then use the
        `_customize_form_hook` hook. The callback will be passed the form instance for you to modify.


        :param request:
        :param response:
        :return:
        """
        form_config = self._build_form_config(request=request)

        if self._form_config_hook_enabled:
            self.form_config_hook.send(self, request=request, response=response, form_config=form_config, hook_name=self.FORM_CONFIG_HOOK_NAME)

        form_instance = self.form(**form_config)

        if self._customize_form_hook_enabled:
            self.customize_form_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.CUSTOMIZE_FORM_HOOK_NAME)

        if form_instance.validate():
            self.set_redirect_url(request=request, response=response, route_name=self.success_route,
                                  status_code=self.success_status_code, follow_continue=True)
            try:
                if self._valid_form_hook_enabled:
                    self.valid_form_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.VALID_FORM_HOOK_NAME)
            except FormDuplicateValue, e:
                filtered_params = self.filter_unwanted_params(request_params=request.params, unwanted=self.filter_params)

                self.set_redirect_url(request=request, response=response, route_name=self.failure_route,
                                      status_code=self.failure_status_code, duplicates=e.duplicates, **filtered_params)

                if self._duplicate_value_hook_enabled:
                    self.duplicate_value_hook.send(self, request=request, response=response, form_instance=form_instance, duplicates=e.duplicates, hook_name=self.DUPLICATE_VALUE_HOOK_NAME)
            except CallbackFailed, e:
                filtered_params = self.filter_unwanted_params(request_params=request.params,
                                                              unwanted=self.filter_params)
                self.set_redirect_url(request=request, response=response, route_name=self.failure_route,
                                      status_code=self.failure_status_code, **filtered_params)

                if self._callback_failed_hook_enabled:
                    self.callback_failed_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.CALLBACK_FAILED_HOOK_NAME)

        else:
            filtered_params = self.filter_unwanted_params(request_params=request.params, unwanted=self.filter_params)
            self.set_redirect_url(request=request, response=response, route_name=self.failure_route,
                                  status_code=self.failure_status_code, **filtered_params)
            if self._form_error_hook_enabled:
                self.form_error_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.FORM_ERROR_HOOK_NAME)

        self._initiate_redirect(request, response)


class SearchHandler(BaseFormHandler):
    """
    If you perform a search, and there are results, you should set `response.raw.search_results` via `_valid_form_hook`.
    You can then use then setup the default receiver for search results to save you having to repeat the same code
    for every search handler.


    search_properties_to_display is a list of search result properties that you want to display. They will be rendered
    in the order that you set in the list. If no list is set then all properties will be displayed in the order that
    they were parsed.
    """
    UI_HOOK_NAME = 'ui'
    RESULTS_UI_HOOK_NAME = 'results_ui'
    FORM_CONFIG_HOOK_NAME = 'form_config'
    CUSTOMIZE_FORM_HOOK_NAME = 'customize_form'
    VALID_FORM_HOOK_NAME = 'valid_form'
    FORM_ERROR_HOOK_NAME = 'form_error'
    CALLBACK_FAILED_HOOK_NAME = 'callback_failed'
    UI_FAILED_HOOK_NAME = 'ui_failed'

    def __init__(self, search_properties_to_display=None, form=BaseSearchForm, view_full_result_route=None,
                 keep_blank_values=0, force_empty_query=False, **kwargs):
        super(SearchHandler, self).__init__(form=form, **kwargs)

        self.search_properties_to_display = search_properties_to_display
        self.view_full_result_route = view_full_result_route
        self.keep_blank_values = keep_blank_values
        self.force_empty_query = force_empty_query

        self.invalid_search_status_code = self.status_manager.add_status(
            message='Your search was not valid. Please try another one.', status_type='alert')

        self.ui_hook = signal(self.UI_HOOK_NAME)
        self.results_ui_hook = signal(self.RESULTS_UI_HOOK_NAME)
        self.form_config_hook = signal(self.FORM_CONFIG_HOOK_NAME)
        self.customize_form_hook = signal(self.CUSTOMIZE_FORM_HOOK_NAME)
        self.valid_form_hook = signal(self.VALID_FORM_HOOK_NAME)
        self.form_error_hook = signal(self.FORM_ERROR_HOOK_NAME)
        self.callback_failed_hook = signal(self.CALLBACK_FAILED_HOOK_NAME)
        self.ui_failed_hook = signal(self.UI_FAILED_HOOK_NAME)

    @property
    def _ui_hook_enabled(self):
        return bool(self.ui_hook.receivers)

    @property
    def _results_ui_hook_enabled(self):
        return bool(self.results_ui_hook.receivers)

    @property
    def _form_config_hook_enabled(self):
        return bool(self.form_config_hook.receivers)

    @property
    def _customize_form_hook_enabled(self):
        return bool(self.customize_form_hook.receivers)

    @property
    def _valid_form_hook_enabled(self):
        return bool(self.valid_form_hook.receivers)

    @property
    def _form_error_hook_enabled(self):
        return bool(self.form_error_hook.receivers)

    @property
    def _callback_failed_hook_enabled(self):
        return bool(self.callback_failed_hook.receivers)

    @property
    def _ui_failed_hook_enabled(self):
        return bool(self.ui_failed_hook.receivers)

    def ui_handler(self, request, response):
        try:
            if self._ui_hook_enabled:
                self.ui_hook.send(self, request=request, response=response, hook_name=self.UI_HOOK_NAME)
        except (ClientError, UIFailed), e:
            logging.exception(u'{} when processing {}.ui'.format(e.message, self.code_name))
            self.set_redirect_url(request=request, response=response, route_name=self.failure_route,
                                  status_code=self.failure_status_code)

            if self._ui_failed_hook_enabled:
                self.ui_failed_hook.send(self, request=request, response=response, hook_name=self.UI_FAILED_HOOK_NAME)

            self._initiate_redirect(request, response)
        else:
            self.parse_status_code(request=request, response=response)

            form_config = self._build_form_config(request=request, action_url=self.get_route_url(request=request, route_name=self.code_name), formdata=request.GET, method='GET')

            if self._form_config_hook_enabled:
                self.form_config_hook.send(self, request=request, response=response, form_config=form_config, hook_name=self.FORM_CONFIG_HOOK_NAME)

            form_instance = self.form(**form_config)

            if self._customize_form_hook_enabled:
                self.customize_form_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.CUSTOMIZE_FORM_HOOK_NAME)

            response.raw.form = form_instance

            if self.force_empty_query or (request.params.get('query', False) is not False) \
                    or (response.raw.status_code == self.invalid_search_status_code):
                if form_instance.validate():
                    try:
                        if self._valid_form_hook_enabled:
                            self.valid_form_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.VALID_FORM_HOOK_NAME)
                    except (CallbackFailed, UIFailed), e:
                        self.set_redirect_url(request=request, response=response, route_name=self.failure_route, status_code=self.invalid_search_status_code)

                        if self._callback_failed_hook_enabled:
                            self.callback_failed_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.CALLBACK_FAILED_HOOK_NAME)

                        self._initiate_redirect(request, response)
                    else:
                        if self._results_ui_hook_enabled:
                            self.results_ui_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.RESULTS_UI_HOOK_NAME)

                elif not response.raw.status_code:
                    self.set_redirect_url(request=request, response=response, route_name=self.failure_route, status_code=self.invalid_search_status_code)

                    if self._form_error_hook_enabled:
                        self.form_error_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.FORM_ERROR_HOOK_NAME)

                    self._initiate_redirect(request, response)


def default_search_results_ui(sender, request, response, form_instance):
    """
    This handles the most common UI values that you would need to set when using the GAE search API. You may also want
    to set `response.raw.search_result_properties` to limit which data is show in the results table.
    :param sender:
    :param request:
    :param response:
    :param form_instance:
    :return:
    """
    if response.raw.search_results.cursor:
        response.raw.search_results_next_link = sender.set_url_query_parameter(url=request.url,
                                                                               new_query_params={
                                                                                   'cursor': response.raw.search_results.cursor},
                                                                               keep_blank_values=sender.keep_blank_values)
    elif request.params.get('cursor', False):
        response.raw.search_results_final_page = True
        response.raw.search_results_next_link = sender.set_url_query_parameter(url=request.url,
                                                                               new_query_params={
                                                                                   'cursor': ''},
                                                                               keep_blank_values=sender.keep_blank_values)
    response.raw.view_full_result_route = sender.view_full_result_route
    response.raw.reset_search_url = sender.get_route_url(request=request, route_name=sender.ui_name)


class HeadlessSearchHandler(SearchHandler):
    """
    This is almost exactly the same as the standard SearchHandler. The only difference is the way the form validation
    is handled. You should use the same hooks for performing searches and modifying the UI as the standard handler.
    """
    def ui_handler(self, request, response):
        try:
            if self._ui_hook_enabled:
                self.ui_hook.send(self, request=request, response=response, hook_name=self.UI_HOOK_NAME)
        except (ClientError, UIFailed), e:
            logging.exception(u'{} when processing {}.ui'.format(e.message, self.code_name))
            self.set_redirect_url(request=request, response=response, route_name=self.failure_route,
                                  status_code=self.failure_status_code)

            if self._ui_failed_hook_enabled:
                self.ui_failed_hook.send(self, request=request, response=response, hook_name=self.UI_FAILED_HOOK_NAME)

            self._initiate_redirect(request, response)
        else:
            self.parse_status_code(request=request, response=response)

            form_config = self._build_form_config(request=request, action_url=self.get_route_url(request=request, route_name=self.code_name), formdata=request.GET, method='GET')

            if self._form_config_hook_enabled:
                self.form_config_hook.send(self, request=request, response=response, form_config=form_config, hook_name=self.FORM_CONFIG_HOOK_NAME)

            form_instance = self.form(**form_config)

            if self._customize_form_hook_enabled:
                self.customize_form_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.CUSTOMIZE_FORM_HOOK_NAME)

            response.raw.form = form_instance

            if not form_instance.validate():
                self.set_redirect_url(request=request, response=response, route_name=self.failure_route, status_code=self.invalid_search_status_code)

                if self._form_error_hook_enabled:
                    self.form_error_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.FORM_ERROR_HOOK_NAME)

                self._initiate_redirect(request, response)

            try:
                if self._valid_form_hook_enabled:
                    self.valid_form_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.VALID_FORM_HOOK_NAME)
            except (CallbackFailed, UIFailed), e:
                self.set_redirect_url(request=request, response=response, route_name=self.failure_route, status_code=self.invalid_search_status_code)

                if self._callback_failed_hook_enabled:
                    self.callback_failed_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.CALLBACK_FAILED_HOOK_NAME)

                self._initiate_redirect(request, response)
            else:
                if self._results_ui_hook_enabled:
                    self.results_ui_hook.send(self, request=request, response=response, form_instance=form_instance, hook_name=self.RESULTS_UI_HOOK_NAME)


class AutoSearchHandler(SearchHandler):
    """
    This is almost exactly the same as the standard SearchHandler. The only difference is the lack of form validation.
    You should use the same hooks for performing searches and modifying the UI as the standard handler.
    """
    def ui_handler(self, request, response):
        try:
            if self._ui_hook_enabled:
                self.ui_hook.send(self, request=request, response=response, hook_name=self.UI_HOOK_NAME)
        except (ClientError, UIFailed), e:
            logging.exception(u'{} when processing {}.ui'.format(e.message, self.code_name))
            self.set_redirect_url(request=request, response=response, route_name=self.failure_route,
                                  status_code=self.failure_status_code)

            if self._ui_failed_hook_enabled:
                self.ui_failed_hook.send(self, request=request, response=response, hook_name=self.UI_FAILED_HOOK_NAME)

            self._initiate_redirect(request, response)
        else:
            self.parse_status_code(request=request, response=response)

            try:
                if self._valid_form_hook_enabled:
                    self.valid_form_hook.send(self, request=request, response=response, form_instance=None, hook_name=self.VALID_FORM_HOOK_NAME)
            except (CallbackFailed, UIFailed), e:
                self.set_redirect_url(request=request, response=response, route_name=self.failure_route, status_code=self.invalid_search_status_code)

                if self._callback_failed_hook_enabled:
                    self.callback_failed_hook.send(self, request=request, response=response, form_instance=None, hook_name=self.CALLBACK_FAILED_HOOK_NAME)

                self._initiate_redirect(request, response)
            else:
                if self._results_ui_hook_enabled:
                    self.results_ui_hook.send(self, request=request, response=response, form_instance=None, hook_name=self.RESULTS_UI_HOOK_NAME)
