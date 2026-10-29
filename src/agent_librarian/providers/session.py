"""Service-owned session lifecycle; no browser, environment or plaintext fallback.

Token fields/negative session ID and internal email field adapted from upstream
8ac9728ec5b128b05077e9d7c4c8bb11b5830c61 core/auth.py, core/base.py, utils/cdp.py.
Copyright (c) 2025 Jacob Ben David; MIT notice in THIRD_PARTY_NOTICES.md.
"""
from dataclasses import dataclass,field
import json
import re
import threading
import time
from typing import Protocol
from ..gateway.common import Rejected

GOOGLE_HOSTS=('notebooklm.google.com','notebook.google.com')

@dataclass(repr=False,frozen=True)
class Session:
    account_id:str
    expected_email:str=field(repr=False)
    cookies:dict=field(repr=False)
    csrf:str=field(repr=False)
    session_id:str=field(repr=False)
    build_label:str
    expires_at:float
    host:str='notebooklm.google.com'

    def secrets(self):return [*self.cookies.values(),self.csrf,self.session_id,self.expected_email]
    def cookie_header(self):return '; '.join(k+'='+v for k,v in self.cookies.items())

    def validate(self):
        if not all(isinstance(x,str) for x in (self.account_id,self.expected_email,self.csrf,self.session_id,self.build_label,self.host)):raise Rejected('SESSION_INVALID')
        if self.host not in GOOGLE_HOSTS or not re.fullmatch('[A-Za-z0-9_-]{1,128}',self.account_id):raise Rejected('SESSION_INVALID')
        if not isinstance(self.expected_email,str) or not re.fullmatch(r'[^\s@"<>]+@[^\s@"<>]+\.[^\s@"<>]+',self.expected_email):raise Rejected('SESSION_INVALID')
        if not isinstance(self.cookies,dict) or not 1<=len(self.cookies)<=40:raise Rejected('SESSION_INVALID')
        for k,v in self.cookies.items():
            if not isinstance(k,str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}',k) or not isinstance(v,str) or not 1<=len(v)<=8192 or any(ord(c)<33 or ord(c)>126 or c in ';,' for c in v):raise Rejected('SESSION_INVALID')
        if not self.csrf or len(self.csrf)>4096 or any(ord(c)<32 for c in self.csrf):raise Rejected('SESSION_INVALID')
        if not re.fullmatch('-?[0-9]{1,64}',self.session_id) or not re.fullmatch('[A-Za-z0-9_.-]{1,256}',self.build_label):raise Rejected('SESSION_INVALID')
        if type(self.expires_at) not in (float,int) or not 0<self.expires_at<float('inf'):raise Rejected('SESSION_INVALID')
        if len(self.cookie_header())>32768:raise Rejected('SESSION_INVALID')
        return self

class CredentialStore(Protocol):
    def load(self)->Session: ...
    def save(self,session:Session)->None: ...
    def delete(self)->None: ...

def page_session(html,old,now):
    """Only unique reviewed internal fields; never generic email guessing."""
    if not isinstance(html,str) or len(html.encode())>2*1024*1024:raise Rejected('SESSION_REFRESH_STRUCTURE_CHANGED')
    if 'landing-header-signin' in html:raise Rejected('AUTHENTICATION_EXPIRED')
    def value(key):
        hits=re.findall('"'+key+r'"\s*:\s*("(?:[^"\\]|\\.)*")',html)
        try:values={json.loads(x) for x in hits}
        except ValueError:raise Rejected('SESSION_REFRESH_STRUCTURE_CHANGED') from None
        if len(values)!=1:raise Rejected('SESSION_REFRESH_STRUCTURE_CHANGED')
        return values.pop()
    email=value('oPEP7c')
    if email.casefold()!=old.expected_email.casefold():raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
    # Page tokens have a short local validation lifetime; this is not cookie renewal.
    return Session(old.account_id,old.expected_email,dict(old.cookies),value('SNlM0e'),
        value('FdrFJe'),value('cfb2h'),now+300,old.host).validate()

class SessionManager:
    """Refresh once before dispatch, never retry a query or recover a browser silently."""
    def __init__(self,store,account_id,expected_email,host,clock=time.time):
        self.store=store;self.account_id=account_id;self.expected_email=expected_email
        self.host=host;self.clock=clock;self.current=None;self.state='UNVALIDATED';self.lock=threading.RLock()
        self._redactions=[]
    def _accept_binding(self,s):
        s.validate()
        if (s.account_id,s.expected_email.casefold(),s.host)!=(self.account_id,self.expected_email.casefold(),self.host):raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
        return s
    def ensure(self,refresh):
        with self.lock:
            if self.state in ('REVOKED','DISABLED'):raise Rejected('SERVICE_DISABLED')
            if self.current is not None and self.current.expires_at>self.clock():return self.current
            old=self._accept_binding(self.store.load());self._redactions=old.secrets()
            self.state='REFRESHING'
            try:
                new=self._accept_binding(refresh(old,self.clock()))
                if new.expires_at<=self.clock():raise Rejected('AUTHENTICATION_EXPIRED')
                self._redactions+=new.secrets();self.store.save(new)
            except Exception:
                self.current=None;self.state='AUTH_REQUIRED'
                raise
            self.current=new;self.state='VALIDATED_PAGE_AND_RPC';return new
    def invalidate(self):
        with self.lock:self.current=None;self.state='AUTH_REQUIRED'
    def secrets(self):return tuple(self._redactions)
    def revoke(self):
        with self.lock:
            self.state='REVOKED';self.current=None;self.store.delete()
    def close(self):
        with self.lock:self.state='DISABLED';self.current=None
