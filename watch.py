import configparser
import datetime
import os
from email.mime.text import MIMEText
from io import StringIO
from subprocess import Popen, PIPE
from time import sleep

import requests
from pythonping import ping
from requests.adapters import HTTPAdapter, Retry
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class LogLevel:
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'


class Result:
    OK = 'OK'
    BAD = 'BAD'
    FAIL = 'FAIL'


class CheckResult:
    def __init__(self, host, check_type, result, details=None):
        self._host = host
        self._check_type = check_type
        self._result = result
        self._details = details

    @property
    def host(self):
        return self._host

    @property
    def check_type(self):
        return self._check_type

    @property
    def result(self):
        return self._result

    @property
    def details(self):
        return self._details


class Config:
    def __init__(self,
                 ping_list=None, http_list=None, https_list=None, timeout=30,
                 mail_to=None, mail_from='report@watcher.tld', mail_levels_list=None, mail_after_ok_checks=0
                 ):
        self._ping_list = ping_list if ping_list is not None else []
        self._http_list = http_list if http_list is not None else []
        self._https_list = https_list if https_list is not None else []
        self._timeout = timeout
        self._mail_to = mail_to
        self._mail_from = mail_from
        self._mail_levels_list = mail_levels_list \
            if mail_levels_list is not None else [LogLevel.WARNING, LogLevel.ERROR]
        self._mail_after_ok_checks = mail_after_ok_checks

    @property
    def ping_list(self):
        return self._ping_list

    @property
    def http_list(self):
        return self._http_list

    @property
    def https_list(self):
        return self._https_list

    @property
    def timeout(self):
        return self._timeout

    @property
    def mail_to(self):
        return self._mail_to

    @property
    def mail_from(self):
        return self._mail_from

    @property
    def mail_levels_list(self):
        return self._mail_levels_list

    @property
    def mail_after_ok_checks(self):
        return self._mail_after_ok_checks

    def from_file(self, path_to_config):
        if not os.path.isfile(path_to_config):
            raise Exception(f'"{path_to_config}" is not a file')
        config = configparser.ConfigParser()
        config.read(path_to_config)
        if 'watch' not in config:
            raise Exception(f'Mandatory section "watch" absent in "{path_to_config}"')
        watch = config['watch']
        if 'ping-list' in watch:
            self._ping_list = self._parse_list_from_string(watch['ping-list'])
        if 'http-list' in watch:
            self._http_list = self._parse_list_from_string(watch['http-list'])
        if 'https-list' in watch:
            self._https_list = self._parse_list_from_string(watch['https-list'])
        if 'timeout' in watch:
            self._timeout = watch.getint('timeout')
        if 'mail-to' in watch:
            self._mail_to = watch['mail-to']
        if 'mail-from' in watch:
            self._mail_from = watch['mail-from']
        if 'mail-levels-list' in watch:
            self._mail_levels_list = [
                item.upper() for item in self._parse_list_from_string(watch['mail-levels-list'])
            ]
        if 'mail-after-ok-checks' in watch:
            self._mail_after_ok_checks = watch.getint('mail-after-ok-checks')

    def no_hosts_defined(self):
        return len(self.ping_list) == 0 and len(self.http_list) == 0 and len(self.https_list) == 0

    @staticmethod
    def _parse_list_from_string(string):
        return [item.strip() for item in string.replace('\n', ',').split(',') if item != '']


class Watcher:
    def __init__(self, config_filename):
        self._config_filename = config_filename

        self._config = Config()
        self._config.from_file(self._config_filename)
        if self._config.no_hosts_defined():
            self._log('Hosts for check are not set', LogLevel.WARNING)
            exit(1)

        self._config_update_required = False

        def _update_required():
            self._config_update_required = True

        class _CustomHandler(FileSystemEventHandler):
            def on_modified(self, event):
                super(_CustomHandler, self).on_modified(event)

                if not event.is_directory:
                    _update_required()

        event_handler = _CustomHandler()
        self._observer = Observer()
        self._observer.schedule(event_handler, path=self._config_filename, recursive=False)
        self._observer.start()

        self._http_adapter = HTTPAdapter(max_retries=Retry(total=1))

        self._ok_checks = 0

    def watch(self):
        try:
            while True:
                if self._config_update_required:
                    self._config.from_file(self._config_filename)
                    message = 'Config was updated'
                    self._log(message)
                    body = f'''Date/time: {get_datetime()}
Result: {message}
{self._format_config()}
'''
                    self._mail(message, body)
                    self._config_update_required = False

                for host in self._config.ping_list:
                    self._submit_result(
                        self._check_ping(host)
                    )
                for host in self._config.http_list:
                    self._submit_result(
                        self._check_http(host, adapter=self._http_adapter, timeout=self._config.timeout, https=False)
                    )
                for host in self._config.https_list:
                    self._submit_result(
                        self._check_http(host, adapter=self._http_adapter, timeout=self._config.timeout)
                    )

                if self._config.mail_after_ok_checks > 0:
                    self._ok_checks += 1
                    if self._ok_checks >= self._config.mail_after_ok_checks:
                        message = 'All tests OK'
                        self._log(message)
                        body = f'''Date/time: {get_datetime()}
Result: {message}
{self._format_config()}
'''
                        self._mail(message, body)
                        self._ok_checks = 0
                sleep(self._config.timeout)
        except KeyboardInterrupt:
            self._observer.stop()
        self._observer.join()

    def _format_config(self):
        return f'''Ping list: {', '.join([host for host in self._config.ping_list])}
HTTP list: {', '.join([host for host in self._config.http_list])}
HTTPS list: {', '.join([host for host in self._config.https_list])}
Timeout: {self._config.timeout}
Mail levels: {', '.join([level for level in self._config.mail_levels_list])}
Mail after OK checks: {self._config.mail_after_ok_checks}'''

    @staticmethod
    def _check_ping(host):
        check_type = 'PING'
        try:
            raw_reply = StringIO()
            reply = ping(host, count=1, verbose=True, out=raw_reply)
            if reply.success():
                return CheckResult(host, check_type, Result.OK)
            else:
                details = raw_reply.getvalue().strip()
                return CheckResult(host, check_type, Result.BAD, details)
        except Exception as e:
            return CheckResult(host, check_type, Result.FAIL, f'{e}')

    @staticmethod
    def _check_http(host, adapter=None, timeout=30, https=True):
        if adapter is None:
            adapter = HTTPAdapter(max_retries=Retry(total=1))
        check_type = 'HTTPS'
        prefix = 'https://'
        if not https:
            check_type = 'HTTP'
            prefix = 'http://'
        try:
            http = requests.Session()
            http.mount(prefix, adapter)
            status_code = http.get(prefix + host, timeout=timeout).status_code
            if status_code == 200:
                return CheckResult(host, check_type, Result.OK)
            else:
                details = f'status code {status_code}'
                return CheckResult(host, check_type, Result.BAD, details)
        except Exception as e:
            return CheckResult(host, check_type, Result.FAIL, f'{e}')

    def _submit_result(self, result, mail=None):
        if result.result in [Result.BAD, Result.FAIL]:
            self._ok_checks = 0
        level = LogLevel.INFO
        if result.result == Result.BAD:
            level = LogLevel.WARNING
        if result.result == Result.FAIL:
            level = LogLevel.ERROR
        message = full_message = result.host + ' ' + result.check_type + ' ' + result.result
        if result.details:
            full_message += ': ' + result.details
        self._log(full_message, level=level)
        
        if self._config.mail_to is None or mail is False:
            return
        if mail or level in self._config.mail_levels_list:
            details = ''
            if result.details:
                details = f'Details: {result.details}'
            body = f'''Date/time: {get_datetime()}
Host: {result.host} 
Check type: {result.check_type}
Result: {result.result}
{details}
'''
            self._mail(message, body)

    @staticmethod
    def _log(message, level=LogLevel.INFO):
        print(f'{get_datetime()} [{level}] {message}')

    def _mail(self, subject, body):
        try:
            msg = MIMEText(body)
            msg['To'] = self._config.mail_to
            msg['From'] = self._config.mail_from
            msg['Subject'] = subject
            p = Popen(['/usr/sbin/sendmail', '-t', '-oi'], stdin=PIPE)
            p.communicate(msg.as_bytes())
        except Exception as e:
            self._log(f'Failed to send mail: {e}', LogLevel.ERROR)


def get_datetime():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


if __name__ == '__main__':
    Watcher('watch.ini').watch()
