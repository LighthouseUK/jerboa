# Jerboa
This is still an alpha release. Feel free to use it but please report any problems.

TODO: update readme with proper description and tutorial


# Introduction

The idea of Jerboa is to reduce the amount of code that you need to write when prototyping an app. The vast majority
of code is usually for request handling and form handling, and is usually boilerplate.

With Jerboa, you can get started simply by specifying some resource method definitions. The request routing and form
handling will be taken care of for you.

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