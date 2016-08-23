import inflection
import logging
from blinker import signal
from .statusmanager import StatusManager, parse_request_status_code
from .utils import decode_unicode_request_params, filter_unwanted_params
from .forms import DeleteModelForm, BaseSearchForm
import webapp2
from urllib import urlencode
from urlparse import parse_qs, urlsplit, urlunsplit

__author__ = 'Matt'


# === Exceptions ===
class UIFailed(Exception):
    """
    Can be used by ui functions. Allows them to fail if some condition is not met e.g. request parameter missing.
    """
    pass


class CallbackFailed(Exception):
    """
    Can be used by callback functions that are invoked upon form validation. Allows them to fail despite the form data
     begin valid e.g. if a unique value already exists.
    """
    pass


class FormDuplicateValue(ValueError, CallbackFailed):
    """
    Can be used by implementors that use the supplied hooks. Say you go to attempt to insert data into a datastore and
    it fails because a value already exists. Rather than having to do lots of checking and fetching of values, simply
    pass this exception the field names of the duplicates and raise it. The CRUD handler will do the rest.
    """

    def __init__(self, duplicates, message=u'Could not save the form because duplicate values were detected'):
        super(FormDuplicateValue, self).__init__(message)
        self.duplicates = duplicates


# === End Exceptions ===


def add_crud_routes(component, handler_object, route_titles=None):
    if not route_titles:
        route_titles = {}

    component.add_route(route_type='rendered',
                        route_name='create',
                        route_title=route_titles.get('create.ui', u'Create {}'.format(component.title)),
                        handler=handler_object.create_ui)
    component.add_route(route_type='rendered',
                        route_name='read',
                        route_title=route_titles.get('read.ui', u'Read {}'.format(component.title)),
                        handler=handler_object.read_ui)
    component.add_route(route_type='rendered',
                        route_name='update',
                        route_title=route_titles.get('update.ui', u'Update {}'.format(component.title)),
                        handler=handler_object.update_ui)
    component.add_route(route_type='rendered',
                        route_name='delete',
                        route_title=route_titles.get('delete.ui', u'Delete {}'.format(component.title)),
                        handler=handler_object.delete_ui)
    component.add_route(route_type='action',
                        route_name='create',
                        handler=handler_object.create_callback)
    component.add_route(route_type='action',
                        route_name='update',
                        handler=handler_object.update_callback)
    component.add_route(route_type='action',
                        route_name='delete',
                        handler=handler_object.delete_callback)


def add_search_routes(component, handler_object, route_titles=None):
    if not route_titles:
        route_titles = {}

    default_search_title = u'Search {}'.format(inflection.pluralize(component.title))

    component.add_route(route_type='rendered',
                        route_name='search',
                        route_title=route_titles.get('search.ui', default_search_title),
                        handler=handler_object.search_ui)
    component.add_route(route_type='action',
                        route_name='search',
                        handler=handler_object.search_callback)


class BaseHandlerMixin(object):
    def __init__(self, component_name, component_title, **kwargs):
        self.name = component_name
        self.title = component_title
        self.handler_map = {
            'app_default': 'default',
        }
        self.status_manager = StatusManager

    @staticmethod
    def decode_unicode_uri_params(kwargs):
        return decode_unicode_request_params(kwargs)

    @staticmethod
    def parse_status_code(request, response):
        return parse_request_status_code(request=request, response=response)

    @staticmethod
    def filter_unwanted_params(request_params, unwanted):
        return filter_unwanted_params(request_params=request_params, unwanted=unwanted)

    def change_handler_mapping(self, handler, new_mapping):
        self.handler_map[handler] = new_mapping

    def _build_minion_route_path(self, method):
        if method == 'default':
            return 'default'
        return 'component.{}.{}'.format(self.name, method)

    def build_url_with_continue_support(self, request, uri_for, **kwargs):
        if request.GET.get('continue_url', False) and not kwargs.get('continue_url', False):
            return webapp2.uri_for(uri_for, continue_url=request.GET['continue_url'],
                                   **self.decode_unicode_uri_params(kwargs))
        else:
            return webapp2.uri_for(uri_for, **self.decode_unicode_uri_params(kwargs))

    def build_handler_url_with_continue_support(self, request, handler, **kwargs):
        return self.build_url_with_continue_support(request=request, uri_for=self._build_minion_route_path(
            method=self.handler_map[handler]), **kwargs)

    def set_redirect_url(self, request, response, handler, follow_continue=False, **kwargs):
        if request.GET.get('continue_url', False) and follow_continue:
            redirect_url = self.set_query_parameter(request.GET['continue_url'], kwargs)
        else:
            redirect_url = self.build_handler_url_with_continue_support(request=request, handler=handler, **kwargs)
        response.redirect_to = str(redirect_url)

    def set_external_redirect_url(self, request, response, uri_for, follow_continue=False, **kwargs):
        if request.GET.get('continue_url', False) and follow_continue:
            redirect_url = self.set_query_parameter(request.GET['continue_url'], kwargs)
        else:
            redirect_url = self.build_url_with_continue_support(request=request, uri_for=uri_for, **kwargs)
        response.redirect_to = str(redirect_url)

    @staticmethod
    def set_query_parameter(url, additional_query_params, keep_blank_values=0):
        """Given a URL, set or replace a query parameter and return the
        modified URL.

            set_query_parameter('http://example.com?foo=bar&biz=baz', {'foo', 'stuff'})

            'http://example.com?foo=stuff&biz=baz'

        Solution originally from: http://stackoverflow.com/a/12897375
        :param url:
        :param additional_query_params dict:
        """
        scheme, netloc, path, query_string, fragment = urlsplit(url)
        query_params = parse_qs(query_string, keep_blank_values=keep_blank_values)

        for param_name, param_value in additional_query_params.iteritems():
            query_params[param_name] = [param_value]
        new_query_string = urlencode(query_params, doseq=True)

        return urlunsplit((scheme, netloc, path, new_query_string, fragment))

    @staticmethod
    def _parse_redirect(request, response):
        webapp2.redirect(uri=response.redirect_to, request=request, response=response)


class BaseFormHandler(BaseHandlerMixin):
    def __init__(self, form, form_method='post', request_config_keys=None, filter_params=None,
                 validation_trigger_codes=None, **kwargs):
        super(BaseFormHandler, self).__init__(**kwargs)

        self.filter_params = filter_params

        if request_config_keys is None:
            self.request_config_keys = ['csrf_config']
        else:
            self.request_config_keys = request_config_keys

        self.generic_success_status_code = self.status_manager.add_status(
            message='Successfully completed operation on {}.'.format(self.title), status_type='success')
        self.generic_failure_status_code = self.status_manager.add_status(
            message='Please correct the errors on the form below.', status_type='alert')
        self.key_required_status_code = self.status_manager.add_status(
            message='You must supply a {} key.'.format(self.title), status_type='alert')
        self.key_invalid_status_code = self.status_manager.add_status(
            message='You must supply a valid {} key.'.format(self.title), status_type='alert')

        self.validation_trigger_codes = [self.generic_failure_status_code]
        self.form = form
        self.form_method = form_method

        if validation_trigger_codes:
            self.validation_trigger_codes += validation_trigger_codes

    def _generate_form_instance(self, request, form, form_method, existing_model=None, action_url=None,
                                formdata=None, data=None, disabled_fields=None):
        # We have to do some hacky fixes for the CSRF protection here.
        form_config = self._get_request_config(request=request, config_keys=self.request_config_keys)

        if disabled_fields and 'csrf' in disabled_fields:
            form_config['csrf'] = False

        form_instance = form(request=request,
                             formdata=formdata,
                             existing_obj=existing_model,
                             data=data,
                             action_url=action_url,
                             method=form_method,
                             **form_config)

        if disabled_fields:
            for field_name in disabled_fields:

                if field_name != 'csrf':
                    delattr(form_instance, field_name)

        return form_instance

    def _parse_model_ui_form(self, request, response, form, action_method, form_method=None, existing_model=None,
                             disabled_fields=None, use_get_data=False, data=None, **kwargs):
        validate = response.raw.status_code in self.validation_trigger_codes
        formdata = request.GET if validate or use_get_data else None
        action_url = self.build_handler_url_with_continue_support(request, action_method)
        if not form_method:
            form_method = self.form_method

        response.raw.form = self._generate_form_instance(request=request,
                                                         form=form,
                                                         action_url=action_url,
                                                         form_method=form_method,
                                                         formdata=formdata,
                                                         existing_model=existing_model,
                                                         data=data,
                                                         disabled_fields=disabled_fields)

        if validate:
            response.raw.form.validate()

    @staticmethod
    def _get_request_config(request, config_keys):
        request_config = {}

        for config_key in config_keys:
            try:
                request_config.update(request.handler_config[config_key])
            except KeyError:
                pass

        return request_config


class StandardFormHandler(BaseFormHandler):
    def __init__(self, handler_name, success_function, handler_map=None, success_message=None,
                 failure_message=None, suppress_success_status=False, force_ui_get_data=False,
                 force_callback_get_data=False, **kwargs):
        super(StandardFormHandler, self).__init__(**kwargs)

        # Default mapping for handlers. These can be overridden but by default it will redirect back to the ui handler
        # upon success, with a success status code in the query string
        ui_name = u'{}.ui'.format(handler_name)
        callback_name = u'{}.action'.format(handler_name)
        success_name = u'{}.success'.format(handler_name)

        default_handler_map = {
            ui_name: ui_name,
            callback_name: callback_name,
            success_name: ui_name,
        }

        self.ui_name = ui_name
        self.callback_name = callback_name
        self.success_name = success_name
        self.success_function = success_function
        self.force_ui_get_data = force_ui_get_data
        self.force_callback_get_data = force_callback_get_data

        if handler_map:
            default_handler_map.update(handler_map)

        self.handler_map.update(default_handler_map)

        if not suppress_success_status and success_message:
            self.success_status_code = self.status_manager.add_status(message=success_message, status_type='success')
        else:
            self.success_status_code = None

        if failure_message:
            self.failure_status_code = self.status_manager.add_status(message=failure_message, status_type='alert')
        else:
            self.failure_status_code = self.generic_failure_status_code

    def ui_handler(self, request, response):
        try:
            signal('{}.hook'.format(self.ui_name)).send(self, request=request, response=response)
        except UIFailed, e:
            # A connector can raise this exception after setting a redirect uri
            self._parse_redirect(request, response)
        else:
            try:
                existing_model = response.raw.existing_model
            except AttributeError:
                existing_model = None

            self.parse_status_code(request=request, response=response)
            self._parse_model_ui_form(request=request, response=response, form=self.form,
                                      action_method=self.handler_map[self.callback_name],
                                      use_get_data=self.force_ui_get_data, form_method=self.form_method,
                                      existing_model=existing_model)

    def callback_handler(self, request, response):
        signal('pre_{}.hook'.format(self.callback_name)).send(self, request=request, response=response)

        formdata = request.GET if self.force_callback_get_data else None

        form = self._generate_form_instance(request=request, form=self.form, form_method=self.form_method, formdata=formdata)

        if form.validate():
            self.set_redirect_url(request=request, response=response, handler=self.success_name,
                                  status_code=self.success_status_code, follow_continue=True)
            try:
                self.success_function(self, request=request, response=response, form=form)
            except FormDuplicateValue, e:
                filtered_params = self.filter_unwanted_params(request_params=request.params,
                                                              unwanted=self.filter_params)

                duplicates_query_string = '&'.join('duplicate={}'.format(s) for s in e.duplicates)

                if not response.redirect_to:
                    self.set_redirect_url(request=request, response=response, handler=self.ui_name,
                                          status_code=self.failure_status_code, **filtered_params)
                # This is crude but there isn't an easy means of using webapp2.uri_for with an array for an arg
                response.redirect_to = u'{}&{}'.format(response.redirect_to, duplicates_query_string)
                signal('invalid_{}.hook'.format(self.callback_name)).send(self, request=request, response=response)
            except (CallbackFailed, UIFailed), e:
                signal('failed_{}.hook'.format(self.callback_name)).send(self, request=request, response=response)
                self._parse_redirect(request, response)
            else:
                signal('valid_{}.hook'.format(self.callback_name)).send(self, request=request, response=response,
                                                                        form=form)

        else:
            filtered_params = self.filter_unwanted_params(request_params=request.params, unwanted=self.filter_params)
            self.set_redirect_url(request=request, response=response, handler=self.ui_name,
                                  status_code=self.failure_status_code, **filtered_params)
            signal('invalid_{}.hook'.format(self.callback_name)).send(self, request=request, response=response)

        self._parse_redirect(request, response)


class CrudHandler(BaseFormHandler):
    def __init__(self, read_properties, disabled_create_properties=None,
                 disabled_update_properties=None, crud_handler_map=None, delete_form=DeleteModelForm,
                 force_create_ui_get_data=False, **kwargs):
        super(CrudHandler, self).__init__(**kwargs)

        default_handler_map = {
            'crud_default': 'read.ui',
            'create_success': 'read.ui',
            'update_success': 'read.ui',
            'delete_success': 'search.ui',
            'create.ui': 'create.ui',
            'read.ui': 'read.ui',
            'update.ui': 'update.ui',
            'delete.ui': 'delete.ui',
            'create.action': 'create.action',
            'update.action': 'update.action',
            'delete.action': 'delete.action',
        }

        if crud_handler_map:
            default_handler_map.update(crud_handler_map)

        self.handler_map.update(default_handler_map)
        self.delete_form = delete_form
        self.read_properties = read_properties
        if disabled_create_properties is None:
            disabled_create_properties = ['uid']
        self.disabled_create_properties = disabled_create_properties
        self.disabled_update_properties = disabled_update_properties or []
        self.force_create_ui_get_data = force_create_ui_get_data

        self.create_success_status_code = self.status_manager.add_status(
            message='Successfully created {}.'.format(self.title), status_type='success')
        self.update_success_status_code = self.status_manager.add_status(
            message='Successfully updated {}.'.format(self.title), status_type='success')
        self.delete_success_status_code = self.status_manager.add_status(
            message='Successfully deleted {}.'.format(self.title), status_type='success')

    @staticmethod
    def _get_model_key(request):
        uid = request.GET['uid']
        if uid == 'None':
            raise ValueError('UID is not set')
        return uid

    def _get_model(self, uid):
        model = self._load_model(uid=uid)

        if not model:
            raise ValueError('Invalid model key')

        return model

    def _load_model(self, uid):
        """
        This method should be defined when using the mixin. Simply load a resource object to be used for the CRUD ops.
        :param uid:
        :return ResourceObject:
        """
        raise NotImplementedError

    def _parse_model_properties(self, model):
        parsed_properties = {}
        for key in self.read_properties:
            parsed_properties[key] = (getattr(model, key, ''), getattr(model, key, ''))
        pass

    def _parse_request_model(self, request):
        model_key = self._get_model_key(request=request)
        return self._get_model(uid=model_key)

    def read_ui(self, request, response):
        signal('read.ui.hook').send(self, request=request, response=response)
        self.parse_status_code(request=request, response=response)

        try:
            model = self._parse_request_model(request=request)
        except KeyError, e:
            logging.exception(e)
            self.set_redirect_url(request=request, response=response, handler='app_default',
                                  status_code=self.key_required_status_code)
            self._parse_redirect(request, response)
        except ValueError, e:
            logging.exception(e)
            self.set_redirect_url(request=request, response=response, handler='app_default',
                                  status_code=self.key_invalid_status_code)
            self._parse_redirect(request, response)
        else:
            response.raw.resource_object = model
            if self.read_properties:
                pass
            response.raw.read_properties = self.read_properties

    def create_ui(self, request, response):
        signal('create.ui.hook').send(self, request=request, response=response)
        self.parse_status_code(request=request, response=response)
        self._parse_model_ui_form(request=request, response=response, form=self.form,
                                  action_method=self.handler_map['create.action'],
                                  disabled_fields=self.disabled_create_properties,
                                  use_get_data=self.force_create_ui_get_data)

    def update_ui(self, request, response):
        signal('update.ui.hook').send(self, request=request, response=response)
        self.parse_status_code(request=request, response=response)

        try:
            model = self._parse_request_model(request=request)
        except KeyError, e:
            logging.exception(e)
            self.set_redirect_url(request=request, response=response, handler='app_default',
                                  status_code=self.key_required_status_code)
            self._parse_redirect(request, response)
        except ValueError, e:
            logging.exception(e)
            self.set_redirect_url(request=request, response=response, handler='app_default',
                                  status_code=self.key_invalid_status_code)
            self._parse_redirect(request, response)
        else:
            self._parse_model_ui_form(request=request, response=response, form=self.form,
                                      existing_model=model, action_method=self.handler_map['update.action'],
                                      disabled_fields=self.disabled_update_properties)

    def delete_ui(self, request, response):
        signal('delete.ui.hook').send(self, request=request, response=response)
        self.parse_status_code(request=request, response=response)

        try:
            model = self._parse_request_model(request=request)
        except KeyError, e:
            logging.exception(e)
            self.set_redirect_url(request=request, response=response, handler='app_default',
                                  status_code=self.key_required_status_code)
            self._parse_redirect(request, response)
        except ValueError, e:
            logging.exception(e)
            self.set_redirect_url(request=request, response=response, handler='app_default',
                                  status_code=self.key_invalid_status_code)
            self._parse_redirect(request, response)
        else:
            response.raw.resource_object = model
            response.raw.read_properties = self.read_properties
            self._parse_model_ui_form(request=request, response=response, form=self.delete_form,
                                      existing_model=model, action_method=self.handler_map['delete.action'])

    def create_callback(self, request, response):
        signal('pre_create.action.hook').send(self, request=request, response=response)

        form = self._generate_form_instance(request=request, form=self.form, form_method=self.form_method,
                                            disabled_fields=self.disabled_create_properties)

        if form.validate():
            try:
                self._do_create(request=request, response=response, form=form)
                signal('valid_create.action.hook').send(self, request=request, response=response, form=form)
            except FormDuplicateValue, e:
                filtered_params = self.filter_unwanted_params(request_params=request.params,
                                                              unwanted=self.filter_params)
                duplicates_query_string = '&'.join('duplicate={}'.format(s) for s in e.duplicates)
                self.set_redirect_url(request=request, response=response, handler='create.ui',
                                      status_code=self.generic_failure_status_code, **filtered_params)
                # This is crude but there isn't an easy means of using webapp2.uri_for with an array for an arg
                response.redirect_to = u'{}&{}'.format(response.redirect_to, duplicates_query_string)
                signal('invalid_create.action.hook').send(self, request=request, response=response)
            else:
                redirect_kwargs = {}
                try:
                    redirect_kwargs['uid'] = response.raw.created_uid
                except AttributeError:
                    pass
                self.set_redirect_url(request=request, response=response, handler='create_success',
                                      status_code=self.create_success_status_code, follow_continue=True,
                                      **redirect_kwargs)

        else:
            filtered_params = self.filter_unwanted_params(request_params=request.params, unwanted=self.filter_params)
            self.set_redirect_url(request=request, response=response, handler='create.ui',
                                  status_code=self.generic_failure_status_code, **filtered_params)
            signal('invalid_create.action.hook').send(self, request=request, response=response)

        self._parse_redirect(request, response)

    def _do_create(self, request, response, form):
        """
        You should define this method to perform the necessary actions for creating a resource from a verified forms
        data.
        :param request:
        :param response:
        :param form:
        :return:
        """
        raise NotImplementedError

    def update_callback(self, request, response):
        signal('pre_update.action.hook').send(self, request=request, response=response)

        form = self._generate_form_instance(request=request, form=self.form, form_method=self.form_method,
                                            disabled_fields=self.disabled_update_properties)

        if form.validate():
            self.set_redirect_url(request=request, response=response, handler='update_success', uid=form.uid.data,
                                  status_code=self.update_success_status_code, follow_continue=True)
            try:
                self._do_update(request=request, response=response, form=form)
                signal('valid_update.action.hook').send(self, request=request, response=response, form=form)
            except FormDuplicateValue, e:
                filtered_params = self.filter_unwanted_params(request_params=request.params,
                                                              unwanted=self.filter_params)
                duplicates_query_string = '&'.join('duplicate={}'.format(s) for s in e.duplicates)
                self.set_redirect_url(request=request, response=response, handler='update.ui',
                                      status_code=self.generic_failure_status_code, **filtered_params)
                # This is crude but there isn't an easy means of using webapp2.uri_for with an array for an arg
                response.redirect_to = u'{}{}'.format(response.redirect_to, duplicates_query_string)
                signal('invalid_update.action.hook').send(self, request=request, response=response)
        else:
            filtered_params = self.filter_unwanted_params(request_params=request.params, unwanted=self.filter_params)
            self.set_redirect_url(request=request, response=response, handler='update.ui',
                                  status_code=self.generic_failure_status_code, **filtered_params)
            signal('invalid_update.action.hook').send(self, request=request, response=response)

        self._parse_redirect(request, response)

    def _do_update(self, request, response, form):
        """
        You should define this method to perform the necessary actions to update a resource from a verified forms data.
        :param request:
        :param response:
        :param form:
        :return:
        """
        raise NotImplementedError

    def delete_callback(self, request, response):
        signal('pre_delete.action.hook').send(self, request=request, response=response)

        form = self._generate_form_instance(request=request, form=self.delete_form, form_method=self.form_method)

        if form.validate():
            self.set_redirect_url(request=request, response=response, handler='delete_success',
                                  status_code=self.delete_success_status_code, follow_continue=True)
            self._do_delete(request=request, response=response, form=form)
            signal('valid_delete.action.hook').send(self, request=request, response=response, form=form)
        else:
            filtered_params = self.filter_unwanted_params(request_params=request.params, unwanted=self.filter_params)
            self.set_redirect_url(request=request, response=response, handler='delete.ui',
                                  status_code=self.generic_failure_status_code, **filtered_params)
            signal('invalid_delete.action.hook').send(self, request=request, response=response)

        self._parse_redirect(request, response)

    def _do_delete(self, request, response, form):
        """
        You should define this method to perform the necessary actions to delete a resource using a verified forms data.
        :param request:
        :param response:
        :param form:
        :return:
        """
        raise NotImplementedError


class SearchHandler(BaseFormHandler):
    """
    search_properties_to_display is a list of search result properties that you want to display. They will be rendered
    in the order that you set in the list. If no list is set then all properties will be displayed in the order that
    they were parsed.
    """
    def __init__(self, search_properties_to_display=None, form=BaseSearchForm, search_handler_map=None,
                 view_full_result_route=None, keep_blank_values=0, force_empty_query=False, **kwargs):
        super(SearchHandler, self).__init__(form=form, **kwargs)

        default_handler_map = {
            'search.ui': 'search.ui',
            'search.action': 'search.action',
        }

        if search_handler_map:
            default_handler_map.update(search_handler_map)

        self.handler_map.update(default_handler_map)
        self.search_properties_to_display = search_properties_to_display
        self.view_full_result_route = view_full_result_route
        self.keep_blank_values = keep_blank_values
        self.force_empty_query = force_empty_query

        self.invalid_search_status_code = self.status_manager.add_status(
            message='Your search was not valid. Please try another one.', status_type='alert')

    def search_ui(self, request, response):
        try:
            signal('search.ui.hook').send(self, request=request, response=response)
        except UIFailed, e:
            # A connector can raise this exception after setting a redirect uri
            self._parse_redirect(request, response)
            return

        self.parse_status_code(request=request, response=response)

        form = self._generate_form_instance(request=request,
                                            form=self.form,
                                            action_url=self.build_handler_url_with_continue_support(request,
                                                                                                    'search.ui'),
                                            formdata=request.GET, form_method=self.form_method)

        if self.force_empty_query or (request.params.get('query', False) is not False) \
                or (response.raw.status_code == self.invalid_search_status_code):
            if form.validate():
                search_results = self._do_search(request=request, response=response, form=form)
                if search_results.cursor:
                    response.raw.search_results_next_link = self.set_query_parameter(url=request.url,
                                                                                     additional_query_params={
                                                                                         'cursor': search_results.cursor},
                                                                                     keep_blank_values=self.keep_blank_values)
                elif request.params.get('cursor', False):
                    response.raw.search_results_final_page = True
                    response.raw.search_results_next_link = self.set_query_parameter(url=request.url,
                                                                                     additional_query_params={
                                                                                         'cursor': ''},
                                                                                     keep_blank_values=self.keep_blank_values)
                response.raw.search_results = search_results
                response.raw.search_properties = self.search_properties_to_display
                response.raw.view_full_result_route = self.view_full_result_route
                response.raw.reset_search_url = self.build_handler_url_with_continue_support(request, 'search.ui')
                signal('valid_search.action.hook').send(self, request=request, response=response, form=form)
            elif not response.raw.status_code:
                self.set_redirect_url(request=request, response=response, handler='search.ui',
                                      status_code=self.invalid_search_status_code)
                signal('invalid_search.action.hook').send(self, request=request, response=response)
                self._parse_redirect(request, response)

        response.raw.form = form

    def _do_search(self, request, response, form):
        """
        You should define this method to perform the necessary actions to search for resources using forms data.
        :param request:
        :param response:
        :param form:
        :return:
        """
        raise NotImplementedError


class HeadlessSearchHandler(BaseFormHandler):
    def __init__(self, search_properties, search_property_map, form=BaseSearchForm, search_handler_map=None,
                 view_full_result_route=None, cancel_text=None, **kwargs):
        super(HeadlessSearchHandler, self).__init__(form=form, **kwargs)

        default_handler_map = {
            'search.ui': 'search.ui',
            'search.action': 'search.action',
        }

        if search_handler_map:
            default_handler_map.update(search_handler_map)

        self.handler_map.update(default_handler_map)
        self.search_properties = search_properties
        self.search_property_map = search_property_map
        self.view_full_result_route = view_full_result_route
        self.cancel_text = cancel_text

        self.invalid_search_status_code = self.status_manager.add_status(
            message='Your search was not valid. Please try another one.', status_type='alert')

    def search_ui(self, request, response):
        try:
            signal('search.ui.hook').send(self, request=request, response=response)
        except UIFailed, e:
            # A connector can raise this exception after setting a redirect uri
            self._parse_redirect(request, response)
            return
        self.parse_status_code(request=request, response=response)

        form = self._generate_form_instance(request=request,
                                            form=self.form,
                                            action_url=self.build_handler_url_with_continue_support(request,
                                                                                                    'search.ui'),
                                            formdata=request.GET, form_method=self.form_method)

        if not form.validate():
            # In theory the sort/filters form should always validate. If it doesn't then you have bad defaults
            # or the user is trying to do some thing you don't want.
            self.set_redirect_url(request=request, response=response, handler='search.ui',
                                  status_code=self.invalid_search_status_code)
            signal('invalid_search.action.hook').send(self, request=request, response=response)
            self._parse_redirect(request, response)

        query = self._build_query_string(request=request, response=response, form=form)

        if not query:
            # This could cause a redirect loop.
            self.set_redirect_url(request=request, response=response, handler='search.ui',
                                  status_code=self.invalid_search_status_code)
            signal('invalid_search.action.hook').send(self, request=request, response=response)
            self._parse_redirect(request, response)

        search_results = self._do_search(request=request, response=response, query=query, form=form)
        if search_results.cursor:
            response.raw.search_results_next_link = self.set_query_parameter(url=request.url,
                                                                             additional_query_params={
                                                                                 'cursor': search_results.cursor})
        elif request.params.get('cursor', False):
            response.raw.search_results_final_page = True
            response.raw.search_results_next_link = self.set_query_parameter(url=request.url,
                                                                             additional_query_params={
                                                                                 'cursor': ''})
        if request.params.get('cancel_uri', False):
            response.raw.cancel_uri = request.params.get('cancel_uri')
            response.raw.cancel_text = self.cancel_text

        response.raw.search_results = search_results
        response.raw.search_properties = self.search_properties
        response.raw.search_name_map = self.search_property_map
        response.raw.view_full_result_route = self.view_full_result_route
        response.raw.reset_search_url = self.build_handler_url_with_continue_support(request, 'search.ui')
        signal('valid_search.action.hook').send(self, request=request, response=response, form=form)

        response.raw.form = form

    def _build_query_string(self, request, response, form):
        """
        You should define this method to format a query string that will be used to search. This is the headless part
        of the handler because they user has no ability to control it, outside of sort, filter options.
        :param request:
        :param response:
        :param form:
        :return:
        """
        raise NotImplementedError

    def _do_search(self, request, response, query, form):
        """
        You should define this method to perform the necessary actions to search for resources using forms data.
        :param request:
        :param response:
        :param form:
        :return:
        """
        raise NotImplementedError


class AutoSearchHandler(BaseHandlerMixin):
    def __init__(self, search_properties, search_property_map, view_full_result_route=None, cancel_text=None, **kwargs):
        super(AutoSearchHandler, self).__init__(**kwargs)

        self.search_properties = search_properties
        self.search_property_map = search_property_map
        self.view_full_result_route = view_full_result_route
        self.cancel_text = cancel_text

        self.invalid_search_status_code = self.status_manager.add_status(
            message='Your search was not valid. Please try another one.', status_type='alert')

    def search_ui(self, request, response):
        try:
            signal('search.ui.hook').send(self, request=request, response=response)
        except UIFailed, e:
            # A connector can raise this exception after setting a redirect uri
            self._parse_redirect(request, response)
            return
        self.parse_status_code(request=request, response=response)

        try:
            query = self._build_query_string(request=request, response=response)
        except ValueError:
            self.set_redirect_url(request=request, response=response, handler='app_default',
                                  status_code=self.invalid_search_status_code)
            signal('invalid_search.action.hook').send(self, request=request, response=response)
            return self._parse_redirect(request, response)

        search_results = self._do_search(request=request, response=response, query=query)
        # TODO: add proper support for cursors without the use of a form
        if search_results.cursor:
            response.raw.search_results_next_link = self.set_query_parameter(url=request.url,
                                                                             additional_query_params={
                                                                                 'cursor': search_results.cursor})
        elif request.params.get('cursor', False):
            response.raw.search_results_final_page = True
            response.raw.search_results_next_link = self.set_query_parameter(url=request.url,
                                                                             additional_query_params={
                                                                                 'cursor': ''})
        if request.params.get('cancel_uri', False):
            response.raw.cancel_uri = request.params.get('cancel_uri')
            response.raw.cancel_text = self.cancel_text

        response.raw.search_results = search_results
        response.raw.search_properties = self.search_properties
        response.raw.search_name_map = self.search_property_map
        response.raw.view_full_result_route = self.view_full_result_route
        signal('valid_search.action.hook').send(self, request=request, response=response)

    def _build_query_string(self, request, response):
        """
        You should define this method to format a query string that will be used to search. This is the headless part
        of the handler because they user has no ability to control it.
        :param request:
        :param response:
        :return:
        """
        raise NotImplementedError

    def _do_search(self, request, response, query):
        """
        You should define this method to perform the necessary actions to search for resources.
        :param request:
        :param response:
        :return:
        """
        raise NotImplementedError
