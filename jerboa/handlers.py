# *-* coding: UTF-8 *-*
from __future__ import absolute_import
import logging
import inspect
from google.appengine.api import namespace_manager
from webob import exc
import webapp2
from blinker import signal
from .utils import get_app_config_value
from .exceptions import BaseAppException, ApplicationError, ClientError, InvalidUserException, \
    UnauthorizedUserException, UserLoggedInException


__author__ = 'Matt Badger'


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
        webapp2.abort(400)


def _handle_logged_in_user_exception(exception, request, response, router=None):
    logging.exception('Encountered logged in user error; they don\'t need to be here')

    if bool(LOGGED_IN_USER_EXCEPTION_HOOK.receivers):
        LOGGED_IN_USER_EXCEPTION_HOOK.send(router or 'custom_dispatcher', exception=exception, request=request, response=response)
    else:
        webapp2.abort(401)


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


def default_route(request, response):
    return webapp2.redirect(webapp2.uri_for(request.handler_config['routes']['default'], **request.GET), request=request, response=response)


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


def custom_dispatcher(router, request, response):
    current_namespace = namespace_manager.get_namespace()
    target_namespace = get_app_config_value(config_key='datastore_namespace')

    try:
        if target_namespace != 'default':
            namespace_manager.set_namespace(target_namespace)

        try:
            rv = router.match(request)
        except exc.HTTPMethodNotAllowed, e:
            logging.exception('HTTP method not allowed for route')
            return _handle_app_exception(exception=e, request=request, response=response, router=router)

        if rv is None:
            logging.exception('Failed to match route.')
            _handle_404(response=response, router=router)

        request.route, request.route_args, request.route_kwargs = rv

        try:
            CUSTOM_DISPATCHER_PRE_HOOK.send(router, request=request, response=response)
            CUSTOM_DISPATCHER_PRE_PROCESS_RESPONSE_HOOK.send(router, request=request, response=response)

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
            CUSTOM_DISPATCHER_POST_HOOK.send(router, request=request, response=response)
            CUSTOM_DISPATCHER_POST_PROCESS_RESPONSE_HOOK.send(router, request=request, response=response)

    finally:
        namespace_manager.set_namespace(current_namespace)

    return response
