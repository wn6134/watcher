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

CONFIG_FILENAME = 'watch.ini'


class LogLevel:
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'


class Config:
    _ping_list = None
    _http_list = None
    _https_list = None
    _timeout = None
    _mail_to = None
    _mail_from = None
    _mail_levels_list = None
    _ok_mail_silent_checks = None

    def __init__(self,
                 ping_list=None,
                 http_list=None,
                 https_list=None,
                 timeout=None,
                 mail_to=None,
                 mail_from=None,
                 mail_levels_list=None,
                 ok_mail_silent_checks=None
                 ):
        self._ping_list = ping_list if ping_list is not None else []
        self._http_list = http_list if http_list is not None else []
        self._https_list = https_list if https_list is not None else []
        self._timeout = timeout if timeout is not None else 60
        self._mail_to = mail_to
        self._mail_from = mail_from if mail_from is not None else 'report@watcher.tld'
        self._mail_levels_list = mail_levels_list \
            if mail_levels_list is not None else [LogLevel.WARNING, LogLevel.ERROR]
        self._ok_mail_silent_checks = ok_mail_silent_checks if ok_mail_silent_checks is not None else 0

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
    def ok_mail_silent_checks(self):
        return self._ok_mail_silent_checks

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
        if 'ok-mail-silent-checks' in watch:
            self._ok_mail_silent_checks = watch.getint('ok-mail-silent-checks')

    def no_hosts_defined(self):
        return len(self.ping_list) == 0 and len(self.http_list) == 0 and len(self.https_list) == 0

    @staticmethod
    def _parse_list_from_string(string):
        return [item.strip() for item in string.replace('\n', ',').split(',') if item != '']


class Watcher:
    _config_filename = None
    _config = None
    _ok_checks = 0
    _http_timeout = 30
    _http_adapter = HTTPAdapter(max_retries=Retry(total=1))
    _observer = None
    _config_update_required = False

    def __init__(self, config_filename=CONFIG_FILENAME):
        self._config_filename = config_filename
        self._config = Config()
        self._config.from_file(self._config_filename)

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

    def watch(self):
        if self._config.no_hosts_defined():
            self._log('Hosts for check are not set', LogLevel.WARNING)
            exit(0)
        try:
            while True:
                if self._config_update_required:
                    self._config.from_file(self._config_filename)
                    self._log('Config was updated', level=LogLevel.DEBUG)
                    self._config_update_required = False
                for host in self._config.ping_list:
                    self._check_ping(host)
                for host in self._config.http_list:
                    self._check_http(host)
                for host in self._config.https_list:
                    self._check_https(host)
                if self._config.ok_mail_silent_checks > 0:
                    self._ok_checks += 1
                    if self._ok_checks >= self._config.ok_mail_silent_checks:
                        self._log('All tests OK', mail=True)
                        self._ok_checks = 0
                sleep(self._config.timeout)
        except KeyboardInterrupt:
            self._observer.stop()
        self._observer.join()

    def _check_ping(self, host):
        try:
            raw_reply = StringIO()
            reply = ping(host, count=1, verbose=True, out=raw_reply)
            if reply.success():
                self._log(f'{host} PING OK', LogLevel.INFO)
            else:
                self._log(f'{host} PING BAD: {raw_reply.getvalue().strip()}', LogLevel.WARNING)
        except Exception as e:
            self._log(f'{host} PING FAILED: {e}', LogLevel.ERROR)

    def _check_http(self, host):
        try:
            http = requests.Session()
            http.mount("http://", self._http_adapter)
            status_code = http.get('http://' + host, timeout=self._http_timeout).status_code
            if status_code == 200:
                self._log(f'{host} HTTP OK', LogLevel.INFO)
            else:
                self._log(f'{host} HTTP BAD: status code {status_code}', LogLevel.WARNING)
        except Exception as e:
            self._log(f'{host} HTTP FAILED: {e}', LogLevel.ERROR)

    def _check_https(self, host):
        try:
            https = requests.Session()
            https.mount("https://", self._http_adapter)
            status_code = https.get('https://' + host, timeout=self._http_timeout).status_code
            if status_code == 200:
                self._log(f'{host} HTTPS OK', LogLevel.INFO)
            else:
                self._log(f'{host} HTTPS BAD: status code {status_code}', LogLevel.WARNING)
        except Exception as e:
            self._log(f'{host} HTTPS FAILED: {e}', LogLevel.ERROR)

    def _log(self, message, level=LogLevel.INFO, mail=None):
        formatted_message = self._format_message(message, level)
        print(formatted_message)
        if self._config.mail_to is None:
            return
        if mail or level in self._config.mail_levels_list:
            self._mail(message, formatted_message)
            self._ok_checks = 0

    @staticmethod
    def _format_message(message, level=LogLevel.INFO):
        return f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{level}] {message}"

    def _mail(self, subject, body):
        try:
            msg = MIMEText(body)
            msg["To"] = self._config.mail_to
            msg["From"] = self._config.mail_from
            msg["Subject"] = subject
            p = Popen(["/usr/sbin/sendmail", "-t", "-oi"], stdin=PIPE)
            p.communicate(msg.as_bytes())
        except Exception as e:
            self._log(f'Failed to send mail: {e}', LogLevel.ERROR, mail=True)


if __name__ == '__main__':
    Watcher().watch()
