"""Local stdio transport: private keys stay in separate peer processes/databases."""
import json
import os
import subprocess
import sys
from .commitment import other

class PeerClient:
    def __init__(self, path, name):
        self.name = name
        self.process = subprocess.Popen([sys.executable, '-m', 'lnchannel.peer', str(path), name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    def call(self, method, **params):
        self.process.stdin.write(json.dumps({'method':method,'params':params})+'\n'); self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line: raise RuntimeError('Peer terminated: '+self.process.stderr.read())
        response = json.loads(line)
        if not response['ok']: raise ValueError(response['error'])
        return response['result']
    def close(self):
        self.process.stdin.close()
        try: self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate(); self.process.wait(timeout=5)

class Session:
    def __init__(self, directory):
        self.peers = {n: PeerClient(directory / f'{n}.sqlite', n) for n in ('alice','bob')}
    def public(self): return {n:p.call('status')['public'] for n,p in self.peers.items()}
    def configure(self, config):
        self.config = config
        for p in self.peers.values(): p.call('configure', config=config)
    def update(self, action=None):
        status = self.peers['alice'].call('status')
        number = 0 if status['state'] is None else status['state']['number']+1
        points = {n:p.call('point',number=number) for n,p in self.peers.items()}
        for p in self.peers.values(): p.call('prepare',points=points,action=action)
        return self.complete_pending()
    def complete_pending(self):
        """Replay pre-finalization phases idempotently; reject ambiguous divergent journals."""
        statuses = {n:p.call('status') for n,p in self.peers.items()}
        pending = [s['pending'] for s in statuses.values() if s['pending']]
        if not pending: return statuses['alice']['state']
        if len(pending) == 1:
            # A crash between the final two finalize calls is recoverable.
            name = next(n for n,s in statuses.items() if s['pending'])
            if statuses[other(name)]['state'] != pending[0]: raise ValueError('Divergent preparation: manual recovery required')
            return self.peers[name].call('finalize')
        if pending[0] != pending[1]: raise ValueError('Divergent pending states')
        signatures = {n:p.call('sign_remote') for n,p in self.peers.items()}
        for n,p in self.peers.items(): p.call('accept_signatures',bundle=signatures[other(n)])
        revocations = {n:p.call('revoke') for n,p in self.peers.items()}
        for n,p in self.peers.items(): p.call('receive_revocation',message=revocations[other(n)])
        results = [p.call('finalize') for p in self.peers.values()]
        if results[0] != results[1]: raise ValueError('Final state disagreement')
        return results[0]
    def close(self):
        for p in self.peers.values(): p.close()
