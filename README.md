# Jerboa
TODO: update readme with proper description and tutorial

This is still an alpha release. Feel free to use it but please report any problems.

The idea of Jerboa is to reduce the amount of code that you need to write when prototyping an app. The vast majority
of code is usually for request handling and form handling, and is usually boilerplate.

With Jerboa, you can get started simply by specifying some resource method definitions. The request routing and form
handling will be taken care of for you.

# Show Me The Code!

Project structure:
```
.
+-- app.yaml
+-- main.py
+-- jerboa
+-- webapp2
+-- static_assets
|   +-- themes
|   |   +-- example
|   |   |   +-- css
|   |   |   |   +-- app.min.css
|   |   |   +-- js
|   |   |   +-- templates
|   |   |   |   +-- company
|   |   |   |   |   +-- overview.html
|   |   |   |   +-- base.html
```

main.py
```python
# main.py
from jerboa.app import JerboaApp
from jerboa.renderers import Jinja2Renderer
import webapp2

resource_definitions = {
    'company': {
        'method_definitions': [
            {
                'method': {
                    'title': 'Company Overview',
                    'code_name': 'overview',
                },
            },
        ],
    }
}

jinja_config = {
    'type': Jinja2Renderer,
    'environment_args': {
        'extensions': ['jinja2.ext.autoescape', 'jinja2.ext.with_', 'jinja2.ext.i18n', 'jinja2.ext.do'],
        'autoescape': False,
    },
    'theme_base_template_path': 'static_assets/themes/example/templates',
    'enable_i18n': False,
    'global_vars': {
        'app_info': {
            'title': 'Example App',
        },
        'theme': 'example',
        'base_url': '/themes/example',
        'css_url': '/themes/example/css',
        'css_ext': '.min.css',
        'js_url': '/themes/example/js',
        'js_ext': '.min.js',
        'main_css': 'app.min.css',
        'base_layout': 'base.html',
        'uri_for': webapp2.uri_for,
    },
    'filters': {
        # Add and extra filters here
    },
    'tests': {
        # Add any extra tests here
    },
}

my_app = JerboaApp(resource_config=resource_definitions, renderer_config=jinja_config)
```

base.html
```html
<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />

    <link href="{{ main_css }}" rel="stylesheet" />

	<title>{% block page_header_title %}{{ app_info.title }}{{ ' | ' + route_title if route_title else '' }}{% endblock %}</title>

</head>
<body>
    {% block content %}
    <h1>{% block title %}{{ route_title if route_title is defined }}{% endblock title %}</h1>
    <p>Here is some content. You can do pretty much whatever you like here</p>
    {% endblock content %}
</body>
</html>
```

overview.html
```html
{% extends base_layout %}

    {% block content %}
    <h1>Company Overview</h1>
    <p>This is the company overview page</p>
    {% endblock content %}
```

The code above show the basic steps to setup an app that will respond to requests to `/company/overview`.

# Setup

## Resource Definitions

The resource definition starts as a dict:

```python
resource_definitions = {

}
```

Within the dict you define resources, which are also dicts. For example, a `company` resource:

```python
resource_definitions = {
    'company': {
    
    }
}
```

Within the resource dict you define methods. Methods are defined as a list of dicts: 

```python
resource_definitions = {
    'company': {
        'method_definitions': [
            {
                'method': {
                    'title': 'Company Overview',
                    'code_name': 'overview',
                },
            },
        ],
    }
}
```
You might be wondering why the resources are defined as a dict, instead of just directly specifying the list of 
methods. It allows for easy refactoring in the future. If we want to add something else to the resource definition
we can simply add a new dict key without breaking the current config generators and parsers.

TODO: mention defaults and their behaviour e.g. page_templates

### Method Config

Key | Default Value | Type | Description 
--- | --- | --- | --- 
**title** | `None` | string &#124; None | *optional* The method title. This can be used in page templates.
**code_name** | n/a | string | *required* The method code name e.g. `read`. This is combined with the resource name to create the handler name e.g. `company_read`.
**template_format** | `'html'` | string &#124; None | *optional* The page template format (the file extension). If you don't explicitly set a page template, and you don't set `template_format` to `None`, then we use this to generate `page_template`. If you do explicitly set `page_template` then this value is ignored.
**page_template** | `''` | string &#124; None | *optional* The page template that the renderer uses. If explicitly set to `None` then we won't set the template automatically. If set to `''` then we will generate the template path based on the resource name and `code_name` e.g. `company/read.html`.
**login_required** | `False` | boolean | *optional* Simple flag that can be used when processing requests. It doesn't actually do anything by itself.
**prefix_route** | `True` | boolean | *optional* By default, when creating the method routes for a resource we will use `PathPrefixRoute` from `webapp2_extras.routes`. This will group all the routes for a resource and prefix them with the resource name e.g. `/company/read`. This can improve performance if you have a lot of routes as it makes matching faster. Of course sometimes this is not desirable e.g. `/robots.txt`, so you can disable it by setting this config option to `False`.
**content_type** | `'text/html'` | string | *required* Any valid HTTP `content-type` header mime type.
**remove_form_uid** | `False` | boolean | *optional* Generally, you will have one form definition that will be used for both `create` and `update` operations. Usually the only difference between them is a lack of a `UID` field when creating. If this config is set to `True` then we will automatically attempt to remove a `uid` field from the handler form. Part of the method config instead of the handler config as you might want to change this per request.

### Handler Config

The handler config will vary depending on which handler you use. Jerboa has a number of built in handlers and their 
configuration options are described below.

#### BaseHandlerMixin 

Key | Default Value | Type | Description 
--- | --- | --- | --- 
**code_name** | n/a | string | *required* By default this will be taken from the method config, but you may override it here. As with the method config, this will determine the handler name.
**success_route** | `None` | string | *optional* A webapp2 route name e.g. `dashboard_overview`. By default the handler will set this to be itself. Used by form handling methods.
**failure_route** | `None` | string | *optional* A webapp2 route name e.g. `dashboard_overview`. By default the handler will set this to be itself. Mainly used by form handling methods, but may also be used if you trigger an exception.


#### StandardUIHandler
Extends `BaseHandlerMixin` and therefore accepts it's arguments. It does not accept any additional arguments


#### BaseFormHandler
Extends `BaseHandlerMixin` and therefore accepts it's arguments as well

Key | Default Value | Type | Description 
--- | --- | --- | --- 
**form** | n/a | WTForms.BaseForm | *required* A WTForms class (**not** an instance) to be used by the form handler.
**form_method** | `post` | string | *optional* HTTP method for the form submission. Either `get` or `post`.
**filter_params** | `None` | list of strings | *optional* If a form fails to validate then we redirect back to it with the form data as `GET` parameters. This config gives you the option to remove some of the form data. A good example would be to remove sensitive data e.g. passwords. Simply provide a list of form fields e.g. `['password']`.
**validation_trigger_codes** | `None` | list of strings | *optional* By default the handler form will be validated if the form error code -- `03` -- is in the GET request. You may supply additional codes that will trigger the validation e.g. `['10']`. The status codes are returned by the StatusManager class when you add a status message class.


#### StandardFormHandler
Extends `BaseFormHandler`, which extends `BaseHandlerMixin`; accepts both sets of arguments.

Key | Default Value | Type | Description 
--- | --- | --- | --- 
**form** | PlaceholderForm | jerboa.BaseForm | *optional* A WTForms class (**not** an instance). By default this handler provides a placeholder form. The placeholder form has a single checkbox field, which must be checked in order to validate. This allows you to test form handling without having to create a form up front.
**success_message** | `None` | string | *optional* If provided, the handler will register a new status message and use it when a form successfully validates.
**failure_message** | `None` | string | *optional* If provided, the handler will register a new status message and use it when a form fails to validate.
**suppress_success_status** | `False` | boolean | *optional* It may be helpful to suppress success messages. If you set this to `True` then the handler will not append a status code when redirecting on success.
**force_ui_get_data** | `False` | boolean | *optional* If set to `True` then the form will render with any matching `GET` parameters. This can be useful when chaining forms together. 
**force_callback_get_data** | `False` | boolean | *optional* If set to `True` then the form will be parsed with any matching `GET` parameters. This can be useful when chaining forms together. 
**enable_default_csrf** | `True` | boolean | *optional* If set to `True` then the handler will configure the default implementation of the form CSRF protection. For this to work a request will need three values: `csrf_context`, `csrf_secret`, `csrf_time_limit`.


TODO: detail the default CSRF setup and link to `enable_default_csrf` above.
TODO: detail the search handlers


## Renderers
Jerboa uses jinja2 for template rendering by default. It works well with App Engine and it has an easy to learn syntax, making
it ideal for use by designers who perhaps aren't familiar with coding/python. 

A minimal config for jinja2 might look like the following:

```python
from jerboa.renderers import Jinja2Renderer
import webapp2

jinja_config = {
    'type': Jinja2Renderer,
    'environment_args': {
        'extensions': ['jinja2.ext.autoescape', 'jinja2.ext.with_', 'jinja2.ext.i18n', 'jinja2.ext.do'],
        'autoescape': False,
    },
    'theme_base_template_path': 'static_assets/themes/example/templates',
    'enable_i18n': False,
    'global_vars': {
        'theme': 'example',
        'base_url': '/themes/example',
        'css_url': '/themes/example/css',
        'css_ext': '.min.css',
        'js_url': '/themes/example/js',
        'js_ext': '.min.js',
        'main_css': 'app.min.css',
        'base_layout': 'base.html',
        'uri_for': webapp2.uri_for,
    },
    'filters': {
        # Add and extra filters here
    },
    'tests': {
        # Add any extra tests here
    },
}

```
With the exception of the `type` key, these are all standard jinja2 configuration options. `type` refers to a jerboa 
renderer class (found in `renderers.py`). You can extend these or create your own.
If you do create your own, you obviously won't need to use the jinja2 config options.

For more information about how to configure jinja2, refer to the docs at (http://jinja.pocoo.org/docs/dev/api/#basics)

## Create your app

Once you have your resource definitions, and the jinja2 config, you can create the app:

```python
# main.py
from jerboa.app import JerboaApp
from jerboa.renderers import Jinja2Renderer
import webapp2

resource_definitions = {
    'company': {
        'method_definitions': [
            {
                'method': {
                    'title': 'Company Overview',
                    'code_name': 'overview',
                },
            },
        ],
    }
}

jinja_config = {
    'type': Jinja2Renderer,
    'environment_args': {
        'extensions': ['jinja2.ext.autoescape', 'jinja2.ext.with_', 'jinja2.ext.i18n', 'jinja2.ext.do'],
        'autoescape': False,
    },
    'theme_base_template_path': 'static_assets/themes/example/templates',
    'enable_i18n': False,
    'global_vars': {
        'theme': 'example',
        'base_url': '/themes/example',
        'css_url': '/themes/example/css',
        'css_ext': '.min.css',
        'js_url': '/themes/example/js',
        'js_ext': '.min.js',
        'main_css': 'app.min.css',
        'base_layout': 'base.html',
        'uri_for': webapp2.uri_for,
    },
    'filters': {
        # Add and extra filters here
    },
    'tests': {
        # Add any extra tests here
    },
}

my_app = JerboaApp(resource_config=resource_definitions, renderer_config=jinja_config)
```

You can then refer to the app in your `app.yaml` file:

```yaml
...

handlers:
- url: /
  script: main.my_app
  secure: always

- url: /.*
  script: main.my_app
  secure: always

...
```

If you run your project you should have an app that responds to GET requests for `/company/overview`. Assuming you
have also setup a `[THEME_DIR]/company/overview.html` template, you should see the page rendered.