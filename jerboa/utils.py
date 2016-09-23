# coding=utf-8
import re
import logging
import webapp2
import pytz
import json
from babel import Locale
from webapp2_extras import i18n
import urllib
from urlparse import parse_qs, urlsplit, urlunsplit
from Crypto.Util.asn1 import DerSequence
from binascii import a2b_base64


I18N_LOCALES_KEY = 'i18n_locales'


def filter_unwanted_params(request_params, unwanted=None):
    if not unwanted:
        unwanted = []

    keys_to_keep = set(request_params) - set(unwanted)
    return{k: v for k, v in request_params.iteritems() if k in keys_to_keep}


def filter_params_to_list(request_params, wanted=None):
    if not wanted:
        return []

    keys_to_keep = set(request_params) | set(wanted)
    return[v for k, v in request_params.iteritems() if k in keys_to_keep]


def filter_params_to_dict(request_params, wanted=None):
    if not wanted:
        return []

    keys_to_keep = set(request_params) | set(wanted)
    return{k: v for k, v in request_params.iteritems() if k in keys_to_keep}


def decode_unicode_request_params(params):
    return dict((k, v.encode('utf8')) for k, v in params.items() if v is not None)


def _get_uri_from_request(request):
    """
    The uri returned from request.uri is not properly urlencoded
    (sometimes it's partially urldecoded) This is a weird hack to get
    werkzeug to return the proper urlencoded string uri
    """
    uri = request.host_url

    try:
        uri += request.path
    except AttributeError:
        pass

    if request.query_string:
        uri += '?' + request.query_string.decode('utf-8')
    return uri


def extract_params(request):
    """Extract request params."""

    uri = _get_uri_from_request(request=request)
    http_method = request.method
    headers = dict(request.headers)
    if 'wsgi.input' in headers:
        del headers['wsgi.input']
    if 'wsgi.errors' in headers:
        del headers['wsgi.errors']

    if request.content_type == 'application/json':
        body = {k: v for k, v in json.loads(request.body).iteritems()}
    else:
        body = {k: v for k, v in request.POST.iteritems()}
    return uri, http_method, body, headers


def set_url_query_parameter(url, new_query_params, keep_blank_values=0):
    """Given a URL, set or replace a query parameter and return the
    modified URL.

        set_query_parameter('http://example.com?foo=bar&biz=baz', {'foo', 'stuff'})

        'http://example.com?foo=stuff&biz=baz'

    Solution originally from: http://stackoverflow.com/a/12897375
    :param url:
    :param new_query_params:
    """
    scheme, netloc, path, query_string, fragment = urlsplit(url)
    query_params = parse_qs(query_string, keep_blank_values=keep_blank_values)

    for param_name, param_value in new_query_params.iteritems():
        query_params[param_name] = [param_value]
    new_query_string = urllib.urlencode(query_params, doseq=True)

    return urlunsplit((scheme, netloc, path, new_query_string, fragment))


def convert_pem_to_rsa_string(pem):
    # Convert from PEM to DER
    lines = pem.replace(" ", '').split()
    der = a2b_base64(''.join(lines[1:-1]))

    # Extract subjectPublicKeyInfo field from X.509 certificate (see RFC3280)
    cert = DerSequence()
    cert.decode(der)
    tbsCertificate = DerSequence()
    tbsCertificate.decode(cert[0])
    return tbsCertificate[6]
    # Alternately you could return an actual RSA key instance
    # Initialize RSA key
    # rsa_key = RSA.importKey(subjectPublicKeyInfo)
    # return rsa_key


# Loading pycountry was annoying me with all of it's debug messages. As the data is relatively static it makes sense to
# hard code it.
STATIC_COUNTRY_LABLES_TUPLE = (
    (u'AF', u'Afghanistan'), (u'AX', u'\xc5land Islands'), (u'AL', u'Albania'), (u'DZ', u'Algeria'),
    (u'AS', u'American Samoa'), (u'AD', u'Andorra'), (u'AO', u'Angola'), (u'AI', u'Anguilla'),
    (u'AQ', u'Antarctica'), (u'AG', u'Antigua and Barbuda'), (u'AR', u'Argentina'),
    (u'AM', u'Armenia'), (u'AW', u'Aruba'), (u'AU', u'Australia'), (u'AT', u'Austria'),
    (u'AZ', u'Azerbaijan'), (u'BS', u'Bahamas'), (u'BH', u'Bahrain'), (u'BD', u'Bangladesh'),
    (u'BB', u'Barbados'), (u'BY', u'Belarus'), (u'BE', u'Belgium'), (u'BZ', u'Belize'),
    (u'BJ', u'Benin'), (u'BM', u'Bermuda'), (u'BT', u'Bhutan'),
    (u'BO', u'Bolivia, Plurinational State of'), (u'BQ', u'Bonaire, Sint Eustatius and Saba'),
    (u'BA', u'Bosnia and Herzegovina'), (u'BW', u'Botswana'), (u'BV', u'Bouvet Island'),
    (u'BR', u'Brazil'), (u'IO', u'British Indian Ocean Territory'), (u'BN', u'Brunei Darussalam'),
    (u'BG', u'Bulgaria'), (u'BF', u'Burkina Faso'), (u'BI', u'Burundi'), (u'KH', u'Cambodia'),
    (u'CM', u'Cameroon'), (u'CA', u'Canada'), (u'CV', u'Cape Verde'), (u'KY', u'Cayman Islands'),
    (u'CF', u'Central African Republic'), (u'TD', u'Chad'), (u'CL', u'Chile'), (u'CN', u'China'),
    (u'CX', u'Christmas Island'), (u'CC', u'Cocos (Keeling) Islands'), (u'CO', u'Colombia'),
    (u'KM', u'Comoros'), (u'CG', u'Congo'), (u'CD', u'Congo, The Democratic Republic of the'),
    (u'CK', u'Cook Islands'), (u'CR', u'Costa Rica'), (u'CI', u"C\xf4te d'Ivoire"),
    (u'HR', u'Croatia'), (u'CU', u'Cuba'), (u'CW', u'Cura\xe7ao'), (u'CY', u'Cyprus'),
    (u'CZ', u'Czech Republic'), (u'DK', u'Denmark'), (u'DJ', u'Djibouti'), (u'DM', u'Dominica'),
    (u'DO', u'Dominican Republic'), (u'EC', u'Ecuador'), (u'EG', u'Egypt'), (u'SV', u'El Salvador'),
    (u'GQ', u'Equatorial Guinea'), (u'ER', u'Eritrea'), (u'EE', u'Estonia'), (u'ET', u'Ethiopia'),
    (u'FK', u'Falkland Islands (Malvinas)'), (u'FO', u'Faroe Islands'), (u'FJ', u'Fiji'),
    (u'FI', u'Finland'), (u'FR', u'France'), (u'GF', u'French Guiana'), (u'PF', u'French Polynesia'),
    (u'TF', u'French Southern Territories'), (u'GA', u'Gabon'), (u'GM', u'Gambia'),
    (u'GE', u'Georgia'), (u'DE', u'Germany'), (u'GH', u'Ghana'), (u'GI', u'Gibraltar'),
    (u'GR', u'Greece'), (u'GL', u'Greenland'), (u'GD', u'Grenada'), (u'GP', u'Guadeloupe'),
    (u'GU', u'Guam'), (u'GT', u'Guatemala'), (u'GG', u'Guernsey'), (u'GN', u'Guinea'),
    (u'GW', u'Guinea-Bissau'), (u'GY', u'Guyana'), (u'HT', u'Haiti'),
    (u'HM', u'Heard Island and McDonald Islands'), (u'VA', u'Holy See (Vatican City State)'),
    (u'HN', u'Honduras'), (u'HK', u'Hong Kong'), (u'HU', u'Hungary'), (u'IS', u'Iceland'),
    (u'IN', u'India'), (u'ID', u'Indonesia'), (u'IR', u'Iran, Islamic Republic of'),
    (u'IQ', u'Iraq'), (u'IE', u'Ireland'), (u'IM', u'Isle of Man'), (u'IL', u'Israel'),
    (u'IT', u'Italy'), (u'JM', u'Jamaica'), (u'JP', u'Japan'), (u'JE', u'Jersey'),
    (u'JO', u'Jordan'), (u'KZ', u'Kazakhstan'), (u'KE', u'Kenya'), (u'KI', u'Kiribati'),
    (u'KP', u"Korea, Democratic People's Republic of"), (u'KR', u'Korea, Republic of'),
    (u'KW', u'Kuwait'), (u'KG', u'Kyrgyzstan'), (u'LA', u"Lao People's Democratic Republic"),
    (u'LV', u'Latvia'), (u'LB', u'Lebanon'), (u'LS', u'Lesotho'), (u'LR', u'Liberia'),
    (u'LY', u'Libya'), (u'LI', u'Liechtenstein'), (u'LT', u'Lithuania'), (u'LU', u'Luxembourg'),
    (u'MO', u'Macao'), (u'MK', u'Macedonia, Republic of'), (u'MG', u'Madagascar'),
    (u'MW', u'Malawi'), (u'MY', u'Malaysia'), (u'MV', u'Maldives'), (u'ML', u'Mali'),
    (u'MT', u'Malta'), (u'MH', u'Marshall Islands'), (u'MQ', u'Martinique'), (u'MR', u'Mauritania'),
    (u'MU', u'Mauritius'), (u'YT', u'Mayotte'), (u'MX', u'Mexico'),
    (u'FM', u'Micronesia, Federated States of'), (u'MD', u'Moldova, Republic of'),
    (u'MC', u'Monaco'), (u'MN', u'Mongolia'), (u'ME', u'Montenegro'), (u'MS', u'Montserrat'),
    (u'MA', u'Morocco'), (u'MZ', u'Mozambique'), (u'MM', u'Myanmar'), (u'NA', u'Namibia'),
    (u'NR', u'Nauru'), (u'NP', u'Nepal'), (u'NL', u'Netherlands'), (u'NC', u'New Caledonia'),
    (u'NZ', u'New Zealand'), (u'NI', u'Nicaragua'), (u'NE', u'Niger'), (u'NG', u'Nigeria'),
    (u'NU', u'Niue'), (u'NF', u'Norfolk Island'), (u'MP', u'Northern Mariana Islands'),
    (u'NO', u'Norway'), (u'OM', u'Oman'), (u'PK', u'Pakistan'), (u'PW', u'Palau'),
    (u'PS', u'Palestine, State of'), (u'PA', u'Panama'), (u'PG', u'Papua New Guinea'),
    (u'PY', u'Paraguay'), (u'PE', u'Peru'), (u'PH', u'Philippines'), (u'PN', u'Pitcairn'),
    (u'PL', u'Poland'), (u'PT', u'Portugal'), (u'PR', u'Puerto Rico'), (u'QA', u'Qatar'),
    (u'RE', u'R\xe9union'), (u'RO', u'Romania'), (u'RU', u'Russian Federation'), (u'RW', u'Rwanda'),
    (u'BL', u'Saint Barth\xe9lemy'), (u'SH', u'Saint Helena, Ascension and Tristan da Cunha'),
    (u'KN', u'Saint Kitts and Nevis'), (u'LC', u'Saint Lucia'),
    (u'MF', u'Saint Martin (French part)'), (u'PM', u'Saint Pierre and Miquelon'),
    (u'VC', u'Saint Vincent and the Grenadines'), (u'WS', u'Samoa'), (u'SM', u'San Marino'),
    (u'ST', u'Sao Tome and Principe'), (u'SA', u'Saudi Arabia'), (u'SN', u'Senegal'),
    (u'RS', u'Serbia'), (u'SC', u'Seychelles'), (u'SL', u'Sierra Leone'), (u'SG', u'Singapore'),
    (u'SX', u'Sint Maarten (Dutch part)'), (u'SK', u'Slovakia'), (u'SI', u'Slovenia'),
    (u'SB', u'Solomon Islands'), (u'SO', u'Somalia'), (u'ZA', u'South Africa'),
    (u'GS', u'South Georgia and the South Sandwich Islands'), (u'ES', u'Spain'),
    (u'LK', u'Sri Lanka'), (u'SD', u'Sudan'), (u'SR', u'Suriname'), (u'SS', u'South Sudan'),
    (u'SJ', u'Svalbard and Jan Mayen'), (u'SZ', u'Swaziland'), (u'SE', u'Sweden'),
    (u'CH', u'Switzerland'), (u'SY', u'Syrian Arab Republic'), (u'TW', u'Taiwan, Province of China'),
    (u'TJ', u'Tajikistan'), (u'TZ', u'Tanzania, United Republic of'), (u'TH', u'Thailand'),
    (u'TL', u'Timor-Leste'), (u'TG', u'Togo'), (u'TK', u'Tokelau'), (u'TO', u'Tonga'),
    (u'TT', u'Trinidad and Tobago'), (u'TN', u'Tunisia'), (u'TR', u'Turkey'),
    (u'TM', u'Turkmenistan'), (u'TC', u'Turks and Caicos Islands'), (u'TV', u'Tuvalu'),
    (u'UG', u'Uganda'), (u'UA', u'Ukraine'), (u'AE', u'United Arab Emirates'),
    (u'GB', u'United Kingdom'), (u'US', u'United States'),
    (u'UM', u'United States Minor Outlying Islands'), (u'UY', u'Uruguay'), (u'UZ', u'Uzbekistan'),
    (u'VU', u'Vanuatu'), (u'VE', u'Venezuela, Bolivarian Republic of'), (u'VN', u'Viet Nam'),
    (u'VG', u'Virgin Islands, British'), (u'VI', u'Virgin Islands, U.S.'),
    (u'WF', u'Wallis and Futuna'), (u'EH', u'Western Sahara'), (u'YE', u'Yemen'), (u'ZM', u'Zambia'),
    (u'ZW', u'Zimbabwe')
)

STATIC_COUNTRY_CODES_SET = {
    u'YE', u'LK', u'LI', u'DZ', u'LC', u'LA', u'DE', u'SN', u'YT', u'LY', u'LV', u'DO', u'LT', u'DM', u'DJ', u'DK',
    u'TF', u'TG', u'TD', u'TC', u'TN', u'TO', u'TL', u'TM', u'TJ', u'TK', u'TH', u'TV', u'TW', u'TT', u'TR', u'TZ',
    u'VU', u'GY', u'GW', u'LB', u'GU', u'GT', u'GS', u'GR', u'GQ', u'GP', u'GN', u'GM', u'GL', u'GI', u'GH', u'GG',
    u'GF', u'GE', u'GD', u'GB', u'GA', u'WF', u'ZM', u'OM', u'WS', u'BD', u'BE', u'BF', u'BG', u'BA', u'BB', u'ML',
    u'BL', u'BM', u'BN', u'BO', u'BH', u'BI', u'BJ', u'BT', u'BV', u'BW', u'BQ', u'BR', u'BS', u'BY', u'BZ', u'LU',
    u'ES', u'LR', u'RS', u'JP', u'LS', u'JM', u'JO', u'JE', u'MM', u'ET', u'MO', u'MN', u'MH', u'MK', u'ER', u'ME',
    u'MD', u'MG', u'MF', u'MA', u'ZA', u'MC', u'EE', u'RE', u'EG', u'MY', u'MX', u'EC', u'MZ', u'MU', u'MT', u'MW',
    u'MV', u'MQ', u'MP', u'MS', u'MR', u'SJ', u'UG', u'UA', u'PL', u'UM', u'PM', u'US', u'RU', u'UY', u'UZ', u'SR',
    u'ZW', u'HR', u'PK', u'PH', u'RO', u'PN', u'HT', u'HU', u'PA', u'PF', u'PG', u'PE', u'PY', u'SZ', u'PR', u'HK',
    u'HN', u'PW', u'PT', u'HM', u'CC', u'CA', u'SX', u'CG', u'CF', u'CD', u'CK', u'CI', u'CH', u'CO', u'CN', u'CM',
    u'CL', u'CR', u'EH', u'CW', u'CV', u'CU', u'PS', u'CZ', u'CY', u'CX', u'KZ', u'KY', u'SB', u'KR', u'KP', u'KW',
    u'SA', u'KI', u'KH', u'KN', u'KM', u'KG', u'KE', u'SS', u'NI', u'FR', u'NL', u'SV', u'NO', u'NA', u'SY', u'NC',
    u'NE', u'NF', u'NG', u'SC', u'SK', u'NZ', u'SG', u'SE', u'SD', u'NP', u'FI', u'FJ', u'FK', u'SO', u'FM', u'SM',
    u'FO', u'VA', u'SI', u'SH', u'VE', u'VG', u'VI', u'VN', u'NU', u'NR', u'SL', u'AX', u'AZ', u'ST', u'AQ', u'AS',
    u'AR', u'AU', u'AT', u'AW', u'AI', u'VC', u'AM', u'AL', u'AO', u'AE', u'AD', u'AG', u'AF', u'IQ', u'IS', u'IR',
    u'IT', u'QA', u'RW', u'IE', u'ID', u'IM', u'IL', u'IO', u'IN'
}


STATIC_LANGUAGE_CODES_TUPLE = (
    (u'aa', u'Afar'),
    (u'ab', u'Abkhazian'),
    (u'af', u'Afrikaans'),
    (u'ak', u'Akan'),
    (u'sq', u'Albanian'),
    (u'am', u'Amharic'),
    (u'ar', u'Arabic'),
    (u'an', u'Aragonese'),
    (u'hy', u'Armenian'),
    (u'as', u'Assamese'),
    (u'av', u'Avaric'),
    (u'ae', u'Avestan'),
    (u'ay', u'Aymara'),
    (u'az', u'Azerbaijani'),
    (u'ba', u'Bashkir'),
    (u'bm', u'Bambara'),
    (u'eu', u'Basque'),
    (u'be', u'Belarusian'),
    (u'bn', u'Bengali'),
    (u'bh', u'Bihari languages'),
    (u'bi', u'Bislama'),
    (u'bo', u'Tibetan'),
    (u'bs', u'Bosnian'),
    (u'br', u'Breton'),
    (u'bg', u'Bulgarian'),
    (u'my', u'Burmese'),
    (u'ca', u'Catalan; Valencian'),
    (u'cs', u'Czech'),
    (u'ch', u'Chamorro'),
    (u'ce', u'Chechen'),
    (u'zh', u'Chinese'),
    (u'cu', u'Church Slavic; Old Slavonic; Church Slavonic; Old Bulgarian; Old Church Slavonic'),
    (u'cv', u'Chuvash'),
    (u'kw', u'Cornish'),
    (u'co', u'Corsican'),
    (u'cr', u'Cree'),
    (u'cy', u'Welsh'),
    (u'cs', u'Czech'),
    (u'da', u'Danish'),
    (u'de', u'German'),
    (u'dv', u'Divehi; Dhivehi; Maldivian'),
    (u'nl', u'Dutch; Flemish'),
    (u'dz', u'Dzongkha'),
    (u'el', u'Greek, Modern (1453-)'),
    (u'en', u'English'),
    (u'eo', u'Esperanto'),
    (u'et', u'Estonian'),
    (u'eu', u'Basque'),
    (u'ee', u'Ewe'),
    (u'fo', u'Faroese'),
    (u'fa', u'Persian'),
    (u'fj', u'Fijian'),
    (u'fi', u'Finnish'),
    (u'fr', u'French'),
    (u'fr', u'French'),
    (u'fy', u'Western Frisian'),
    (u'ff', u'Fulah'),
    (u'Ga', u'Georgian'),
    (u'de', u'German'),
    (u'gd', u'Gaelic; Scottish Gaelic'),
    (u'ga', u'Irish'),
    (u'gl', u'Galician'),
    (u'gv', u'Manx'),
    (u'el', u'Greek, Modern (1453-)'),
    (u'gn', u'Guarani'),
    (u'gu', u'Gujarati'),
    (u'ht', u'Haitian; Haitian Creole'),
    (u'ha', u'Hausa'),
    (u'he', u'Hebrew'),
    (u'hz', u'Herero'),
    (u'hi', u'Hindi'),
    (u'ho', u'Hiri Motu'),
    (u'hr', u'Croatian'),
    (u'hu', u'Hungarian'),
    (u'hy', u'Armenian'),
    (u'ig', u'Igbo'),
    (u'is', u'Icelandic'),
    (u'io', u'Ido'),
    (u'ii', u'Sichuan Yi; Nuosu'),
    (u'iu', u'Inuktitut'),
    (u'ie', u'Interlingue; Occidental'),
    (u'ia', u'Interlingua (International Auxiliary Language Association)'),
    (u'id', u'Indonesian'),
    (u'ik', u'Inupiaq'),
    (u'is', u'Icelandic'),
    (u'it', u'Italian'),
    (u'jv', u'Javanese'),
    (u'ja', u'Japanese'),
    (u'kl', u'Kalaallisut; Greenlandic'),
    (u'kn', u'Kannada'),
    (u'ks', u'Kashmiri'),
    (u'ka', u'Georgian'),
    (u'kr', u'Kanuri'),
    (u'kk', u'Kazakh'),
    (u'km', u'Central Khmer'),
    (u'ki', u'Kikuyu; Gikuyu'),
    (u'rw', u'Kinyarwanda'),
    (u'ky', u'Kirghiz; Kyrgyz'),
    (u'kv', u'Komi'),
    (u'kg', u'Kongo'),
    (u'ko', u'Korean'),
    (u'kj', u'Kuanyama; Kwanyama'),
    (u'ku', u'Kurdish'),
    (u'lo', u'Lao'),
    (u'la', u'Latin'),
    (u'lv', u'Latvian'),
    (u'li', u'Limburgan; Limburger; Limburgish'),
    (u'ln', u'Lingala'),
    (u'lt', u'Lithuanian'),
    (u'lb', u'Luxembourgish; Letzeburgesch'),
    (u'lu', u'Luba-Katanga'),
    (u'lg', u'Ganda'),
    (u'mk', u'Macedonian'),
    (u'mh', u'Marshallese'),
    (u'ml', u'Malayalam'),
    (u'mi', u'Maori'),
    (u'mr', u'Marathi'),
    (u'ms', u'Malay'),
    (u'Mi', u'Micmac'),
    (u'mk', u'Macedonian'),
    (u'mg', u'Malagasy'),
    (u'mt', u'Maltese'),
    (u'mn', u'Mongolian'),
    (u'mi', u'Maori'),
    (u'ms', u'Malay'),
    (u'my', u'Burmese'),
    (u'na', u'Nauru'),
    (u'nv', u'Navajo; Navaho'),
    (u'nr', u'Ndebele, South; South Ndebele'),
    (u'nd', u'Ndebele, North; North Ndebele'),
    (u'ng', u'Ndonga'),
    (u'ne', u'Nepali'),
    (u'nl', u'Dutch; Flemish'),
    (u'nn', u'Norwegian Nynorsk; Nynorsk, Norwegian'),
    (u'nb', u'BokmÃ¥l, Norwegian; Norwegian BokmÃ¥l'),
    (u'no', u'Norwegian'),
    (u'oc', u'Occitan (post 1500)'),
    (u'oj', u'Ojibwa'),
    (u'or', u'Oriya'),
    (u'om', u'Oromo'),
    (u'os', u'Ossetian; Ossetic'),
    (u'pa', u'Panjabi; Punjabi'),
    (u'fa', u'Persian'),
    (u'pi', u'Pali'),
    (u'pl', u'Polish'),
    (u'pt', u'Portuguese'),
    (u'ps', u'Pushto; Pashto'),
    (u'qu', u'Quechua'),
    (u'rm', u'Romansh'),
    (u'ro', u'Romanian; Moldavian; Moldovan'),
    (u'ro', u'Romanian; Moldavian; Moldovan'),
    (u'rn', u'Rundi'),
    (u'ru', u'Russian'),
    (u'sg', u'Sango'),
    (u'sa', u'Sanskrit'),
    (u'si', u'Sinhala; Sinhalese'),
    (u'sk', u'Slovak'),
    (u'sk', u'Slovak'),
    (u'sl', u'Slovenian'),
    (u'se', u'Northern Sami'),
    (u'sm', u'Samoan'),
    (u'sn', u'Shona'),
    (u'sd', u'Sindhi'),
    (u'so', u'Somali'),
    (u'st', u'Sotho, Southern'),
    (u'es', u'Spanish; Castilian'),
    (u'sq', u'Albanian'),
    (u'sc', u'Sardinian'),
    (u'sr', u'Serbian'),
    (u'ss', u'Swati'),
    (u'su', u'Sundanese'),
    (u'sw', u'Swahili'),
    (u'sv', u'Swedish'),
    (u'ty', u'Tahitian'),
    (u'ta', u'Tamil'),
    (u'tt', u'Tatar'),
    (u'te', u'Telugu'),
    (u'tg', u'Tajik'),
    (u'tl', u'Tagalog'),
    (u'th', u'Thai'),
    (u'bo', u'Tibetan'),
    (u'ti', u'Tigrinya'),
    (u'to', u'Tonga (Tonga Islands)'),
    (u'tn', u'Tswana'),
    (u'ts', u'Tsonga'),
    (u'tk', u'Turkmen'),
    (u'tr', u'Turkish'),
    (u'tw', u'Twi'),
    (u'ug', u'Uighur; Uyghur'),
    (u'uk', u'Ukrainian'),
    (u'ur', u'Urdu'),
    (u'uz', u'Uzbek'),
    (u've', u'Venda'),
    (u'vi', u'Vietnamese'),
    (u'vo', u'VolapÃ¼k'),
    (u'cy', u'Welsh'),
    (u'wa', u'Walloon'),
    (u'wo', u'Wolof'),
    (u'xh', u'Xhosa'),
    (u'yi', u'Yiddish'),
    (u'yo', u'Yoruba'),
    (u'za', u'Zhuang; Chuang'),
    (u'zh', u'Chinese'),
    (u'zu', u'Zulu')
)

DEFAULT_NONE_VALUE = u'NONE'
LANG_LIST = [(DEFAULT_NONE_VALUE, u'--')]
LANG_LIST.extend(list(STATIC_LANGUAGE_CODES_TUPLE))
LANG_TUPLE = tuple(LANG_LIST)

STATIC_LANGUAGE_CODES_SET = {
    u'aa',
    u'ab',
    u'af',
    u'ak',
    u'sq',
    u'am',
    u'ar',
    u'an',
    u'hy',
    u'as',
    u'av',
    u'ae',
    u'ay',
    u'az',
    u'ba',
    u'bm',
    u'eu',
    u'be',
    u'bn',
    u'bh',
    u'bi',
    u'bo',
    u'bs',
    u'br',
    u'bg',
    u'my',
    u'ca',
    u'cs',
    u'ch',
    u'ce',
    u'zh',
    u'cu',
    u'cv',
    u'kw',
    u'co',
    u'cr',
    u'cy',
    u'cs',
    u'da',
    u'de',
    u'dv',
    u'nl',
    u'dz',
    u'el',
    u'en',
    u'eo',
    u'et',
    u'eu',
    u'ee',
    u'fo',
    u'fa',
    u'fj',
    u'fi',
    u'fr',
    u'fr',
    u'fy',
    u'ff',
    u'Ga',
    u'de',
    u'gd',
    u'ga',
    u'gl',
    u'gv',
    u'el',
    u'gn',
    u'gu',
    u'ht',
    u'ha',
    u'he',
    u'hz',
    u'hi',
    u'ho',
    u'hr',
    u'hu',
    u'hy',
    u'ig',
    u'is',
    u'io',
    u'ii',
    u'iu',
    u'ie',
    u'ia',
    u'id',
    u'ik',
    u'is',
    u'it',
    u'jv',
    u'ja',
    u'kl',
    u'kn',
    u'ks',
    u'ka',
    u'kr',
    u'kk',
    u'km',
    u'ki',
    u'rw',
    u'ky',
    u'kv',
    u'kg',
    u'ko',
    u'kj',
    u'ku',
    u'lo',
    u'la',
    u'lv',
    u'li',
    u'ln',
    u'lt',
    u'lb',
    u'lu',
    u'lg',
    u'mk',
    u'mh',
    u'ml',
    u'mi',
    u'mr',
    u'ms',
    u'Mi',
    u'mk',
    u'mg',
    u'mt',
    u'mn',
    u'mi',
    u'ms',
    u'my',
    u'na',
    u'nv',
    u'nr',
    u'nd',
    u'ng',
    u'ne',
    u'nl',
    u'nn',
    u'nb',
    u'no',
    u'oc',
    u'oj',
    u'or',
    u'om',
    u'os',
    u'pa',
    u'fa',
    u'pi',
    u'pl',
    u'pt',
    u'ps',
    u'qu',
    u'rm',
    u'ro',
    u'ro',
    u'rn',
    u'ru',
    u'sg',
    u'sa',
    u'si',
    u'sk',
    u'sk',
    u'sl',
    u'se',
    u'sm',
    u'sn',
    u'sd',
    u'so',
    u'st',
    u'es',
    u'sq',
    u'sc',
    u'sr',
    u'ss',
    u'su',
    u'sw',
    u'sv',
    u'ty',
    u'ta',
    u'tt',
    u'te',
    u'tg',
    u'tl',
    u'th',
    u'bo',
    u'ti',
    u'to',
    u'tn',
    u'ts',
    u'tk',
    u'tr',
    u'tw',
    u'ug',
    u'uk',
    u'ur',
    u'uz',
    u've',
    u'vi',
    u'vo',
    u'cy',
    u'wa',
    u'wo',
    u'xh',
    u'yi',
    u'yo',
    u'za',
    u'zh',
    u'zu',
}

COUNTIES_ENGLAND = {
    u'Bedfordshire',
    u'Berkshire',
    u'Buckinghamshire',
    u'Cambridgeshire',
    u'Cheshire',
    u'Cornwall',
    u'Cumbria',
    u'Derbyshire',
    u'Devon',
    u'Dorset',
    u'Durham',
    u'East Sussex',
    u'East Yorkshire',
    u'Essex',
    u'Gloucestershire',
    u'Hampshire',
    u'Herefordshire',
    u'Hertfordshire',
    u'Isle of Wight',
    u'Kent',
    u'Lancashire',
    u'Leicestershire',
    u'Lincolnshire',
    u'London',
    u'Merseyside',
    u'Middlesex',
    u'Norfolk',
    u'North Humberside',
    u'North Yorkshire',
    u'Northamptonshire',
    u'Northumberland',
    u'Nottinghamshire',
    u'Oxfordshire',
    u'Rutland',
    u'Shropshire',
    u'Somerset',
    u'South Yorkshire',
    u'Staffordshire',
    u'Suffolk',
    u'Surrey',
    u'Tyne and Wear',
    u'Warwickshire',
    u'West Midlands',
    u'West Sussex',
    u'West Yorkshire',
    u'Wiltshire',
    u'Worcestershire',
}

COUNTIES_WALES = {
    u'Blaenau Gwent',
    u'Bridgend',
    u'Caerphilly',
    u'Cardiff',
    u'Carmarthenshire',
    u'Ceredigion',
    u'Conwy',
    u'Denbigshire',
    u'Flintshire',
    u'Gwynedd',
    u'Isle of Anglesey',
    u'Merthyr Tydfil',
    u'Monmouthshire',
    u'Neath Port Talbot',
    u'Newport',
    u'Pembrokeshire',
    u'Powys',
    u'Rhondda Cynon Taf',
    u'Swansea',
    u'Torfaen',
    u'Vale of Glamorgan',
    u'Wrexham',
}

COUNTIES_SCOTLAND = {
    u'Aberdeen City',
    u'Aberdeenshire',
    u'Angus',
    u'Argyll & Bute',
    u'Clackmannanshire',
    u'Dumfries & Galloway',
    u'Dundee City',
    u'East Ayrshire',
    u'East Dunbartonshire',
    u'East Lothian',
    u'East Renfrewshire',
    u'Edinburgh City',
    u'Falkirk',
    u'Fife',
    u'Glasgow City',
    u'Highland',
    u'Inverclyde',
    u'Midlothian Council',
    u'Moray',
    u'North Ayrshire',
    u'North Lanarkshire',
    u'Orkney Islands',
    u'Perth & Kinross',
    u'Renfrewshire',
    u'Scottish Borders',
    u'Shetland',
    u'South Ayrshire',
    u'South Lanarkshire',
    u'Stirling',
    u'West Dunbartonshire',
    u'West Lothian',
    u'Western Isles',
}

COUNTIES_NI = {
    u'Antrim',
    u'Armagh',
    u'Down',
    u'Fermanagh',
    u'Londonderry',
    u'Tyrone',
}

UK_COUNTY_SET = {
    u'Bedfordshire',
    u'Berkshire',
    u'Buckinghamshire',
    u'Cambridgeshire',
    u'Cheshire',
    u'Cornwall',
    u'Cumbria',
    u'Derbyshire',
    u'Devon',
    u'Dorset',
    u'Durham',
    u'East Sussex',
    u'East Yorkshire',
    u'Essex',
    u'Gloucestershire',
    u'Hampshire',
    u'Herefordshire',
    u'Hertfordshire',
    u'Isle of Wight',
    u'Kent',
    u'Lancashire',
    u'Leicestershire',
    u'Lincolnshire',
    u'London',
    u'Merseyside',
    u'Middlesex',
    u'Norfolk',
    u'North Humberside',
    u'North Yorkshire',
    u'Northamptonshire',
    u'Northumberland',
    u'Nottinghamshire',
    u'Oxfordshire',
    u'Rutland',
    u'Shropshire',
    u'Somerset',
    u'South Yorkshire',
    u'Staffordshire',
    u'Suffolk',
    u'Surrey',
    u'Tyne and Wear',
    u'Warwickshire',
    u'West Midlands',
    u'West Sussex',
    u'West Yorkshire',
    u'Wiltshire',
    u'Worcestershire',
    u'Blaenau Gwent',
    u'Bridgend',
    u'Caerphilly',
    u'Cardiff',
    u'Carmarthenshire',
    u'Ceredigion',
    u'Conwy',
    u'Denbigshire',
    u'Flintshire',
    u'Gwynedd',
    u'Isle of Anglesey',
    u'Merthyr Tydfil',
    u'Monmouthshire',
    u'Neath Port Talbot',
    u'Newport',
    u'Pembrokeshire',
    u'Powys',
    u'Rhondda Cynon Taf',
    u'Swansea',
    u'Torfaen',
    u'Vale of Glamorgan',
    u'Wrexham',
    u'Aberdeen City',
    u'Aberdeenshire',
    u'Angus',
    u'Argyll & Bute',
    u'Clackmannanshire',
    u'Dumfries & Galloway',
    u'Dundee City',
    u'East Ayrshire',
    u'East Dunbartonshire',
    u'East Lothian',
    u'East Renfrewshire',
    u'Edinburgh City',
    u'Falkirk',
    u'Fife',
    u'Glasgow City',
    u'Highland',
    u'Inverclyde',
    u'Midlothian Council',
    u'Moray',
    u'North Ayrshire',
    u'North Lanarkshire',
    u'Orkney Islands',
    u'Perth & Kinross',
    u'Renfrewshire',
    u'Scottish Borders',
    u'Shetland',
    u'South Ayrshire',
    u'South Lanarkshire',
    u'Stirling',
    u'West Dunbartonshire',
    u'West Lothian',
    u'Western Isles',
    u'Antrim',
    u'Armagh',
    u'Down',
    u'Fermanagh',
    u'Londonderry',
    u'Tyrone',
}

UK_COUNTIES_TUPLE = (
    (u'default', u'Please select a county.'),
    (u'England', (
        (u'Bedfordshire', u'Bedfordshire'),
        (u'Berkshire', u'Berkshire'),
        (u'Buckinghamshire', u'Buckinghamshire'),
        (u'Cambridgeshire', u'Cambridgeshire'),
        (u'Cheshire', u'Cheshire'),
        (u'Cornwall', u'Cornwall'),
        (u'Cumbria', u'Cumbria'),
        (u'Derbyshire', u'Derbyshire'),
        (u'Devon', u'Devon'),
        (u'Dorset', u'Dorset'),
        (u'Durham', u'Durham'),
        (u'East Sussex', u'East Sussex'),
        (u'East Yorkshire', u'East Yorkshire'),
        (u'Essex', u'Essex'),
        (u'Gloucestershire', u'Gloucestershire'),
        (u'Hampshire', u'Hampshire'),
        (u'Herefordshire', u'Herefordshire'),
        (u'Hertfordshire', u'Hertfordshire'),
        (u'Isle of Wight', u'Isle of Wight'),
        (u'Kent', u'Kent'),
        (u'Lancashire', u'Lancashire'),
        (u'Leicestershire', u'Leicestershire'),
        (u'Lincolnshire', u'Lincolnshire'),
        (u'London', u'London'),
        (u'Merseyside', u'Merseyside'),
        (u'Middlesex', u'Middlesex'),
        (u'Norfolk', u'Norfolk'),
        (u'North Humberside', u'North Humberside'),
        (u'North Yorkshire', u'North Yorkshire'),
        (u'Northamptonshire', u'Northamptonshire'),
        (u'Northumberland', u'Northumberland'),
        (u'Nottinghamshire', u'Nottinghamshire'),
        (u'Oxfordshire', u'Oxfordshire'),
        (u'Rutland', u'Rutland'),
        (u'Shropshire', u'Shropshire'),
        (u'Somerset', u'Somerset'),
        (u'South Yorkshire', u'South Yorkshire'),
        (u'Staffordshire', u'Staffordshire'),
        (u'Suffolk', u'Suffolk'),
        (u'Surrey', u'Surrey'),
        (u'Tyne and Wear', u'Tyne and Wear'),
        (u'Warwickshire', u'Warwickshire'),
        (u'West Midlands', u'West Midlands'),
        (u'West Sussex', u'West Sussex'),
        (u'West Yorkshire', u'West Yorkshire'),
        (u'Wiltshire', u'Wiltshire'),
        (u'Worcestershire', u'Worcestershire'),
    ),
    ),
    (u'Wales', (
        (u'Blaenau Gwent', u'Blaenau Gwent'),
        (u'Bridgend', u'Bridgend'),
        (u'Caerphilly', u'Caerphilly'),
        (u'Cardiff', u'Cardiff'),
        (u'Carmarthenshire', u'Carmarthenshire'),
        (u'Ceredigion', u'Ceredigion'),
        (u'Conwy', u'Conwy'),
        (u'Denbigshire', u'Denbigshire'),
        (u'Flintshire', u'Flintshire'),
        (u'Gwynedd', u'Gwynedd'),
        (u'Isle of Anglesey', u'Isle of Anglesey'),
        (u'Merthyr Tydfil', u'Merthyr Tydfil'),
        (u'Monmouthshire', u'Monmouthshire'),
        (u'Neath Port Talbot', u'Neath Port Talbot'),
        (u'Newport', u'Newport'),
        (u'Pembrokeshire', u'Pembrokeshire'),
        (u'Powys', u'Powys'),
        (u'Rhondda Cynon Taf', u'Rhondda Cynon Taf'),
        (u'Swansea', u'Swansea'),
        (u'Torfaen', u'Torfaen'),
        (u'Vale of Glamorgan', u'Vale of Glamorgan'),
        (u'Wrexham', u'Wrexham'),
    ),
    ),
    (u'Scotland', (
        (u'Aberdeen City', u'Aberdeen City'),
        (u'Aberdeenshire', u'Aberdeenshire'),
        (u'Angus', u'Angus'),
        (u'Argyll & Bute', u'Argyll & Bute'),
        (u'Clackmannanshire', u'Clackmannanshire'),
        (u'Dumfries & Galloway', u'Dumfries & Galloway'),
        (u'Dundee City', u'Dundee City'),
        (u'East Ayrshire', u'East Ayrshire'),
        (u'East Dunbartonshire', u'East Dunbartonshire'),
        (u'East Lothian', u'East Lothian'),
        (u'East Renfrewshire', u'East Renfrewshire'),
        (u'Edinburgh City', u'Edinburgh City'),
        (u'Falkirk', u'Falkirk'),
        (u'Fife', u'Fife'),
        (u'Glasgow City', u'Glasgow City'),
        (u'Highland', u'Highland'),
        (u'Inverclyde', u'Inverclyde'),
        (u'Midlothian Council', u'Midlothian Council'),
        (u'Moray', u'Moray'),
        (u'North Ayrshire', u'North Ayrshire'),
        (u'North Lanarkshire', u'North Lanarkshire'),
        (u'Orkney Islands', u'Orkney Islands'),
        (u'Perth & Kinross', u'Perth & Kinross'),
        (u'Renfrewshire', u'Renfrewshire'),
        (u'Scottish Borders', u'Scottish Borders'),
        (u'Shetland', u'Shetland'),
        (u'South Ayrshire', u'South Ayrshire'),
        (u'South Lanarkshire', u'South Lanarkshire'),
        (u'Stirling', u'Stirling'),
        (u'West Dunbartonshire', u'West Dunbartonshire'),
        (u'West Lothian', u'West Lothian'),
        (u'Western Isles', u'Western Isles'),
    ),
    ),
    (u'Northern Ireland', (
        (u'Antrim', u'Antrim'),
        (u'Armagh', u'Armagh'),
        (u'Down', u'Down'),
        (u'Fermanagh', u'Fermanagh'),
        (u'Londonderry', u'Londonderry'),
        (u'Tyrone', u'Tyrone'),
    ),
    ),
)


US_STATES_DICT = {
    u'AL': u'Alabama',
    u'AK': u'Alaska',
    u'AZ': u'Arizona',
    u'AR': u'Arkansas',
    u'CA': u'California',
    u'CO': u'Colorado',
    u'CT': u'Connecticut',
    u'DE': u'Delaware',
    u'FL': u'Florida',
    u'GA': u'Georgia',
    u'HI': u'Hawaii',
    u'ID': u'Idaho',
    u'IL': u'Illinois',
    u'IN': u'Indiana',
    u'IA': u'Iowa',
    u'KS': u'Kansas',
    u'KY': u'Kentucky',
    u'LA': u'Louisiana',
    u'ME': u'Maine',
    u'MD': u'Maryland',
    u'MA': u'Massachusetts',
    u'MI': u'Michigan',
    u'MN': u'Minnesota',
    u'MS': u'Mississippi',
    u'MO': u'Missouri',
    u'MT': u'Montana',
    u'NE': u'Nebraska',
    u'NV': u'Nevada',
    u'NH': u'New Hampshire',
    u'NJ': u'New Jersey',
    u'NM': u'New Mexico',
    u'NY': u'New York',
    u'NC': u'North Carolina',
    u'ND': u'North Dakota',
    u'OH': u'Ohio',
    u'OK': u'Oklahoma',
    u'OR': u'Oregon',
    u'PA': u'Pennsylvania',
    u'RI': u'Rhode Island',
    u'SC': u'South Carolina',
    u'SD': u'South Dakota',
    u'TN': u'Tennessee',
    u'TX': u'Texas',
    u'UT': u'Utah',
    u'VT': u'Vermont',
    u'VA': u'Virginia',
    u'WA': u'Washington',
    u'WV': u'West Virginia',
    u'WI': u'Wisconsin',
    u'WY': u'Wyoming',
}


US_STATES_TUPLE = (
    (u'default', u'Please select a state.'),
    (u'AL', u'Alabama'),
    (u'AK', u'Alaska'),
    (u'AZ', u'Arizona'),
    (u'AR', u'Arkansas'),
    (u'CA', u'California'),
    (u'CO', u'Colorado'),
    (u'CT', u'Connecticut'),
    (u'DE', u'Delaware'),
    (u'FL', u'Florida'),
    (u'GA', u'Georgia'),
    (u'HI', u'Hawaii'),
    (u'ID', u'Idaho'),
    (u'IL', u'Illinois'),
    (u'IN', u'Indiana'),
    (u'IA', u'Iowa'),
    (u'KS', u'Kansas'),
    (u'KY', u'Kentucky'),
    (u'LA', u'Louisiana'),
    (u'ME', u'Maine'),
    (u'MD', u'Maryland'),
    (u'MA', u'Massachusetts'),
    (u'MI', u'Michigan'),
    (u'MN', u'Minnesota'),
    (u'MS', u'Mississippi'),
    (u'MO', u'Missouri'),
    (u'MT', u'Montana'),
    (u'NE', u'Nebraska'),
    (u'NV', u'Nevada'),
    (u'NH', u'New Hampshire'),
    (u'NJ', u'New Jersey'),
    (u'NM', u'New Mexico'),
    (u'NY', u'New York'),
    (u'NC', u'North Carolina'),
    (u'ND', u'North Dakota'),
    (u'OH', u'Ohio'),
    (u'OK', u'Oklahoma'),
    (u'OR', u'Oregon'),
    (u'PA', u'Pennsylvania'),
    (u'RI', u'Rhode Island'),
    (u'SC', u'South Carolina'),
    (u'SD', u'South Dakota'),
    (u'TN', u'Tennessee'),
    (u'TX', u'Texas'),
    (u'UT', u'Utah'),
    (u'VT', u'Vermont'),
    (u'VA', u'Virginia'),
    (u'WA', u'Washington'),
    (u'WV', u'West Virginia'),
    (u'WI', u'Wisconsin'),
    (u'WY', u'Wyoming'),
)

US_STATES_SET = {
    u'AL',
    u'AK',
    u'AZ',
    u'AR',
    u'CA',
    u'CO',
    u'CT',
    u'DE',
    u'FL',
    u'GA',
    u'HI',
    u'ID',
    u'IL',
    u'IN',
    u'IA',
    u'KS',
    u'KY',
    u'LA',
    u'ME',
    u'MD',
    u'MA',
    u'MI',
    u'MN',
    u'MS',
    u'MO',
    u'MT',
    u'NE',
    u'NV',
    u'NH',
    u'NJ',
    u'NM',
    u'NY',
    u'NC',
    u'ND',
    u'OH',
    u'OK',
    u'OR',
    u'PA',
    u'RI',
    u'SC',
    u'SD',
    u'TN',
    u'TX',
    u'UT',
    u'VT',
    u'VA',
    u'WA',
    u'WV',
    u'WI',
    u'WY',
}


def eu_country(country_code):
    eu_list = {u'BE',
               u'BG',
               u'CZ',
               u'DK',
               u'DE',
               u'EE',
               u'IE',
               u'GR',
               u'ES',
               u'FR',
               u'HR',
               u'IT',
               u'CY',
               u'LV',
               u'LT',
               u'LU',
               u'HU',
               u'MT',
               u'NL',
               u'AT',
               u'PL',
               u'PT',
               u'RO',
               u'SI',
               u'SK',
               u'FI',
               u'SE',
               u'GB'}
    check = {country_code}
    if len(eu_list - check) < 28:
        return True
    else:
        return False


def get_country_list():
    country_list = None

    try:
        # We only want to import pycountry if absolutely necessary.
        import pycountry

        logging.info('Retrieving pycountry country list.')
        country_list = list(pycountry.countries)
    except (ImportError, ImportWarning) as e:
        logging.error(msg='Could not get country list as pycountry could not be found.')

    return country_list


def build_iso_country_alpha2_code_lables():
    countries = get_country_list()
    logging.info('Building iso_country_alpha2_code_lables.')
    country_code_labels = []
    for country in countries:
        country_code_labels.append((country.alpha2, country.name))
    # running_app.registry['iso_country_alpha2_code_lables'] = country_code_label_list

    return country_code_labels


def build_iso_country_alpha2_codes():
    countries = get_country_list()
    logging.info('Building iso_country_alpha2_codes.')

    country_code_codes = set()
    for country in countries:
        country_code_codes.add(country.alpha2)
    # running_app = country_code_label_list

    return country_code_codes


def get_country_code_labels(app=None):
    country_codes = STATIC_COUNTRY_LABLES_TUPLE

    if not country_codes:
        if not app:
            import webapp2
            app = webapp2.get_app()

        if app:
            country_codes = app.registry.get('iso_country_alpha2_code_lables')

        if not country_codes:
            country_codes = build_iso_country_alpha2_code_lables()

        if app:
            app.registry['iso_country_alpha2_code_lables'] = country_codes

    return country_codes


def get_country_codes(app=None):
    country_codes = STATIC_COUNTRY_CODES_SET

    if not country_codes:
        if not app:
            import webapp2
            app = webapp2.get_app()

        if app:
            country_codes = app.registry.get('iso_country_alpha2_codes')

        if not country_codes:
            country_codes = build_iso_country_alpha2_codes()

        if app:
            app.registry['iso_country_alpha2_codes'] = country_codes

    return country_codes


def country_exists(iso_alpha_2_code):
    return iso_alpha_2_code in get_country_codes()

"""
The following is imported from the GAE Boilerplate project
"""


def parse_accept_language_header(string, pattern='([a-zA-Z]{1,8}(-[a-zA-Z0-9]{1,8})?)\s*(;\s*q\s*=\s*(1|0\.[0-9]+))?'):
    """
    Parse a dict from an Accept-Language header string
    (see http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html)
    example input: en-US,en;q=0.8,es-es;q=0.5
    example output: {'en_US': 100, 'en': 80, 'es_ES': 50}
    """
    res = {}
    if not string:
        return None
    for match in re.finditer(pattern, string):
        if None == match.group(4):
            q = 1
        else:
            q = match.group(4)
        l = match.group(1).replace('-', '_')
        if len(l) == 2:
            l = l.lower()
        elif len(l) == 5:
            l = l.split('_')[0].lower() + "_" + l.split('_')[1].upper()
        else:
            l = None
        if l:
            res[l] = int(100 * float(q))
    return res


def get_locale_from_accept_header(request):
    """
    Detect locale from request.header 'Accept-Language'
    Locale with the highest quality factor that most nearly matches our
    config.locales is returned.
    cls: self object

    Note that in the future if
        all User Agents adopt the convention of sorting quality factors in descending order
        then the first can be taken without needing to parse or sort the accept header
        leading to increased performance
        (see http://lists.w3.org/Archives/Public/ietf-http-wg/2012AprJun/0473.html)
    """
    header = request.headers.get("Accept-Language", '')
    parsed = parse_accept_language_header(header)
    if parsed is None:
        return None
    pairs_sorted_by_q = sorted(parsed.items(), key=lambda (lang, q): q, reverse=True)
    locale = Locale.negotiate([lang for (lang, q) in pairs_sorted_by_q], request.app.config.get('locales'), sep='_')
    return str(locale)


def get_country_code(request):
    """
    Country code based on ISO 3166-1 (http://en.wikipedia.org/wiki/ISO_3166-1)
    :param request: Request Object
    :return: ISO Code of the country
    """
    if 'X-AppEngine-Country' in request.headers:
        if request.headers['X-AppEngine-Country'] in pytz.country_timezones:
            return request.headers['X-AppEngine-Country']
    return None


def get_city_code(request):
    """
    City code based on ISO 3166-1 (http://en.wikipedia.org/wiki/ISO_3166-1)
    :param request: Request Object
    :return: ISO Code of the City
    """
    if 'X-AppEngine-City' in request.headers:
        return request.headers['X-AppEngine-City']
    return None


def get_region_code(request):
    """
    City code based on ISO 3166-1 (http://en.wikipedia.org/wiki/ISO_3166-1)
    :param request: Request Object
    :return: ISO Code of the City
    """
    if 'X-AppEngine-City' in request.headers:
        return request.headers['X-AppEngine-Region']
    return None


def get_city_lat_long(request):
    """
    City code based on ISO 3166-1 (http://en.wikipedia.org/wiki/ISO_3166-1)
    :param request: Request Object
    :return: ISO Code of the City
    """
    if 'X-AppEngine-City' in request.headers:
        return request.headers['X-AppEngine-CityLatLong']
    return None


def _set_locale(request, force=None):
    """
    retrieve locale from a prioritized list of sources and then set locale and save it
    cls: self object
    force: a locale to force set (ie 'en_US')
    return: locale as string or None if i18n should be disabled
    """
    try:
        webapp2_instance = webapp2.get_app()
    except AssertionError:
        logging.debug('No webapp2 global set; skipping registry lookup for jinja2 template engine.')
        locales = []
    else:
        locales = webapp2_instance.config.get(I18N_LOCALES_KEY) or []

    # disable i18n if config.locales array is empty or None
    if not locales:
        return None
    # 1. force locale if provided
    locale = force
    if locale not in locales:
        # 2. retrieve locale from url query string
        locale = request.get("hl", None)
        if locale not in locales:
            # 3. retrieve locale from user preferences
            user_session_info = request.registry['user_session_info']
            if user_session_info:
                user_id = user_session_info.get('user_id', None)
                if user_id:
                    stored_locale = request.session.get('inferred_locale', None)
                    if not stored_locale:
                        lower = str(request.registry['user_session_info'].get('language_preference', None))
                        upper = str(lower).upper()
                        stored_locale = '{0}_{1}'.format(lower, upper)
                        request.session['inferred_locale'] = stored_locale
                    locale = stored_locale
                else:
                    locale = None
            if locale not in locales:
                # 4. retrieve locale from accept language header
                locale = get_locale_from_accept_header(request)
                if locale not in locales:
                    # 5. detect locale from IP address location
                    territory = get_country_code(request) or 'ZZ'
                    locale = str(Locale.negotiate(territory, locales))
                    if locale not in locales:
                        # 6. use default locale
                        locale = i18n.get_store().default_locale
    i18n.get_i18n(request=request).set_locale(locale)
    request.registry['locale'] = locale
    # save locale in cookie with 26 weeks expiration (in seconds)
    # cls.response.set_cookie('hl', locale, max_age=15724800)
    # return locale

"""
End import from the GAE Boilerplate project
"""