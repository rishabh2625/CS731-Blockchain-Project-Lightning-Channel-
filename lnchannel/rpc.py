"""Small cookie-authenticated JSON-RPC adapter; no wallet keys enter the engine."""
import base64
import json
import urllib.request
import urllib.error
from urllib.parse import quote
from pathlib import Path

class RPCError(RuntimeError):
    def __init__(self, error):
        self.error = error
        super().__init__(f"RPC {error['code']}: {error['message']}")

class RPC:
    def __init__(self, url, cookie, wallet=None):
        self.url, self.cookie, self.wallet = url.rstrip('/'), Path(cookie), wallet
    def call(self, method, *params):
        token = base64.b64encode(self.cookie.read_text().strip().encode()).decode()
        url = self.url + ('/wallet/'+quote(self.wallet,safe='') if self.wallet else '')
        request = urllib.request.Request(url, json.dumps({'jsonrpc':'2.0','id':'lnlab','method':method,'params':params}).encode(),
                                         {'Authorization':'Basic '+token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=60) as response: data = json.load(response)
        except urllib.error.HTTPError as exc:
            data = json.loads(exc.read())
        if data.get('error'): raise RPCError(data['error'])
        return data['result']
