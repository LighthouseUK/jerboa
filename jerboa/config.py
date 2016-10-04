"""
This configuration parser takes a platform argument and uses that for the sections of the config file
i.e. Production, Development, Testing

All you need to do is use the corresponding get methods for the data you need. The platform is automatically used
where applicable.
"""
from __future__ import absolute_import
import codecs
from datetime import datetime
from ConfigParser import SafeConfigParser, NoSectionError, NoOptionError


__author__ = 'Matt Badger'


class CustomConfigParser(SafeConfigParser):
    def __init__(self, platform, *args, **kwargs):
        self.platform = platform
        SafeConfigParser.__init__(self, *args, **kwargs)

    def get(self, option, section=None, raw=False, vars=None):
        if section is None:
            section = self.platform
        return SafeConfigParser.get(self, section, option, raw=False, vars=None)

    def getint(self, option, section=None):
        return int(self.get(option=option, section=section))

    def getfloat(self, option, section=None):
        return float(self.get(option=option, section=section))

    def getboolean(self, option, section=None):
        v = self.get(section=section, option=option)
        if v.lower() not in self._boolean_states:
            raise ValueError, 'Not a boolean: %s' % v
        return self._boolean_states[v.lower()]

    def getdate(self, option, section=None, raw=False, vars=None):
        if section is None:
            section = self.platform
        value = SafeConfigParser.get(self, section, option, raw=False, vars=None)
        return datetime.strptime(value, '%Y-%m-%d')

    def getdatetime(self, option, section=None, raw=False, vars=None):
        if section is None:
            section = self.platform
        value = SafeConfigParser.get(self, section, option, raw=False, vars=None)
        return datetime.strptime(value, '%Y-%m-%d %H%M%S')

    def getlist(self, option, section=None, raw=False, vars=None):
        if section is None:
            section = self.platform
        setting = SafeConfigParser.get(self, section, option, raw=False, vars=None)
        return setting.split(',')


def load_config(config_file_path, platform='Development', allow_no_value=True, **kwargs):

    config_instance = CustomConfigParser(platform=platform, allow_no_value=allow_no_value, **kwargs)

    with codecs.open(config_file_path, 'r', encoding='utf-8') as f:
        config_instance.readfp(f)

    return config_instance
