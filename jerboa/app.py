# coding=utf-8
import os
import logging
import inspect
import webapp2
from webob import exc
from blinker import signal
from datetime import datetime, timedelta
from urlparse import urlparse
from google.appengine.api import namespace_manager
from webapp2_extras.routes import RedirectRoute, PathPrefixRoute, MultiRoute
from .forms import PlaceholderForm, BaseSearchForm, DeleteModelForm
from .utils import decode_unicode_request_params, filter_unwanted_params, set_url_query_parameter
from .renderers import Jinja2Renderer


__author__ = 'Matt'


"""
These are the exceptions used by Jerboa. Each inherits from `BaseAppException` so that we can catch them all in the
dispatcher. Generally it is frowned upon to catch such a wide array of errors, but in this case it allows us attempt
a recovery if something happened during a request dispatch.
"""


class BaseAppException(Exception):
    pass


class ApplicationError(BaseAppException):
    # This can be used when something goes wrong when handling a request
    pass


class ClientError(BaseAppException):
    def __init__(self, message, response_code=400):

        # Call the base class constructor with the parameters it needs
        super(ClientError, self).__init__(message)

        # Now for your custom code...
        self.response_code = response_code


class UserLoggedInException(ClientError):
    def __init__(self, message=None, response_code=403):
        if message is None:
            message = 'User cannot be logged in for this operation'
        super(UserLoggedInException, self).__init__(message=message, response_code=response_code)


class InvalidUserException(ClientError):
    def __init__(self, message=None, response_code=403):
        if message is None:
            message = 'Either the user is missing or invalid for this request'
        super(InvalidUserException, self).__init__(message=message, response_code=response_code)


class UnauthorizedUserException(ClientError):
    def __init__(self, message=None, response_code=403):
        if message is None:
            message = 'User is valid but does not have permission to execute this request'
        super(UnauthorizedUserException, self).__init__(message=message, response_code=response_code)


# === Handler Exceptions ===
class InvalidResourceUID(ClientError):
    def __init__(self, message=None, response_code=403, resource_uid=''):
        if message is None:
            message = '`{}` is not a valid resource UID'.format(resource_uid)
        super(InvalidResourceUID, self).__init__(message=message, response_code=response_code)


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


"""
This is the App Registry. It is simply a container object for all of the app routes and handlers. This makes it a little
easier to reference either thing without polluting the global namespace.

Most of the time it would be easier to just use the registry built into webapp2. But if you want to create your own
instance you can.

The reset method is generally only useful when testing.
"""


class AppRegistry(object):
    handlers = {}
    routes = []
    renderers = {}

    def reset(self):
        self.handlers = {}
        self.routes = []
        self.renderers = {}

"""
This is the config parser. It takes a config (example below) and generates routes and handlers, connecting them via
signals.


default_method_definition = {
    'method': {
        'title': None,
        'code_name': None,   # mandatory
        'page_template': '',
        'page_template_type': 'html',
        'login_required': False,
        'prefix_route': True,
        'content_type': 'text/html',
        'remove_form_uid': False,
    },
    'route': {
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
    },
    'handler': {
        'type': StandardUIHandler,
        'success_route': None,
        'failure_route': None,
        # You can include any kwargs required by the handler class here e.g. form
    }
}

The method config keys are added to the route. When a request comes in the route gets added to re request for reference.
By extension you also therefore get the method config in the request. You can use this anywhere that you have access
to the request object.

        e.g. request.route.method_config['title']


By default we don't include any UIDs when redirecting to success handlers. This is to keep things flexible -- there are
many possible actions you could take on a successful form submission.

If you want to include query params in the success url redirect then you will need to set them manually. This is
particularly relevant when using the CRUD generator -- the default is to redirect to 'read' on successful create/update.

    e.g. handler.set_redirect_url(request=request, response=response, route_name=self.success_route,
                                  status_code=self.success_status_code, follow_continue=True, custom_uid=XYZ)
"""


def generate_route(route_config, method_config):
    route_template = route_config['template']
    del route_config['template']

    method_route = RedirectRoute(route_template, **route_config)
    # Attaching this to the actual route instead of the parent route object. Potentially need to move this
    # to be able to use route.method_config
    method_route.method_config = method_config

    return method_config['prefix_route'], method_route


def generate_handler(handler_config):
    handler_type = handler_config['type']
    del handler_config['type']

    return handler_type(**handler_config)


def parse_component_config(resource_config, app_registry, default_login=False, default_template_format='html'):
    for resource, config in resource_config.iteritems():
        resource_routes_prefixed = []
        for method_definition in config['method_definitions']:
            handler_name = '{}_{}'.format(resource, method_definition['method']['code_name'])

            # Parse the default method config
            default_method_config = {
                'title': None,
                'code_name': None,
                'page_template': '',
                'template_format': None,
                'login_required': default_login,
                'prefix_route': True,
                'content_type': 'text/html',
                'remove_form_uid': False,
            }

            try:
                default_method_config.update(method_definition['method'])
            except KeyError:
                pass
            except TypeError:
                # The value was set explicitly to None, so we skip the generation
                pass

            if default_method_config['page_template'] == '':
                if default_method_config['template_format'] is not None:
                    template_format = default_method_config['template_format']
                else:
                    template_format = default_template_format
                # The base template path should be set in your renderer. Therefore we only specify the resource type
                # and the method + file type by default. You can of course specify a custom path in the config.
                default_method_config['page_template'] = '{0}/{1}.{2}'.format(resource,
                                                                              default_method_config['code_name'],
                                                                              template_format)

            # Parse the default route config
            # Template is the method name by default. We automatically prefix with the resource name,
            # unless the config tells us otherwise.
            default_route_config = {
                'template': '/{}'.format(default_method_config['code_name']),
                'handler': default_route_signaler,
                'name': handler_name,
                'strict_slash': True
            }

            try:
                default_route_config.update(method_definition['route'])
            except KeyError:
                # Even if the dict update fails, we still want to generate a route with the default values
                prefixed, method_route = generate_route(route_config=default_route_config,
                                                        method_config=default_method_config)
                if prefixed:
                    resource_routes_prefixed.append(method_route)
                else:
                    app_registry.routes.append(method_route)
            except TypeError:
                # The value was set explicitly to None, so we skip the route generation
                pass
            else:
                # The dict update works so we generate the route with the updated values
                prefixed, method_route = generate_route(route_config=default_route_config,
                                                        method_config=default_method_config)
                if prefixed:
                    resource_routes_prefixed.append(method_route)
                else:
                    app_registry.routes.append(method_route)

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
                # Even if the dict update fails, we still want to generate a handler with the default values
                app_registry.handlers[handler_name] = generate_handler(handler_config=default_handler_config)
            except TypeError:
                # The value was set explicitly to None, so we skip the handler generation
                pass
            else:
                # The dict update works so we generate the handler with the updated values
                app_registry.handlers[handler_name] = generate_handler(handler_config=default_handler_config)

                if default_method_config['remove_form_uid']:
                    # A very common pattern for CRUD will be to have one form and remove the UID field when creating.
                    app_registry.handlers[handler_name].customize_form_hook.connect(remove_form_uid,
                                                                                    sender=app_registry.handlers[handler_name])

        if resource_routes_prefixed:
            # By adding the prefixed routes in one go we group them all together as a single entry. This can give a
            # performance boost to the webapp2 router when parsing requests; if the request does not match the prefix
            # then we can skip all of the routes within it.
            AppRegistry.routes.append(PathPrefixRoute('/{0}'.format(resource), resource_routes_prefixed))


def crud_method_definition_generator(resource_name, form=PlaceholderForm, delete_form=DeleteModelForm,
                                     method_customizations=None):
    """
    It is quite possible that you have to specify enough config for this generator to become redundant. We include it
    to help with prototyping, where you just need to quickly setup routes to demonstrate UI flows.

    `resource_name` is the same as you would supply in the method defintion e.g. user or company

    `form` is the form that should be used for creating and editing a resource

    `method_customizations` is essentially the same as supplying a method definition -- you can override any of the
        values that we set by default below. The format should be exactly the same as normal method definitions, except
        that they should be supplied in a dict with the CRUD method names as keys


    Example method_customization:

    {
        'create': {
            'method': {
                'title': 'Register User',
                'code_name': 'register',
            },
            'handler': {
                'success_route': 'default',
            }
        }

    }

    NOTE: we use 'default' as the success route for each of these methods. This allows us to show a status message,
    without needing to set a UID in the success redirect. The advantage of this is that it allows for fast prototyping.
    You will most likely want to customise this.

    :param resource_name:
    :param form:
    :param delete_form:
    :param method_customizations:
    :type resource_name: str
    :type form: object
    :type delete_form: object
    :type method_customizations: dict of dict(s)
    :return:
    """
    if method_customizations is None:
        method_customizations = {}

    try:
        method_customizations['create']
    except KeyError:
        method_customizations['create'] = {
            'method': {},
            'route': {},
            'handler': {},
        }
    else:
        try:
            method_customizations['create']['method']
        except KeyError:
            method_customizations['create']['method'] = {}
        try:
            method_customizations['create']['route']
        except KeyError:
            method_customizations['create']['route'] = {}
        try:
            method_customizations['create']['handler']
        except KeyError:
            method_customizations['create']['handler'] = {}

    try:
        method_customizations['read']
    except KeyError:
        method_customizations['read'] = {
            'method': {},
            'route': {},
            'handler': {},
        }
    else:
        try:
            method_customizations['read']['method']
        except KeyError:
            method_customizations['read']['method'] = {}
        try:
            method_customizations['read']['route']
        except KeyError:
            method_customizations['read']['route'] = {}
        try:
            method_customizations['read']['handler']
        except KeyError:
            method_customizations['read']['handler'] = {}

    try:
        method_customizations['update']
    except KeyError:
        method_customizations['update'] = {
            'method': {},
            'route': {},
            'handler': {},
        }
    else:
        try:
            method_customizations['update']['method']
        except KeyError:
            method_customizations['update']['method'] = {}
        try:
            method_customizations['update']['route']
        except KeyError:
            method_customizations['update']['route'] = {}
        try:
            method_customizations['update']['handler']
        except KeyError:
            method_customizations['update']['handler'] = {}

    try:
        method_customizations['delete']
    except KeyError:
        method_customizations['delete'] = {
            'method': {},
            'route': {},
            'handler': {},
        }
    else:
        try:
            method_customizations['delete']['method']
        except KeyError:
            method_customizations['delete']['method'] = {}
        try:
            method_customizations['delete']['route']
        except KeyError:
            method_customizations['delete']['route'] = {}
        try:
            method_customizations['delete']['handler']
        except KeyError:
            method_customizations['delete']['handler'] = {}

    create = {
        'method': {
            'title': 'Create {}'.format(resource_name.title()),
            'code_name': 'create',
            'remove_form_uid': True,
        },
        'route': {},
        'handler': {
            'type': StandardFormHandler,
            'form': form,
            'success_route': 'default',
            'success_message': 'Successfully created {}'.format(resource_name.title())
        },
    }
    create['method'].update(method_customizations['create']['method'])
    create['route'].update(method_customizations['create']['route'])
    create['handler'].update(method_customizations['create']['handler'])

    read = {
        'method': {
            'title': 'View {}'.format(resource_name.title()),
            'code_name': 'read',
        },
        'route': {},
        'handler': {
            'type': StandardFormHandler,
            'form': form,
        },
    }
    read['method'].update(method_customizations['read']['method'])
    read['route'].update(method_customizations['read']['route'])
    read['handler'].update(method_customizations['read']['handler'])

    update = {
        'method': {
            'title': 'Update {}'.format(resource_name.title()),
            'code_name': 'update',
        },
        'route': {},
        'handler': {
            'type': StandardFormHandler,
            'form': form,
            'success_route': 'default',
            'success_message': 'Successfully updated {}'.format(resource_name.title())
        },
    }
    update['method'].update(method_customizations['update']['method'])
    update['route'].update(method_customizations['update']['route'])
    update['handler'].update(method_customizations['update']['handler'])

    delete = {
        'method': {
            'title': 'Delete {}'.format(resource_name.title()),
            'code_name': 'delete',
        },
        'route': {},
        'handler': {
            'type': StandardFormHandler,
            'form': delete_form,
            'success_route': 'default',
            'success_message': 'Successfully deleted {}'.format(resource_name.title())
        },
    }
    delete['method'].update(method_customizations['delete']['method'])
    delete['route'].update(method_customizations['delete']['route'])
    delete['handler'].update(method_customizations['delete']['handler'])

    return [
        create,
        read,
        update,
        delete,
    ]


def default_route_signaler(request, response, **kwargs):
    """
    This is the default handler for each of the created routes. When invoked, it sends out a signal. The relevant
    handler can then pick up the signal at process the request. This avoids the need to couple a handler to a route
    directly.
    :param request:
    :param response:
    :param kwargs:
    :return:
    """
    handler_hook_name = u'{}_http_{}'.format(request.route.name, request.method.lower())
    handler_signal = signal(handler_hook_name)

    if bool(handler_signal.receivers):
        # We send request as an arg to avoid having to use a separate 'sender', which would affect the method signatures
        handler_signal.send(request, response=response)
    else:
        logging.debug(u'No handler registered for `{}`'.format(handler_hook_name))


def add_routes(app_instance, route_list):
    """
    Recursive function to add routes to a webapp2 instance.
    :param app_instance:
    :param route_list:
    :return:
    """
    for item in route_list:
        if isinstance(item, (webapp2.Route, MultiRoute)):
            app_instance.router.add(item)
        else:
            add_routes(app_instance=app_instance, route_list=item)


"""
This section contains the custom dispatcher. Very little has actually changed in the way the dispatcher works. The main
difference is that we add the ability to hook into it using signals. These hooks can be used to modify the
request/response.
For example you could add some config values to the request that will be picked up by any connected
handlers. You could also check the authentication status of a request before it even touches a handler.

In addition to the hooks, we add in some app error handling. Essentially, if an error occurs, we just make sure the
correct status code is set, and that there is some debug logging. You can extend this functionality however you see fit
by using the signals that get send out by the exception handlers.
"""


CUSTOM_DISPATCHER_REQUEST_INIT_HOOK = signal('request_init_hook')
CUSTOM_DISPATCHER_RESPONSE_INIT_HOOK = signal('response_init_hook')
CUSTOM_DISPATCHER_PRE_HOOK = signal('pre_dispatch_request_hook')
CUSTOM_DISPATCHER_POST_HOOK = signal('post_dispatch_request_hook')
CUSTOM_DISPATCHER_PRE_PROCESS_RESPONSE_HOOK = signal('pre_process_response_hook')
CUSTOM_DISPATCHER_POST_PROCESS_RESPONSE_HOOK = signal('post_process_response_hook')

# Exception handling
CLIENT_404_HOOK = signal('client_404_hook')
CLIENT_EXCEPTION_HOOK = signal('client_exception_hook')
LOGGED_IN_USER_EXCEPTION_HOOK = signal('logged_in_user_exception_hook')
INVALID_USER_EXCEPTION_HOOK = signal('invalid_user_exception_hook')
UNAUTHORIZED_USER_EXCEPTION_HOOK = signal('unauthorized_user_exception_hook')
APP_EXCEPTION_HOOK = signal('app_exception_hook')
UNHANDLED_EXCEPTION_HOOK = signal('unhandled_exception_hook')


def _handle_exception(exception, request, response, router=None):
    logging.exception('Non specific exception encountered.')

    if bool(UNHANDLED_EXCEPTION_HOOK.receivers):
        UNHANDLED_EXCEPTION_HOOK.send(router or 'custom_dispatcher', exception=exception, request=request, response=response)
    else:
        webapp2.abort(500)


def _handle_app_exception(exception, request, response, router=None):
    logging.exception('Encountered application error.')

    if bool(APP_EXCEPTION_HOOK.receivers):
        APP_EXCEPTION_HOOK.send(router or 'custom_dispatcher', exception=exception, request=request, response=response)
    else:
        webapp2.abort(500)


def _handle_client_exception(exception, request, response, router=None):
    logging.exception('Encountered client error.')

    if bool(CLIENT_EXCEPTION_HOOK.receivers):
        CLIENT_EXCEPTION_HOOK.send(router or 'custom_dispatcher', exception=exception, request=request, response=response)
    else:
        if response.redirect_to:
            webapp2.redirect(uri=response.redirect_to, request=request, response=response)
        else:
            webapp2.abort(400)


def _handle_logged_in_user_exception(exception, request, response, router=None):
    """
    This is a somewhat unique case where we actually want to redirect the user on error, instead of responding with
    the relevant http error code. By default we just redirect them to the default route with an error message.

    :param exception:
    :param request:
    :param response:
    :param router:
    :return:
    """
    logging.exception('Encountered logged in user error; they don\'t need to be here')

    if bool(LOGGED_IN_USER_EXCEPTION_HOOK.receivers):
        LOGGED_IN_USER_EXCEPTION_HOOK.send(router or 'custom_dispatcher', exception=exception, request=request, response=response)
    else:
        redirect_url = webapp2.uri_for('default', status_code=StatusManager.DEFAULT_USER_LOGGED_IN_CODE)
        webapp2.redirect(uri=redirect_url, request=request, response=response)


def _handle_invalid_user_exception(exception, request, response, router=None):
    logging.exception('Encountered invalid user.')

    if bool(INVALID_USER_EXCEPTION_HOOK.receivers):
        INVALID_USER_EXCEPTION_HOOK.send(router or 'custom_dispatcher', exception=exception, request=request, response=response)
    else:
        webapp2.abort(401)


def _handle_unauthorized_user_exception(exception, request, response, router=None):
    logging.exception('Encountered unauthorized user.')

    if bool(UNAUTHORIZED_USER_EXCEPTION_HOOK.receivers):
        UNAUTHORIZED_USER_EXCEPTION_HOOK.send(router or 'custom_dispatcher', exception=exception, request=request, response=response)
    else:
        webapp2.abort(403)


def _handle_404(response, router=None):
    # redirect to a 404 page and give details about what may have happened
    # Send out a signal for the app to hook into

    if bool(CLIENT_404_HOOK.receivers):
        CLIENT_404_HOOK.send(router or 'custom_dispatcher', response=response)
    else:
        webapp2.abort(404)


"""
This is a useful little function that automtically redirects to the default route of the app, assuming that it isn't '/'
"""


def default_route(request, response):
    return webapp2.redirect(webapp2.uri_for(request.settings.get('default_route', section=request.frontend), **request.GET), request=request, response=response)


class CustomHandlerAdapter(webapp2.BaseHandlerAdapter):
    """An adapter for dispatching requests to handler functions.

    The handler is passed both the request and response objects instead of just the request as in BaseHandlerAdapter.
    """

    def __call__(self, request, response):
        # Annoyingly, BaseHandlerAdapter does not pass the response object so we have to override it here.
        return self.handler(request, response)


def custom_adapter(router, handler):
    if inspect.isclass(handler):
        return router.default_adapter(handler)
    else:
        # A "view" function.
        adapter = CustomHandlerAdapter
        return adapter(handler)


def custom_dispatcher(router, request, response, app_instance):
    try:
        rv = router.match(request)
    except exc.HTTPMethodNotAllowed, e:
        logging.exception('HTTP method not allowed for route')
        return _handle_app_exception(exception=e, request=request, response=response, router=router)

    if rv is None:
        logging.exception('Failed to match route.')
        _handle_404(response=response, router=router)

    request.route, request.route_args, request.route_kwargs = rv
    # We add this before passing response to the pre_process hook. That way any connected functions can set response
    # values without having to check it they can or not.
    response.raw = ScratchSpace()

    # Use this hook to set a custom namespace; set request.namespace
    CUSTOM_DISPATCHER_REQUEST_INIT_HOOK.send(router, request=request, app_instance=app_instance)
    CUSTOM_DISPATCHER_RESPONSE_INIT_HOOK.send(router, response=response, app_instance=app_instance)

    current_namespace = namespace_manager.get_namespace()
    try:
        target_namespace = request.namespace
    except AttributeError:
        target_namespace = 'default'

    try:
        if target_namespace != 'default':
            namespace_manager.set_namespace(target_namespace)

        try:
            CUSTOM_DISPATCHER_PRE_HOOK.send(router, request=request, response=response, app_instance=app_instance)
            CUSTOM_DISPATCHER_PRE_PROCESS_RESPONSE_HOOK.send(router, request=request, response=response, app_instance=app_instance)

            router.default_dispatcher(request, response)
        except ApplicationError, e:
            _handle_app_exception(exception=e, request=request, response=response, router=router)
        except UserLoggedInException, e:
            _handle_logged_in_user_exception(exception=e, request=request, response=response, router=router)
        except InvalidUserException, e:
            _handle_invalid_user_exception(exception=e, request=request, response=response, router=router)
        except UnauthorizedUserException, e:
            _handle_unauthorized_user_exception(exception=e, request=request, response=response, router=router)
        except ClientError, e:
            _handle_client_exception(exception=e, request=request, response=response, router=router)
        except BaseAppException, e:
            _handle_exception(exception=e, request=request, response=response, router=router)
        else:
            # We don't want to trigger this hook unless the request was successful.
            CUSTOM_DISPATCHER_POST_HOOK.send(router, request=request, response=response, app_instance=app_instance)
            CUSTOM_DISPATCHER_POST_PROCESS_RESPONSE_HOOK.send(router, request=request, response=response, app_instance=app_instance)

    finally:
        namespace_manager.set_namespace(current_namespace)

    return response


"""
This is a convenience class which removes the need for some of the boilerplate code associated with setting up a Jerboa
app. It takes care of the config parsing, adds the routes, and sets up the custom dispatcher. By default it also tries
to invoke a renderer during the post processing stage of a request.
"""

RENDERER_CONFIG_HOOK = signal('renderer_config_hook')


class JerboaApp(webapp2.WSGIApplication):
    def __init__(self, resource_config, default_login=True, add_default_route=True, debug=None, webapp2_config=None, default_renderer=None):
        if debug is None:
            try:
                debug = os.environ['SERVER_SOFTWARE'].startswith('Dev')
            except KeyError:
                debug = True

        super(JerboaApp, self).__init__(debug=debug, config=webapp2_config)

        self.app_registry = AppRegistry()

        if add_default_route:
            self.router.add(webapp2.Route(template='/', name='default', handler=default_route))

        self.router.set_dispatcher(custom_dispatcher)
        self.router.set_adapter(custom_adapter)
        CUSTOM_DISPATCHER_PRE_PROCESS_RESPONSE_HOOK.connect(set_content_type, sender=self.router)
        CUSTOM_DISPATCHER_PRE_PROCESS_RESPONSE_HOOK.connect(custom_response_headers, sender=self.router)

        self.parse_component_config(resource_config=resource_config, app_registry=self.app_registry,
                                    default_login=default_login)

        if self.app_registry.routes:
            for route in AppRegistry.routes:
                self.router.add(route)

        if default_renderer is not None:
            self.app_registry.renderers['default'] = default_renderer

    parse_component_config = staticmethod(parse_component_config)

    add_routes = add_routes

    def __call__(self, environ, start_response):
        """Called by WSGI when a request comes in.

        Modified version of the default webapp2 method. We send the app instance to the
        dispatch method so that we can properly use signals.

        :param environ:
            A WSGI environment.
        :param start_response:
            A callable accepting a status code, a list of headers and an
            optional exception context to start the response.
        :returns:
            An iterable with the response to return to the client.
        """
        with self.request_context_class(self, environ) as (request, response):
            try:
                if request.method not in self.allowed_methods:
                    # 501 Not Implemented.
                    raise exc.HTTPNotImplemented()

                rv = self.router.dispatch(request, response, app_instance=self)
                if rv is not None:
                    response = rv
            except Exception, e:
                try:
                    # Try to handle it with a custom error handler.
                    rv = self.handle_exception(request, response, e)
                    if rv is not None:
                        response = rv
                except webapp2.HTTPException, e:
                    # Use the HTTP exception as response.
                    response = e
                except Exception, e:
                    # Error wasn't handled so we have nothing else to do.
                    response = self._internal_error(e)

            try:
                return response(environ, start_response)
            except Exception, e:
                return self._internal_error(e)(environ, start_response)


"""
Rather than sending the status message as a GET param, we simply send a status code and then look up the message later.

TODO: we need to add in i18n support
"""


class StatusManager(object):
    DEFAULT_SUCCESS_CODE = '1'
    DEFAULT_FAILURE_CODE = '2'
    DEFAULT_FORM_FAILURE_CODE = '3'
    DEFAULT_USER_LOGGED_IN_CODE = '4'
    DEFAULT_MISSING_KEY = '5'
    DEFAULT_INVALID_KEY = '6'

    statuses = {
        DEFAULT_SUCCESS_CODE: (u'Successfully completed operation', 'success'),
        DEFAULT_FAILURE_CODE: (u'Failed to complete operation.', 'alert'),
        DEFAULT_FORM_FAILURE_CODE: (u'Please correct the errors on the form below.', 'alert'),
        DEFAULT_USER_LOGGED_IN_CODE: (u'You can\'t visit that page as a logged in user.', 'alert'),
        DEFAULT_MISSING_KEY: (u'You must supply a key.', 'alert'),
        DEFAULT_INVALID_KEY: (u'You must supply a valid key.', 'alert'),
    }

    @classmethod
    def add_status(cls, message, status_type):
        new_code = str(len(cls.statuses)+1)
        cls.statuses[new_code] = (message, status_type)
        return new_code


def parse_request_status_code(request, response):
    request_status_code = request.GET.get('status_code', False)
    if not request_status_code:
        response.raw.status_code = 0
        return

    try:
        response.raw.status_message = StatusManager.statuses[request_status_code]
    except KeyError:
        response.raw.status_code = 0
    else:
        response.raw.status_code = request_status_code


"""
Here we define the standard request handlers. There are certain patterns that apply to all apps e.g. UI rendering or
form submission handling. Rather than repeat this code all over the place you can simply use one of the handlers below.

They are designed to trigger signals at key moments during the processing of a request. So for example the form handler
will send a signal once form validation has passed. All you need to do is connect to the signal and do whatever you need
to do with the data. You don't have to worry about checking the form manually. Equally you can choose not to do anything
with the data. This is what makes it very easy, and fast, to prototype in Jerboa.
"""


class BaseHandlerMixin(object):
    """
    The route handling is a little complicated. We want the allow the routes to be configurable via the handler config.
    However, at the time of init, webapp2 has not yet been initialized. This means that we have to accept the webapp2
    route names in the config and then parse them on demand (we cache the result so the overhead is minimal).

    """
    def __init__(self, code_name, success_route=None, failure_route=None, **kwargs):
        self.code_name = code_name
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
        # Be careful with this. Anything in kwargs will be appended as a GET param, apart from the named args to
        # 'get_route_url.
        response.redirect_to = self.get_route_url(**kwargs)

    set_url_query_parameter = staticmethod(set_url_query_parameter)

    @staticmethod
    def _initiate_redirect(request, response):
        webapp2.redirect(uri=response.redirect_to, request=request, response=response)

    @staticmethod
    def valid_url(url):
        """
        Crude url check method that returns a boolean value for valid or not.

        :param url:
        :return:
        """
        try:
            result = urlparse(url)
            return True if result.scheme or result.netloc else False
        except:
            return False


class BaseFormHandler(BaseHandlerMixin):
    def __init__(self, form, form_method='post', filter_params=None, validation_trigger_codes=None, **kwargs):
        super(BaseFormHandler, self).__init__(**kwargs)

        self.filter_params = filter_params

        self.success_status_code = self.status_manager.DEFAULT_SUCCESS_CODE
        self.failure_status_code = self.status_manager.DEFAULT_FORM_FAILURE_CODE
        self.key_required_status_code = self.status_manager.DEFAULT_MISSING_KEY
        self.key_invalid_status_code = self.status_manager.DEFAULT_INVALID_KEY

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


def default_form_csrf_config(sender, request, response, form_config, **kwargs):
    form_config['csrf_context'] = request.environ['beaker.session']
    form_config['csrf_secret'] = request.settings.getbyteliteral('csrf_secret')
    form_config['csrf_time_limit'] = timedelta(minutes=request.settings.getint('csrf_time_limit'))


def default_form_recaptcha_config(sender, request, response, form_config, **kwargs):
    form_config['recaptcha_site_key'] = request.settings.get('recaptcha_site_key')
    form_config['recaptcha_site_secret'] = request.settings.get('recaptcha_site_secret')


def remove_form_uid(handler, request, response, form_instance, hook_name):
    del form_instance.uid


class StandardUIHandler(BaseHandlerMixin):
    UI_HOOK_NAME = 'ui'
    UI_FAILED_HOOK_NAME = 'ui_failed'

    def __init__(self, **kwargs):
        super(StandardUIHandler, self).__init__(**kwargs)
        self.failure_status_code = self.status_manager.DEFAULT_FORM_FAILURE_CODE

        self.ui_hook = signal(self.UI_HOOK_NAME)
        self.ui_failed_hook = signal(self.UI_FAILED_HOOK_NAME)

        signal(u'{}_http_get'.format(self.code_name)).connect(self.ui_handler)

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


"""
The hook names are repeated here with instances of signals. That way, implementors don't need to import blinker
directly; keeps code to a minimum.

We have kept the definitions in the handlers so that you have the option of pickling them. There could be some
interesting experiments with caching to avoid the first load overhead on GAE.
"""
UI_HOOK_NAME = 'ui'
FORM_CONFIG_HOOK_NAME = 'form_config'
CUSTOMIZE_FORM_HOOK_NAME = 'customize_form'
VALID_FORM_HOOK_NAME = 'valid_form'
FORM_ERROR_HOOK_NAME = 'form_error'
DUPLICATE_VALUE_HOOK_NAME = 'duplicate_value'
CALLBACK_FAILED_HOOK_NAME = 'callback_failed'
UI_FAILED_HOOK_NAME = 'ui_failed'
UI_HOOK = signal(UI_HOOK_NAME)
FORM_CONFIG_HOOK = signal(FORM_CONFIG_HOOK_NAME)
CUSTOMIZE_FORM_HOOK = signal(CUSTOMIZE_FORM_HOOK_NAME)
VALID_FORM_HOOK = signal(VALID_FORM_HOOK_NAME)
FORM_ERROR_HOOK = signal(FORM_ERROR_HOOK_NAME)
DUPLICATE_VALUE_HOOK = signal(DUPLICATE_VALUE_HOOK_NAME)
CALLBACK_FAILED_HOOK = signal(CALLBACK_FAILED_HOOK_NAME)
UI_FAILED_HOOK = signal(UI_FAILED_HOOK_NAME)


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
                 force_ui_get_data=False, force_callback_get_data=False, enable_default_csrf=True, **kwargs):
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

        signal(u'{}_http_get'.format(self.code_name)).connect(self.ui_handler)
        signal(u'{}_http_post'.format(self.code_name)).connect(self.callback_handler)
        if enable_default_csrf:
            self.form_config_hook.connect(default_form_csrf_config, sender=self)

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
            formdata = request.GET if validate or self.force_ui_get_data else None

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
        formdata = request.GET if self.force_callback_get_data else None

        form_config = self._build_form_config(request=request, formdata=formdata)

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

        signal(u'{}_http_get'.format(self.code_name)).connect(self.ui_handler)

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


"""
Instead of passing lots of different args to the renderer we can use a scratch space. This is just a simple object that
we set on the response object. You can then set whatever you like in it from your handlers. It just keeps things neater.
You could choose not to use this of course, in which case there is no code to change -- just don't connect the
`retrofit_response` function to the dispatcher.
"""


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


def set_content_type(sender, request, response, **kwargs):
    """
    Designed to be used via a blinker signal, hence the 'sender' arg.

    Adds the content type to the headers. If you want to override this you should change the config that is
    applied to the route. The value supplied in the route config must be a string that can be used for the
    `Content-Type` header.

    :param sender:
    :param request:
    :param response:
    :return:
    """

    try:
        response.headers.add_header('Content-Type', request.route.method_config['content_type'])
    except KeyError:
        # No content type set
        pass
    except AttributeError:
        # No method_config attribute set. This should only ever happen in non-jerboa generated routes e.g. the default
        # handler
        pass


def custom_response_headers(sender, request, response, **kwargs):
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
    except AttributeError:
        # No method_config attribute set. This should only ever happen in non-jerboa generated routes e.g. the default
        # handler
        pass

