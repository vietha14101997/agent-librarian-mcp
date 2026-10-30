"""Dedicated Chromium lifecycle. No personal browser discovery or cookie export.

Playwright is only the CDP client; Chromium owns persistent credentials and their
OS protection. No remote endpoint, fixed port, password-store override or daemon.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import time

from ..gateway.common import Rejected
from ..locations import user_data
from .state import private_dir
from .browser_auth import quiet_browser_environment


def browser_root():
    root = user_data().absolute() / 'managed-chromium'
    if any((p / '.git').exists() for p in (root, *root.parents)):
        raise Rejected('MANAGED_PROFILE_INSIDE_REPOSITORY')
    return private_dir(root, create=True)


def profile_for(state):
    return private_dir(browser_root() / state.load()['runtime_id'], create=True)


@contextmanager
def profile_lock(profile):
    fd = os.open(profile / 'controller.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise Rejected('MANAGED_BROWSER_BUSY') from None
        yield
    finally:
        os.close(fd)


class ManagedBrowser:
    """One bounded controller lease; reuse only a profile-owned CDP browser.

    Normal operations close browsers they launched. `browser start` deliberately
    retains its window; subsequent processes reconnect and leave it running.
    The profile survives every close, timeout and independent Python process.
    """
    def __init__(self, state, *, headless=True, keep_open=False, engine_factory=None, start_if_missing=True):
        self.state = state; self.profile = profile_for(state)
        self.headless = headless; self.keep_open = keep_open
        self.engine_factory = engine_factory; self.browser = None; self.process = None
        self.start_if_missing = start_if_missing
        self.engine = None; self.lease = None; self.launched = False

    def __enter__(self):
        self.lease = profile_lock(self.profile); self.lease.__enter__()
        try:
            if self.engine_factory is None:
                try: from playwright.sync_api import sync_playwright
                except ImportError: raise Rejected('PERSONAL_DEPENDENCIES_REQUIRED') from None
                self.engine_factory = sync_playwright
            with quiet_browser_environment():
                self.engine = self.engine_factory().start()
            try: self._connect_or_start()
            except Rejected: raise
            except Exception: raise Rejected('MANAGED_BROWSER_UNAVAILABLE') from None
            return self
        except BaseException:
            self.close(); raise

    def _endpoint(self):
        port_file = self.profile / 'DevToolsActivePort'
        if port_file.is_symlink(): raise Rejected('MANAGED_BROWSER_ENDPOINT_INVALID')
        try:
            with port_file.open('rb') as stream: raw = stream.read(1025)
        except FileNotFoundError: return None
        if len(raw) > 1024: raise Rejected('MANAGED_BROWSER_ENDPOINT_INVALID')
        lines = raw.decode('ascii').splitlines()
        if len(lines) != 2 or not lines[0].isdigit() or not 1 <= int(lines[0]) <= 65535:
            raise Rejected('MANAGED_BROWSER_ENDPOINT_INVALID')
        # Never accept a host or URL supplied by a profile file.
        import re
        if not re.fullmatch(r'/devtools/browser/[A-Za-z0-9-]{1,128}', lines[1]):
            raise Rejected('MANAGED_BROWSER_ENDPOINT_INVALID')
        return 'ws://127.0.0.1:' + lines[0] + lines[1]

    def _attach(self, endpoint):
        browser = self.engine.chromium.connect_over_cdp(endpoint, timeout=2000)
        try:
            cdp = browser.new_browser_cdp_session()
            try: args = cdp.send('Browser.getBrowserCommandLine')['arguments']
            finally: cdp.detach()
            required = {f'--user-data-dir={self.profile}', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0'}
            if not required <= set(args): raise Rejected('MANAGED_BROWSER_OWNERSHIP_MISMATCH')
            if not browser.contexts: raise Rejected('MANAGED_BROWSER_UNAVAILABLE')
            self.browser = browser; self.context = browser.contexts[0]
        except BaseException:
            # Disconnect only. Never close a browser whose ownership is unproven.
            raise

    def _connect_or_start(self):
        endpoint = self._endpoint()
        if endpoint:
            try:
                self._attach(endpoint); return
            except Rejected: raise
            except Exception: pass  # Stale endpoint; Chromium's profile lock is authoritative.
        if not self.start_if_missing: raise Rejected('MANAGED_BROWSER_NOT_RUNNING')
        executable = Path(self.engine.chromium.executable_path)
        if not executable.is_file(): raise Rejected('MANAGED_CHROMIUM_INSTALL_APPROVAL_REQUIRED')
        port_file = self.profile / 'DevToolsActivePort'
        if port_file.exists(): port_file.unlink()
        args = [str(executable), f'--user-data-dir={self.profile}', '--remote-debugging-port=0',
                '--remote-debugging-address=127.0.0.1', '--enable-automation', '--no-first-run',
                '--no-default-browser-check', '--disable-extensions', 'about:blank']
        if self.headless: args.insert(-1, '--headless=new')
        with quiet_browser_environment():
            self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, start_new_session=True)
        self.launched = True
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None: raise Rejected('MANAGED_BROWSER_UNAVAILABLE')
            endpoint = self._endpoint()
            if endpoint:
                try: self._attach(endpoint); return
                except Rejected: raise
                except Exception: pass
            time.sleep(.1)
        raise Rejected('MANAGED_BROWSER_UNAVAILABLE')

    def page(self, *, navigate=True):
        from urllib.parse import urlsplit
        from ..providers.session import GOOGLE_HOSTS
        pages = [p for p in self.context.pages if urlsplit(p.url).hostname in GOOGLE_HOSTS and urlsplit(p.url).path == '/']
        page = pages[0] if pages else self.context.new_page()
        if navigate:
            try: page.goto('https://notebook.google.com/', wait_until='domcontentloaded', timeout=20000)
            except Exception: raise Rejected('MANAGED_BROWSER_OFFLINE') from None
        return page

    def close_browser(self):
        if self.browser:
            try:
                # Playwright's Browser.close on connect_over_cdp only disconnects.
                # The CDP command actually closes our proven profile-owned process.
                self.browser.new_browser_cdp_session().send('Browser.close')
                self.browser.close()
                if self.process: self.process.wait(timeout=5)
            except Exception: raise Rejected('MANAGED_BROWSER_CLOSE_FAILED') from None
            self.browser = None

    def close(self):
        try:
            if self.launched and not self.keep_open:
                if self.browser:
                    try: self.close_browser()
                    except Rejected: pass
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    try: self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=5)
            elif self.launched and self.browser is None and self.process and self.process.poll() is None:
                self.process.terminate()  # Failed startup must not leak a process.
        finally:
            try:
                if self.engine: self.engine.stop(); self.engine = None
            finally:
                if self.lease: self.lease.__exit__(None, None, None); self.lease = None

    def __exit__(self, *args): self.close()


def install_browser(approve=False):
    """Explicit executable download boundary, independent of login and mappings."""
    import sys
    preview = {'status': 'DOWNLOAD_APPROVAL_REQUIRED', 'dependency': 'Playwright 1.64.1 Chromium',
               'command': [sys.executable, '-m', 'playwright', 'install', 'chromium'],
               'profile_access': False, 'active_runtime_changes': False}
    if not approve: return preview
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as engine:
            if Path(engine.chromium.executable_path).is_file():
                return {'status': 'MANAGED_CHROMIUM_REUSED', 'downloaded': False}
    except ImportError: raise Rejected('PERSONAL_DEPENDENCIES_REQUIRED') from None
    try:
        result = subprocess.run(preview['command'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    except subprocess.TimeoutExpired: raise Rejected('MANAGED_CHROMIUM_DOWNLOAD_TIMEOUT') from None
    if result.returncode: raise Rejected('MANAGED_CHROMIUM_DOWNLOAD_FAILED')
    return {'status': 'MANAGED_CHROMIUM_INSTALLED', 'downloaded': True}
