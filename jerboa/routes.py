from webapp2_extras.routes import RedirectRoute, MultiRoute, NamePrefixRoute, PathPrefixRoute

__author__ = 'Matt'


# TODO use this factory to setup a crud route factory
class RouteFactory(object):
    component_type = None
    component_group = None

    def __init__(self, component_type, component_group):
        self.component_type = component_type
        self.component_group = component_group

    @staticmethod
    def route_path_template(route_name, strip_type=True, content_type=None):
        if strip_type:
            return '/{0}'.format(route_name)
        else:
            return '/{0}.{1}'.format(route_name, content_type)

    @staticmethod
    def route_page_template(route_name, content_type, base=None, ):
        if base:
            return '{0}/{1}.{2}'.format(base, route_name, content_type)
        else:
            return '{0}.{1}'.format(route_name, content_type)

    @staticmethod
    def route_base_path(component_group, component_name):
        return '{0}/{1}'.format(component_group, component_name)

    def generate_rendered_route(self, route_name, component_name, **kwargs):
        content_type = kwargs.get('content_type', 'html')
        strip_type = kwargs.get('strip_type', True)

        if not kwargs.get('template', None):
            kwargs['template'] = self.route_path_template(route_name=route_name, strip_type=strip_type, content_type=content_type)
        if not kwargs.get('page_template', None):
            base = self.route_base_path(self.component_group, component_name)

            kwargs['page_template'] = self.route_page_template(route_name=route_name, base=base, content_type=content_type)
        if not kwargs.get('name', None):
            kwargs['name'] = route_name

        new = RenderedRoute(**kwargs)
        return new
        # return RenderedRoute(**kwargs)

    rendered = generate_rendered_route

    def generate_action_route(self, route_name, **kwargs):
        if not kwargs.get('template', None):
            kwargs['template'] = self.route_path_template(route_name=route_name)
        if not kwargs.get('name', None):
            kwargs['name'] = route_name

        kwargs['template'] = '{0}{1}'.format(kwargs['template'], '/callback')
        return ActionRoute(**kwargs)

    action = generate_action_route


# This override allows us to add routes one at a time to the multiroute object.
class RouteGroup(MultiRoute):
    _group_attr = 'name'
    _suffix = 'default'

    def __init__(self, routes=None):
        if not routes:
            routes = []
        super(RouteGroup, self).__init__(routes=routes)

    def add_route(self, route):
        setattr(route, self._group_attr, getattr(route, self._group_attr) + self._suffix)
        self.routes.append(route)

#     TODO method for iterating routes so that we can set attrs, such as step number.


# Name of format 'minion/flow name' . 'action name e.g. insert' . 'ui'
class UIs(RouteGroup):
    _suffix = '.ui'


# Name of format 'minion/flow name' . 'action name e.g. insert' . 'action'
class Actions(RouteGroup):
    _suffix = '.action'

# Might seem unnecessary to append action but it means you can immediately tell what a route does. For example if you
# only need to define an action with no corresponding UI route.


# Couldn't think of a better name to represent a group of routes + handlers. Currently this applies to Minions and Flows
class BaseComponent(object):
    # id = None
    # component_type = None
    # component_group = None
    # route_factory = None
    #
    # raw_routes_prefix = None
    # raw_routes_no_prefix = None
    # routes_prefix = None
    # routes_no_prefix = None

    # routes = None

    # Should really have a base class that minion and flow can extend from to add additional functionality
    route_type_map = {
        'RenderedRoute': 'ui',
        'ActionRoute': 'action',
    }
    route_type_groups = {
        'ui': UIs,
        'action': Actions,
    }

    def __init__(self, name, title, component_type=None, component_group=None, route_factory=None):
        self.name = name
        self.title = title
        if component_type:
            self.component_type = component_type
        if not component_group:
            self.component_group = '{0}s'.format(self.component_type)
        if not route_factory:
            # self.route_factory = RouteFactory()
            # Static instance of route factory
            self.route_factory = RouteFactory(component_type=self.component_type, component_group=self.component_group)
        self.raw_routes_prefix = []
        self.raw_routes_no_prefix = []
        self.routes = None

    def generate_route(self, route_type, route_name, **kwargs):
        """
        Defaults to building a route with the following args using the 'route_name' param:

        template = route_name
        name = route_name
        page_template = 'entity_type.entity_name.route_name'

        """
        if not self.route_factory:
            raise AttributeError

        return getattr(self.route_factory, route_type)(route_name=route_name, component_name=self.name, **kwargs)

    def add_route(self, route_type, route_name, **kwargs):
        new_route = self.generate_route(route_type, route_name, **kwargs)

        if new_route.auto_url_prefix:
            self.raw_routes_prefix.append(new_route)
        else:
            self.raw_routes_no_prefix.append(new_route)

        if self.routes:
            # Setting this to none ensures that any new routes are taken into account by get_routes
            self.routes = None

    def default_process_raw_routes(self):
        routes_prefix = self.group_routes(routes=self.raw_routes_prefix, route_type_map=self.route_type_map, route_type_groups=self.route_type_groups)
        routes_no_prefix = self.group_routes(routes=self.raw_routes_no_prefix, route_type_map=self.route_type_map, route_type_groups=self.route_type_groups)

        routes = []
        if routes_prefix:
            routes.append(PathPrefixRoute('/{0}'.format(self.name), [NamePrefixRoute('{0}.{1}.'.format(self.component_type, self.name), routes_prefix)]))

        if routes_no_prefix:
            routes.append(NamePrefixRoute('{0}.{1}.'.format(self.component_type, self.name), routes_no_prefix))

        self.routes = routes

    process_raw_routes = default_process_raw_routes

    @staticmethod
    def default_group_routes(routes, route_type_map, route_type_groups):
        route_list = []
        group_instances = {}

        for route in routes:
            if not isinstance(route, RedirectRoute):
                # Enforce that all defined routes extend from RedirectRoute to ensure strict slash is used.
                # Also ensures that multiroute objects are not passed. This is important (need to be able to
                # operate on individual route definitions)
                raise ValueError

            group = route_type_map.get(type(route).__name__, None)

            if group:
                existing = group_instances.get(group, None)
                if not existing:
                    group_instances[group] = route_type_groups.get(group, RouteGroup)()
                group_instances[group].add_route(route)
            else:
                route_list.append(route)

        if group_instances:
            # add the route groups to the route list
            route_list.extend(group_instances.values())

        return route_list

    group_routes = default_group_routes

    def get_routes(self):
        if not self.routes and not self.raw_routes_prefix and not self.raw_routes_no_prefix:
            return None
        elif not self.routes:
            self.process_raw_routes()

        return self.routes


# Top level that wraps the routes and prefixes names + paths. Also any public convenience methods?
class Component(BaseComponent):
    component_type = 'component'


# class Flow(BaseComponent):
#     component_type = 'flow'
#
#     def process_raw_routes(self):
#         super(Flow, self).process_raw_routes()
#         # Do whatever we need to do to setup the flow on the routes.
#         total = len(self.routes)
#         routes = self.routes
#
#         class RouteFlow(object):
#             pass
#
#         # Need to take into account routes that may be ui pairs or just single items. Alternately enforce that all
#         # steps are pairs?
#         # debug to see what self.routes looks like at this point - do we have a list of routes or is it nested pairs?
#
#         # At this point we will see PathPrefix routes. How do we drill down to find pairs or singletons?
#         # if route.name in current_group then add the same next and previous
#         """
#         Group name = step e.g. register.step1
#         Group contains ui + action routes e.g. register.step1.ui, register.step1.action
#         Theoretically either of these could be None, but not both
#         """
#         for i in range(0, total):
#             new_flow = RouteFlow()
#
#             new_flow.next_route = routes[i+1] if 1 < total else None
#             new_flow.previous_route = routes[i-1] if i > 0 else None
#             new_flow.step_number = i+1
#
#             routes[i].flow = new_flow


# Extending RedirectRoute to gain the strict slash feature; could write this from scratch instead
# TODO: change the self set properties to a single route_config dict
# This will allow us to easily grab all of the custom properties without having to inspect the instance.
class GovernedRoute(RedirectRoute):
    # add the governor_steps attr to init args + pass through. Call super after init
    def __init__(self, template, handler, handler_method=None, name=None, defaults=None, build_only=False, methods=None,
                 schemes=None, redirect_to=None, redirect_to_name=None, strict_slash=True, governor_steps=None, auto_url_prefix=True, **kwargs):

        self.governor_steps = governor_steps
        self.auto_url_prefix = auto_url_prefix
        # TODO automatically set the login + authorization steps for every route

        super(GovernedRoute, self).__init__(
            template, handler=handler, name=name, defaults=defaults,
            build_only=build_only, handler_method=handler_method, methods=methods,
            schemes=schemes, redirect_to=redirect_to, redirect_to_name=redirect_to_name,
            strict_slash=strict_slash)


class RenderedRoute(GovernedRoute):
    def __init__(self, template, handler, handler_method=None, page_template=None, route_title=None,
                 template_engine='jinja2', disable_page_rendering=False, name=None, defaults=None, build_only=False,
                 methods=None, schemes=None, redirect_to=None, redirect_to_name=None, strict_slash=True,
                 governor_steps=None, content_type='text/html', auto_url_prefix=True, login_required=True, **kwargs):

        self.disable_page_rendering = disable_page_rendering
        self.template_engine = template_engine
        self.page_template = page_template
        self.content_type = content_type
        self.auto_url_prefix = auto_url_prefix
        if not route_title and name:
            self.route_title = name.title()
        else:
            self.route_title = route_title
        self.login_required = login_required

        # TODO set the allowed http methods to get only
        # TODO set default governor steps that apply to all rendered routes e.g. login

        super(RenderedRoute, self).__init__(
            template, handler=handler, name=name, defaults=defaults,
            build_only=build_only, handler_method=handler_method, methods=methods,
            schemes=schemes, redirect_to=redirect_to, redirect_to_name=redirect_to_name,
            strict_slash=strict_slash, governor_steps=governor_steps, auto_url_prefix=auto_url_prefix)


class ActionRoute(GovernedRoute):
    def __init__(self, template, handler, handler_method=None, name=None, defaults=None, build_only=False, methods=None,
                 schemes=None, redirect_to=None, redirect_to_name=None, strict_slash=True, governor_steps=None, auto_url_prefix=True, login_required=True, **kwargs):

        # TODO set the allowed http methods to post only
        # TODO set default governor steps that apply to all actions e.g. login
        self.auto_url_prefix = auto_url_prefix
        self.login_required = login_required

        super(ActionRoute, self).__init__(
            template, handler=handler, name=name, defaults=defaults,
            build_only=build_only, handler_method=handler_method, methods=methods,
            schemes=schemes, redirect_to=redirect_to, redirect_to_name=redirect_to_name,
            strict_slash=strict_slash, governor_steps=governor_steps, auto_url_prefix=auto_url_prefix)
