import re
import json
import urllib
import urllib2
import wtforms
from datetime import datetime
import wtforms.csrf.session as csrf_lib
import webapp2_extras.i18n as i18n
from .utils import STATIC_LANGUAGE_CODES_TUPLE, UK_COUNTY_SET, STATIC_COUNTRY_CODES_SET, STATIC_LANGUAGE_CODES_SET, UK_COUNTIES_TUPLE, STATIC_COUNTRY_LABLES_TUPLE, US_STATES_SET, eu_country

DEFAULT_NONE_VALUE = u'NONE'

BOOLEAN_VALUE_TUPLE = (
    (DEFAULT_NONE_VALUE, u'--'),
    (u'yes', i18n.lazy_gettext(u'Yes')),
    (u'no', i18n.lazy_gettext(u'No')),
)

REQUEST_CONFIG_KEYS = [u'csrf_config']

# These keys are provided by google for testing. They will always validate. NEVER use them in production.
TEST_RECAPTCHA_SITE_KEY = u'6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI'
TEST_RECAPTCHA_SITE_SECRET = u'6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe'


# Constant values to be used in other parts of the package.
FIELD_MAXLENGTH = 50  # intended to stop maliciously long input
ADDRESS_MAXLENGTH = 100
CITY_MAXLENGTH = 40
PHONE_MAXLENGTH = 20

EMAIL_REGEXP = "^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
ALPHANUMERIC_REGEXP = "^\w+$"
MOBILE_REGEXP = "^\+?[0-9-()]{1,20}$"


# === Filters ===
def strip_whitespace_filter(value):
    if value is not None and hasattr(value, 'strip'):
        return value.strip()
    return value


def lowercase_filter(value):
    if value is not None and hasattr(value, 'lower'):
        return value.lower()
    return value
# === End Filters ===


class FormTranslations(object):
    def gettext(self, string):
        return i18n.gettext(string)

    def ngettext(self, singular, plural, n):
        return i18n.ngettext(singular, plural, n)


class LenghtSupportedForm(wtforms.Form):
    def __len__(self):
        return len(self._fields)


class FormField(wtforms.FormField):
    def __len__(self):
        return len(self._fields)


class BaseForm(LenghtSupportedForm):
    """
    BaseForm extends the WTForms implementation and adds in a few config options.

    By default it enables CSRF protection (must pass in config for the CSRF, including where to store the challenge).

    If you provide recaptcha config details then the form will automatically add in the required fields to protect the
    form.
    """
    title = ''

    class Meta:
        csrf = True
        csrf_class = csrf_lib.SessionCSRF

    def __init__(self, request, formdata=None, existing_obj=None, data=None, action_url=None, method=None, **kwargs):
        self.action_url = action_url or ''
        self.method = method
        self.duplicates = []

        if not formdata:
            formdata = request.POST
        else:
            # Check if duplicate values were submitted so that validators can check fields without having to touch a
            # datastore.
            self.duplicates = formdata.getall('duplicate')

        meta_dict = {}

        if self.Meta.csrf:
            if not kwargs.get('csrf', True):
                meta_dict['csrf'] = False
            else:
                if kwargs.get('csrf_context', False):
                    meta_dict['csrf_context'] = kwargs['csrf_context']
                else:
                    meta_dict['csrf_context'] = request.session

                if kwargs.get('csrf_secret', False):
                    meta_dict['csrf_secret'] = kwargs['csrf_secret']

                if kwargs.get('csrf_time_limit', False):
                    meta_dict['csrf_time_limit'] = kwargs['csrf_time_limit']

        # This is used by reCaptcha for validation. Could be used for other validation rules as well
        self.request_headers = {'remote_addr': request.remote_addr}

        recaptcha_site_key = kwargs.get('recaptcha_site_key', False)
        recaptcha_site_secret = kwargs.get('recaptcha_site_secret', False)

        if recaptcha_site_key and recaptcha_site_secret:
            try:
                self.recaptcha2.kwargs.update({'site_key': recaptcha_site_key, 'site_secret': recaptcha_site_secret})
                response_field = getattr(self, u'g-recaptcha-response')
                response_field.kwargs.update({'site_key': recaptcha_site_key, 'site_secret': recaptcha_site_secret})
            except (KeyError, AttributeError):
                pass

        super(BaseForm, self).__init__(formdata=formdata, obj=existing_obj, data=data, meta=meta_dict, **kwargs)

    def _get_translations(self):
        return FormTranslations()


# === Widgets ===
class SelectOptGroups(object):
    """
    Renders a select field.

    If `multiple` is True, then the `size` property should be specified on
    rendering to make the field useful.

    The field must provide an `iter_choices()` method which the widget will
    call on rendering; this method must yield tuples of
    `(value, label, selected)`.
    """
    def __init__(self, multiple=False):
        self.multiple = multiple

    def __call__(self, field, **kwargs):
        kwargs.setdefault('id', field.id)
        if self.multiple:
            kwargs['multiple'] = True
        html = ['<select %s>' % wtforms.widgets.core.html_params(name=field.name, **kwargs)]

        html.append('<option value="default">=== Please select an entry category ===</option>')
        # if form data for this field is empty, get the finished string from memcached
        for category, category_info in field.choices.items():
            html.append('<optgroup label="' + category_info.get('class_name') + '">')
            for award_id, award_info in category_info.get('awards').items():
                cat_id = category+award_id
                html.append(self.render_option(cat_id, award_info.get('award_name'), cat_id == field.data))
            html.append('</optgroup>')
        html.append('</select>')
        return wtforms.widgets.core.HTMLString(''.join(html))

    @classmethod
    def render_option(cls, value, label, selected, **kwargs):
        options = dict(kwargs, value=value)
        if selected:
            options['selected'] = True
        return wtforms.widgets.core.HTMLString('<option %s>%s</option>' % (wtforms.widgets.core.html_params(**options), wtforms.widgets.core.escape(wtforms.compat.text_type(label))))


class ExtendedSelectWidget(wtforms.widgets.core.Select):
    """
    Add support of choices with ``optgroup`` to the ``Select`` widget.
    """
    def __call__(self, field, **kwargs):
        kwargs.setdefault('id', field.id)
        if self.multiple:
            kwargs['multiple'] = True
        html = ['<select %s>' % wtforms.widgets.core.html_params(name=field.name, **kwargs)]
        for item1, item2 in field.choices:
            if isinstance(item2, (list,tuple)):
                group_label = item1
                group_items = item2
                html.append('<optgroup %s>' % wtforms.widgets.core.html_params(label=group_label))
                for inner_val, inner_label in group_items:
                    html.append(self.render_option(inner_val, inner_label, inner_val == field.data))
                html.append('</optgroup>')
            else:
                val = item1
                label = item2
                html.append(self.render_option(val, label, val == field.data))
        html.append('</select>')
        return wtforms.widgets.core.HTMLString(''.join(html))


class ExtendedSelectField(wtforms.fields.core.SelectField):
    """
    Add support of ``optgroup`` grouping to default WTForms' ``SelectField`` class.

    Here is an example of how the data is laid out.

        (
            ('Fruits', (
                ('apple', 'Apple'),
                ('peach', 'Peach'),
                ('pear', 'Pear')
            )),
            ('Vegetables', (
                ('cucumber', 'Cucumber'),
                ('potato', 'Potato'),
                ('tomato', 'Tomato'),
            )),
            ('other','None Of The Above')
        )

    It's a little strange that the tuples are (value, label) except for groups which are (Group Label, list of tuples)
    but this is actually how Django does it too https://docs.djangoproject.com/en/dev/ref/models/fields/#choices

    """
    widget = ExtendedSelectWidget()

    def pre_validate(self, form):
        """
        Don't forget to validate also values from embedded lists.
        """
        for item1, item2 in self.choices:
            if isinstance(item2, (list, tuple)):
                group_label = item1
                group_items = item2
                for val,label in group_items:
                    if val == self.data:
                        return
            else:
                val = item1
                label = item2
                if val == self.data:
                    return
        raise ValueError(self.gettext('Not a valid choice!'))


class Recaptcha2Widget(object):
    """
    This is the widget which displays reCaptcha2 objects. This is used by
    default for the Recaptcha2Field and isn't usually used on its own.
    """

    def __call__(self, field):
        return """
                <script src="https://www.google.com/recaptcha/api.js" async defer></script>
                <div class="g-recaptcha" data-sitekey="{recaptcha_site_key}" style="width: 304px; margin: 0 auto 20px auto;"></div>
                <noscript>
                    <div style="width: 302px; ">
                        <div style="width: 302px; ">
                            <div style="width: 302px; height: 422px;">
                                <iframe src="https://www.google.com/recaptcha/api/fallback?k={recaptcha_site_key}" frameborder="0" scrolling="no" style="width: 302px; height:422px; border-style: none;"></iframe>
                            </div>
                            <div style="width: 300px; border-style: none; bottom: 12px; left: 25px; margin: 0px; padding: 0px; right: 25px; background: #f9f9f9; border: 1px solid #c1c1c1; border-radius: 3px;">
                                <textarea id="g-recaptcha-response" name="g-recaptcha-response" class="g-recaptcha-response" style="width: 250px; height: 40px; border: 1px solid #c1c1c1; margin: 10px 25px; padding: 0px; resize: none;" ></textarea>
                            </div>
                        </div>
                    </div>
                </noscript>""".format(recaptcha_site_key=field.site_key)


class Recaptcha2InputField(wtforms.Field):
    """
    This field represents a reCaptcha field. This uses the RecaptchaWidget
    to show a reCaptcha entry field and will also handle validation for you.
    """

    widget = Recaptcha2Widget()

    def __init__(self, label='', validators=None, site_key=None, site_secret=None, **kwargs):
        """
        Initialize a reCaptcha field. ``site_key`` and ``site_secret``, though
        they appear optional, are in fact required (they are only optional due to
        fields by default having optional arguments).
        """

        # Create the field with the reCaptcha validator, since that
        # is the whole point.
        super(Recaptcha2InputField, self).__init__(label, validators, **kwargs)

        if not site_key or not site_secret:
            raise ValueError(u'You must supply your site key and site secret in order to render a recaptcha field')

        self.site_key = site_key
        self.site_secret = site_secret


class Recaptcha2Validator(object):
    """
    This is a validator for a RecaptchaField. Note that this is typically
    not used directly, since the RecaptchaField automatically adds this
    validator.
    """

    def __init__(self, message=None):
        if not message:
            message = u'Invalid reCaptcha response'

        self.message = message

    def __call__(self, form, field):
        """
        Verify a Google reCAPTCHA 2.0 response.
        """
        endpoint = u"https://www.google.com/recaptcha/api/siteverify"

        recaptcha_params = {
            'secret': field.site_secret,
            'response': field.data,
            'remoteip': form.request_headers.get(u'remote_addr', None),
        }
        recaptcha_params = urllib.urlencode(recaptcha_params)
        request = urllib2.Request(endpoint, recaptcha_params)
        response = urllib2.urlopen(request)
        result = json.load(response)

        if not result['success']:
            error_codes = result.get('error_codes', None)
            if error_codes:
                self.message = u'{0}: {1}'.format(self.message, error_codes)
            raise wtforms.validators.ValidationError(self.message)


class Recaptcha2ResponseField(wtforms.HiddenField):
    """
    This field represents a reCaptcha response. Used to validate the returned value from the reCaptcha service
    """

    def __init__(self, label='', validators=None, site_key=None, site_secret=None, **kwargs):
        super(Recaptcha2ResponseField, self).__init__(label, validators or [Recaptcha2Validator()], **kwargs)

        if not site_key or not site_secret:
            raise ValueError(u'You must supply your site key and site secret in order to render a recaptcha field')

        self.site_key = site_key
        self.site_secret = site_secret


class CheckboxArrayField(wtforms.SelectMultipleField):
    widget = wtforms.widgets.ListWidget(prefix_label=False)
    option_widget = wtforms.widgets.CheckboxInput()

# === End Widgets ===


# === Validators ===
def SecondaryEmailValidation(form, field):
    if len(field.data) > 0:
        regex = re.compile(EMAIL_REGEXP)
        if not regex.match(field.data or ''):
            raise wtforms.validators.ValidationError('Invalid characters found in email address')


def MobileValidator(form, field):
    if field.data:
        regex = re.compile(MOBILE_REGEXP)
        if not regex.match(field.data or ''):
            raise wtforms.validators.ValidationError('Invalid characters found in mobile number')


def USStateValidation(form, field):
    if form.country.data == 'US' and not len(field.data) > 0:
        raise wtforms.validators.ValidationError('State is a required field for US addresses.')
    elif form.country.data == 'US' and field.data not in US_STATES_SET:
        raise wtforms.validators.ValidationError('Please select a valid US state from the list.')


def UKCountyValidation(form, field):
    if form.country.data == 'GB' and not len(field.data) > 0:
        raise wtforms.validators.ValidationError('County is a required field for UK addresses.')
    elif form.country.data == 'GB' and field.data not in UK_COUNTY_SET:
        raise wtforms.validators.ValidationError('Please select a valid UK county from the list.')


def UKPostCodeValidation(form, field):
    if not len(field.data) > 0 and form.country.data == 'GB':
        raise wtforms.validators.ValidationError('Post code is a required field for UK addresses.')


def DeliveryUSStateValidation(form, field):
    if form.delivery_country.data == 'US' and not len(field.data) > 0:
        raise wtforms.validators.ValidationError('Delivery State is a required field for US addresses.')
    elif form.delivery_country.data == 'US' and field.data not in US_STATES_SET:
        raise wtforms.validators.ValidationError('Please select a valid US state from the list.')


def BillingUSStateValidation(form, field):
    if form.billing_country.data == 'US' and not len(field.data) > 0:
        raise wtforms.validators.ValidationError('Billing State is a required field for US addresses.')
    elif form.billing_country.data == 'US' and field.data not in US_STATES_SET:
        raise wtforms.validators.ValidationError('Please select a valid US state from the list.')


def DeliveryUKCountyValidation(form, field):
    if form.delivery_country.data == 'GB' and not len(field.data) > 0:
        raise wtforms.validators.ValidationError('Delivery County is a required field for UK addresses.')
    elif form.delivery_country.data == 'GB' and field.data not in UK_COUNTY_SET:
        raise wtforms.validators.ValidationError('Please select a valid UK county from the list.')


def BillingUKCountyValidation(form, field):
    if form.billing_country.data == 'GB' and not len(field.data) > 0:
        raise wtforms.validators.ValidationError('Billing County is a required field for UK addresses.')
    elif form.billing_country.data == 'GB' and field.data not in UK_COUNTY_SET:
        raise wtforms.validators.ValidationError('Please select a valid UK county from the list.')


def DeliveryUKPostCodeValidation(form, field):
    if not len(field.data) > 0 and form.delivery_country.data == 'GB':
        raise wtforms.validators.ValidationError('Delivery Post code is a required field for UK addresses.')


def BillingUKPostCodeValidation(form, field):
    if not len(field.data) > 0 and form.billing_country.data == 'GB':
        raise wtforms.validators.ValidationError('Billing Post code is a required field for UK addresses.')


def CountryCodeValidation(form, field):
    if len(field.data) > 0:
        if not field.data in STATIC_COUNTRY_CODES_SET:
            raise wtforms.validators.ValidationError('The country you selected is not valid.')


def CountryCodeValidationWithDefaultSupport(form, field):
    if len(field.data) > 0:
        if not field.data in STATIC_COUNTRY_CODES_SET and field.data != DEFAULT_NONE_VALUE:
            raise wtforms.validators.ValidationError('The country you selected is not valid.')


def LanguageCodeValidation(form, field):
    if len(field.data) > 0:
        if not field.data in STATIC_LANGUAGE_CODES_SET:
            raise wtforms.validators.ValidationError('The language you selected is not valid.')


def LanguageCodeValidationWithDefaultSupport(form, field):
    if len(field.data) > 0:
        if not field.data in STATIC_LANGUAGE_CODES_SET and field.data != DEFAULT_NONE_VALUE:
            raise wtforms.validators.ValidationError('The language you selected is not valid.')


def UniqueValueValidation(form, field):
    if field.name in form.duplicates:
        raise wtforms.validators.ValidationError('{} already exists. Please enter a different one.'.format(field.label.text))


def SearchQueryRequired(form, field):
    if not field.data and not (hasattr(form, 'filter_options') and form.filter_options.filter_expressions):
        raise wtforms.validators.ValidationError('Please enter a query or select filters from the advanced options')


def DefaultSelectValidation(form, field):
    if field.data == 'default':
        raise wtforms.validators.ValidationError('Please select a valid option from the list.')


def TaxRegisteredValidation(form, field):
    if form.billing_country.data == 'GB':
        form.not_tax_registered.data = False
    elif not len(field.data) > 0 and eu_country(form.billing_country.data):
        if not form.not_tax_registered.data:
            raise wtforms.validators.ValidationError('You must provide your tax number if you are tax registered.')

# ==== End Validators ====


# ==== Mixins ====
class ReferrerMixin(object):
    referrer = wtforms.fields.HiddenField('referrer')


class BaseModelMixin(object):
    uid = wtforms.fields.HiddenField('uid', validators=[wtforms.validators.InputRequired()])


class TokenMixin(object):
    token = wtforms.fields.HiddenField(validators=[wtforms.validators.InputRequired()])


class TermsAgreedMixin(object):
    terms_agreed = wtforms.fields.BooleanField(
        i18n.lazy_gettext('I confirm that I have read the terms and conditions.'),
        [wtforms.validators.InputRequired(
            i18n.lazy_gettext('Please tick to confirm that you have read the terms and conditions of entry.'))]
        )


class AuthIDMixin(object):
    auth_id = wtforms.fields.StringField(i18n.lazy_gettext('Username or Email Address'), [
        wtforms.validators.InputRequired(),
        wtforms.validators.Length(max=FIELD_MAXLENGTH, message=i18n.lazy_gettext(
            "Field cannot be longer than %(max)d characters.")),
    ])


class UsernameMixin(object):
    username = wtforms.fields.StringField(i18n.lazy_gettext('Username'), [
        wtforms.validators.InputRequired(),
        UniqueValueValidation,
        wtforms.validators.Length(max=FIELD_MAXLENGTH, message=i18n.lazy_gettext(
            "Field cannot be longer than %(max)d characters.")),
    ])


class NameMixin(object):
    first_name = wtforms.fields.StringField(i18n.lazy_gettext('First Name'), [
        wtforms.validators.InputRequired(),
        wtforms.validators.Length(max=FIELD_MAXLENGTH,
                                  message=i18n.lazy_gettext("Field cannot be longer than %(max)d characters.")),
    ])
    last_name = wtforms.fields.StringField(i18n.lazy_gettext('Last Name'), [
        wtforms.validators.InputRequired(),
        wtforms.validators.Length(max=FIELD_MAXLENGTH,
                                  message=i18n.lazy_gettext("Field cannot be longer than %(max)d characters.")),
    ])


class PasswordMixin(object):
    password = wtforms.fields.PasswordField(i18n.lazy_gettext('Password'), [
        wtforms.validators.InputRequired(),
        wtforms.validators.Length(max=FIELD_MAXLENGTH,
                                  message=i18n.lazy_gettext("Field cannot be longer than %(max)d characters."))
    ])


class ConfirmPasswordMixin(PasswordMixin):
    c_password = wtforms.fields.PasswordField(i18n.lazy_gettext('Confirm Password'), [
        wtforms.validators.InputRequired(),
        wtforms.validators.EqualTo('password', i18n.lazy_gettext('Passwords must match.')),
        wtforms.validators.Length(max=FIELD_MAXLENGTH,
                                  message=i18n.lazy_gettext("Field cannot be longer than %(max)d characters."))
    ])


class EmailAddressMixin(object):
    email_address = wtforms.fields.StringField(i18n.lazy_gettext('Email'), [wtforms.validators.InputRequired(),
                                                                            UniqueValueValidation,
                                                                            wtforms.validators.Length(max=FIELD_MAXLENGTH,
                                                                                                      message=i18n.lazy_gettext("Email address must be less than between %(max)d characters long.")),
                                                                            wtforms.validators.regexp(EMAIL_REGEXP,
                                                                                                      flags=re.UNICODE,
                                                                                                      message=i18n.lazy_gettext('Invalid email address.'))])


class LanguagePreferenceMixin(object):
    language_preference = wtforms.fields.SelectField(i18n.lazy_gettext('Preferred Language'), [
        # custom validator to check that value is in list specified.
        LanguageCodeValidation,
        wtforms.validators.InputRequired(),
        wtforms.validators.Length(max=2, message=i18n.lazy_gettext("Language code must be %(max)d characters.")),
    ], choices=STATIC_LANGUAGE_CODES_TUPLE, default='en')


class MobilePhoneMixin(object):
    mobile = wtforms.fields.StringField(i18n.lazy_gettext('Mobile'), [
            wtforms.validators.Length(min=8,
                                      max=15,
                                      message=i18n.lazy_gettext("Mobile number must be between %(min)d and %(max)d characters long.")),
            wtforms.validators.regexp(MOBILE_REGEXP,
                                      message=i18n.lazy_gettext('Invalid characters found in mobile number.'))])


class PhoneMixin(object):
    phone = wtforms.fields.StringField(i18n.lazy_gettext('Phone'), [
            wtforms.validators.InputRequired(),
            wtforms.validators.Length(max=PHONE_MAXLENGTH,
                                      message=i18n.lazy_gettext("Phone number must be less than %(max)d characters long.")),
            wtforms.validators.regexp(MOBILE_REGEXP,
                                      message=i18n.lazy_gettext('Invalid characters found in phone number.'))])


class AddressMixin(object):
    address_1 = wtforms.fields.StringField(i18n.lazy_gettext('Address 1'), [
        wtforms.validators.InputRequired(),
        wtforms.validators.Length(max=ADDRESS_MAXLENGTH,
                                  message=i18n.lazy_gettext("Address 1 cannot be longer than %(max)d characters.")),
    ])
    address_2 = wtforms.fields.StringField(i18n.lazy_gettext('Address 2'), [
        wtforms.validators.Length(max=ADDRESS_MAXLENGTH,
                                  message=i18n.lazy_gettext("Address 2 cannot be longer than %(max)d characters.")),
    ])
    address_3 = wtforms.fields.StringField(i18n.lazy_gettext('Address 3'), [
        wtforms.validators.Length(max=ADDRESS_MAXLENGTH,
                                  message=i18n.lazy_gettext("Address 3 cannot be longer than %(max)d characters.")),
    ])
    city = wtforms.fields.StringField(i18n.lazy_gettext('City'), [
        wtforms.validators.InputRequired(),
        wtforms.validators.Length(max=CITY_MAXLENGTH,
                                  message=i18n.lazy_gettext("City cannot be longer than %(max)d characters.")),
    ])
    state = wtforms.fields.StringField(i18n.lazy_gettext('County/State'), [
        # In theory county will now be an alphanumeric code so length is not required
        # Need to check that US states work when passing to SagePay
        wtforms.validators.Length(max=CITY_MAXLENGTH,
                                  message=i18n.lazy_gettext("County/State cannot be longer than %(max)d characters.")),
    ])
    county = ExtendedSelectField(i18n.lazy_gettext('County (Required for UK companies)'), [
        UKCountyValidation,
    ], choices=UK_COUNTIES_TUPLE)
    post_code = wtforms.fields.StringField(i18n.lazy_gettext('Post Code/Zip Code (Required for UK companies)'), [
        UKPostCodeValidation,
    ])
    country = wtforms.fields.SelectField(i18n.lazy_gettext('Country'), [
        # custom validator to check that value is in list specified.
        CountryCodeValidation,
        wtforms.validators.InputRequired(),
        wtforms.validators.Length(max=2, message=i18n.lazy_gettext("Country code must be %(max)d characters.")),
    ], choices=STATIC_COUNTRY_LABLES_TUPLE, default='GB')


class TwitterMixin(object):
    twitter = wtforms.fields.StringField(i18n.lazy_gettext('Twitter'), [
    ])


class FacebookMixin(object):
    facebook = wtforms.fields.StringField(i18n.lazy_gettext('Facebook'), [
    ])


class WebsiteMixin(object):
    website = wtforms.fields.StringField(i18n.lazy_gettext('Website'), [
    ])


class SocialMediaMixin(FacebookMixin, TwitterMixin, WebsiteMixin):
    pass


class SearchField(object):
    query = wtforms.fields.StringField(i18n.lazy_gettext('Search'), [
        wtforms.validators.InputRequired(),
    ])


class SearchWithFiltersMixin(object):
    query = wtforms.fields.StringField(i18n.lazy_gettext('Search'), [
        SearchQueryRequired,
    ])


class GAESearchLimitMixin(object):
    limit = wtforms.fields.SelectField(i18n.lazy_gettext('Results per page'), [
        wtforms.validators.Length(max=1000, message=i18n.lazy_gettext("The maximum results per page is %(max)d.")),
    ], choices=((u'5', u'5'), (u'20', u'20'), (u'50', u'50'), (u'100', u'100'), (u'250', u'250')), default=u'5')


class SortByPlaceholderMixin(object):
    sort_by = wtforms.fields.SelectField(i18n.lazy_gettext(u'Sort By'), [], choices=((DEFAULT_NONE_VALUE, u'No Sort')),
                                         default=DEFAULT_NONE_VALUE)


class SortDirectionMixin(object):
    sort_direction = wtforms.fields.SelectField(i18n.lazy_gettext('Sort Direction'), [
    ], choices=((u'ASCENDING', u'Ascending'), (u'DESCENDING', u'Descending')), default=u'ASCENDING')


class GAESearchCursorMixin(object):
    cursor = wtforms.fields.HiddenField('cursor', [])


class RecaptchaMixin(object):
    recaptcha2 = Recaptcha2InputField(i18n.lazy_gettext('reCaptcha'), [], )
# Annoyingly we can't set the response field directly as it contains dashes. There is probably a better solution to this
setattr(RecaptchaMixin, u'g-recaptcha-response', Recaptcha2ResponseField(i18n.lazy_gettext('reCaptcha Response'), []))

# ==== End Mixins ====


class BaseModelForm(BaseForm, BaseModelMixin):
    pass


class PlaceholderForm(BaseForm):
    """
    We remove the CSRF protection from the placeholder form; chances are if you are using it then you don't have
    a session mechanism setup, meaning there would be nowhere to save the csrf token for verification.
    """
    class Meta:
        csrf = False

    required_input = wtforms.fields.StringField(label=i18n.lazy_gettext('Required Input'),
                                                default='Here is some text',
                                                validators=[wtforms.validators.InputRequired()])


class LoginForm(BaseForm, AuthIDMixin, PasswordMixin):
    class Meta:
        csrf = False

    title = 'Login'


class ForgottenPasswordForm(BaseForm, AuthIDMixin):
    class Meta:
        csrf = False

    title = 'Forgotten Password Request'


class ResetPasswordForm(BaseForm, ConfirmPasswordMixin, TokenMixin):
    class Meta:
        csrf = False

    title = 'Reset Password'


class DeleteModelForm(BaseForm, BaseModelMixin):
    confirm = wtforms.fields.BooleanField(i18n.lazy_gettext('I confirm that I want to delete this item'),
                                          validators=[wtforms.validators.InputRequired()])


class BaseSortOptionsForm(LenghtSupportedForm):
    """
    Implementors should use this as the basis for creating sort options. Define a custom version using this as
    the base class and then adding any mixins/fields you want. Use the wtforms.FormField enclosure to add it to your
    search form.
    """
    int_fields = []
    date_fields = []


class BaseFilterOptionsForm(LenghtSupportedForm):
    """
    Implementors should use this as the basis for creating filter options. Define a custom version using this as
    the base class and then adding any mixins/fields you want. Use the wtforms.FormField enclosure to add it to your
    search form.
    """
    pass


class BaseSearchForm(BaseForm, SearchWithFiltersMixin):
    class Meta:
        csrf = False


class BaseHeadlessSearchForm(BaseForm, BaseModelMixin):
    class Meta:
        csrf = False

    cancel_uri = wtforms.fields.HiddenField('cancel_uri', validators=[])


class GAESortOptions(BaseSortOptionsForm, GAESearchLimitMixin, SortByPlaceholderMixin, SortDirectionMixin):
    @property
    def sort_expressions(self):
        if self.sort_by.data and self.sort_by.data != DEFAULT_NONE_VALUE:
            default_value = ''
            if self.sort_by.data in self.int_fields:
                default_value = 0
            elif self.sort_by.data in self.date_fields:
                default_value = datetime.now().date()
            return (self.sort_by.data, self.sort_direction.data, default_value),
        else:
            return None


class GAEFilterOptions(BaseFilterOptionsForm):
    @property
    def filter_expressions(self):
        filter_expressions = [(field, value) for field, value in self.data.iteritems() if value and value != DEFAULT_NONE_VALUE]
        return filter_expressions or None


class UserForm(BaseModelForm, NameMixin, UsernameMixin, EmailAddressMixin, ConfirmPasswordMixin,
               LanguagePreferenceMixin, RecaptchaMixin):
    pass


# Example user forms
class UserSortOptions(GAESortOptions):
    sort_by = wtforms.fields.SelectField(i18n.lazy_gettext(u'Sort By'),
                                         [],
                                         choices=(
                                             (u'NONE', i18n.lazy_gettext(u'None')),
                                             (u'username', i18n.lazy_gettext(u'Username')),
                                             (u'first_name', i18n.lazy_gettext(u'First Name')),
                                             (u'last_name', i18n.lazy_gettext(u'Last Name')),
                                             (u'email_address', i18n.lazy_gettext(u'Primary Email')),
                                             (u'recovery_email_address', i18n.lazy_gettext(u'Recovery Email')),
                                             (u'language_preference', i18n.lazy_gettext(u'Language')),
                                             (u'created', i18n.lazy_gettext(u'Registered')),
                                             (u'updated', i18n.lazy_gettext(u'Updated')),
                                         ),
                                         default=DEFAULT_NONE_VALUE)


LANG_LIST = [(DEFAULT_NONE_VALUE, u'--')]
LANG_LIST.extend(list(STATIC_LANGUAGE_CODES_TUPLE))
LANG_TUPLE = tuple(LANG_LIST)


class UserFilterOptions(GAEFilterOptions):
    language_preference = wtforms.fields.SelectField(i18n.lazy_gettext(u'Preferred Language'), [
        LanguageCodeValidationWithDefaultSupport,
    ], choices=LANG_TUPLE, default=DEFAULT_NONE_VALUE)


class UserSearchForm(BaseSearchForm, GAESearchCursorMixin):
    sort_options = FormField(UserSortOptions)
    filter_options = FormField(UserFilterOptions)
