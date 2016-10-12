#!/usr/bin/env python

"""Datadog output Splunk Setup REST Handler."""

__author__ = 'Robert van Veelen <robert.vanveelen@gmail.com>'
__license__ = 'Apache License, Version 2.0'


import logging
import os
import shutil

import splunk.admin


class ConfigDatadogOutputApp(splunk.admin.MConfigHandler):
    """Datadog output Splunk Setup REST Handler."""

    def setup(self):
        """Sets up required configuration params for splunk_datadog."""
        if self.requestedAction == splunk.admin.ACTION_EDIT:
            self.supportedArgs.addOptArg('host')
            self.supportedArgs.addOptArg('port')
            self.supportedArgs.addOptArg('prefix')
            self.supportedArgs.addOptArg('namespace')
            self.supportedArgs.addOptArg('tags')

    def handleList(self, confInfo):
        """Handles configuration params for splunk_datadog."""
        conf = self.readConf('datadog')
        if conf:
            for stanza, settings in conf.items():
                for key, val in settings.items():
                    confInfo[stanza].append(key, val)

    def handleEdit(self, confInfo):
        """Handles editing configuration params for splunk_datadog."""
        del confInfo

        if self.callerArgs.data['host'][0] in [None, '']:
            self.callerArgs.data['host'][0] = ''
        if self.callerArgs.data['port'][0] in [None, '']:
            self.callerArgs.data['port'][0] = ''
        if self.callerArgs.data['namespace'][0] in [None, '']:
            self.callerArgs.data['namespace'][0] = ''
        if self.callerArgs.data['prefix'][0] in [None, '']:
            self.callerArgs.data['prefix'][0] = ''
        if self.callerArgs.data['tags'][0] in [None, '']:
            self.callerArgs.data['tags'][0] = ''

        self.writeConf('datadog', 'datadog_config', self.callerArgs.data)

        install_datadog_py(os.environ.get('SPLUNK_HOME'))


def install_datadog_py(splunk_home):
    """Copies datadog.py to Splunk's bin/scripts directory."""

    script_src = os.path.join(
        splunk_home, 'etc', 'apps', 'splunk_datadog', 'bin', 'datadog.py')
    script_dest = os.path.join(splunk_home, 'bin', 'scripts')

    logging.info(
        'Copying script_src=%s to script_dest=%s', script_src, script_dest)
    shutil.copy(script_src, script_dest)


if __name__ == '__main__':
    splunk.admin.init(ConfigDatadogOutputApp, splunk.admin.CONTEXT_NONE)
