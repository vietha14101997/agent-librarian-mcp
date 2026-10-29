"""Credential-free authentication lifecycle receipts and explicit desktop outcome."""
import json
import subprocess
import sys
import time
from .state import write_private,read_private

class LoginProgress:
    def __init__(self,state,reset=False):
        self.state=state;self.events=[]
        if not reset and (state.path/'last-login.json').exists():self.events=read_private(state.path/'last-login.json').get('events',[])[-100:]
        self.offset=self.events[-1]['elapsed_ms'] if self.events else 0
        self.started=time.monotonic();self.cleanup_requested=False;self.context_closed=False
    def event(self,kind,**metadata):
        entry={'event':kind,'elapsed_ms':self.offset+int((time.monotonic()-self.started)*1000),**metadata}
        self.events.append(entry);self.events=self.events[-100:]
        write_private(self.state.path/'last-login.json',{'kind':'AUTH_LIFECYCLE_METADATA_ONLY','events':self.events})
    def closed(self):
        self.context_closed=True;self.event('browser_context_closed',controller_cleanup_requested=self.cleanup_requested)
    def attach(self,context):
        context.on('close',lambda *_:self.closed())
        def page_events(page):
            self.event('page_opened')
            page.on('close',lambda *_:self.event('page_closed'))
            page.on('crash',lambda *_:self.event('page_crashed'))
        context.on('page',page_events)
        for page in context.pages:page_events(page)
        browser=context.browser
        if browser:browser.on('disconnected',lambda *_:self.event('browser_disconnected',controller_cleanup_requested=self.cleanup_requested))

def notify_outcome(success,code=None):
    if sys.platform!='darwin':return
    text=('Connected. Your session is stored in macOS Keychain. Return to Codex or the terminal for notebook selection.' if success else
        'Not connected. No verified session was saved by this attempt. Your browser profile was retained. Status: '+(code or 'AUTHENTICATION_REQUIRED'))
    # Static text plus a finite program error code; never account, token, URL or response data.
    script='display alert "Agent Librarian" message '+json.dumps(text)+' buttons {"OK"} default button "OK"'
    try:subprocess.Popen(['/usr/bin/osascript','-e',script],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except Exception:pass # CLI and persistent status remain authoritative if desktop alerts are unavailable.
