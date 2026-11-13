"""Isolated two-node regtest harness. Never touches an existing Bitcoin data directory."""
import os
import socket
import subprocess
import time
from pathlib import Path
from .rpc import RPC

ROOT = Path(__file__).resolve().parents[1]

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); return s.getsockname()[1]

def core_binary():
    configured = os.environ.get('BITCOIND')
    if configured: return Path(configured)
    found = list((ROOT/'.tools').glob('bitcoin-*/bin/bitcoind.exe'))
    if not found: raise FileNotFoundError('Set BITCOIND or run tools/fetch_core.py')
    return sorted(found)[-1]

class Node:
    def __init__(self, directory, chain='regtest'):
        if chain not in ('regtest','signet'): raise ValueError('Test networks only')
        self.chain=chain
        self.directory = Path(directory).resolve(); self.directory.mkdir(parents=True,exist_ok=True)
        self.port, self.rpcport = free_port(), free_port()
        args = [str(core_binary()), '-'+chain, '-server=1', '-txindex=1', '-dnsseed=0','-discover=0',
                '-listen=1', '-connect=0', '-fallbackfee=0.0002', '-persistmempool=0', '-printtoconsole=0',
                f'-datadir={self.directory}', f'-rpcport={self.rpcport}', f'-port={self.port}', '-bind=127.0.0.1']
        if chain=='signet': args.extend(['-signetchallenge=51','-signetseednode=','-minimumchainwork=0'])
        self.log = open(self.directory/'process.log','w')
        self.process = subprocess.Popen(args, stdout=self.log, stderr=self.log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.rpc = RPC(f'http://127.0.0.1:{self.rpcport}', self.directory/chain/'.cookie')
        deadline = time.monotonic()+45
        while time.monotonic()<deadline:
            try: self.rpc.call('getblockchaininfo'); break
            except Exception:
                if self.process.poll() is not None: raise RuntimeError((self.directory/'process.log').read_text())
                time.sleep(.1)
        else: self.close(); raise TimeoutError('Core startup timeout')
        self.rpc.call('createwallet','lab')
        self.wallet = RPC(self.rpc.url,self.rpc.cookie,'lab')
        self.address = self.wallet.call('getnewaddress','','bech32')
    def mine(self,n=1):
        if self.chain=='regtest': return self.rpc.call('generatetoaddress',n,self.address)
        from .signet import mine
        return mine(self,n)
    def close(self):
        try: self.rpc.call('stop')
        except Exception: pass
        try: self.process.wait(timeout=15)
        except subprocess.TimeoutExpired: self.process.terminate(); self.process.wait(timeout=5)
        self.log.close()

class Network:
    def __init__(self, directory, chain='regtest'):
        self.nodes = []
        try:
            self.nodes.append(Node(Path(directory)/'alice-core',chain))
            self.nodes.append(Node(Path(directory)/'bob-core',chain))
            self.nodes[0].rpc.call('addnode',f'127.0.0.1:{self.nodes[1].port}','onetry')
            self.nodes[0].mine(101)
            self.sync()
        except Exception:
            self.close(); raise
    def sync(self):
        target = self.nodes[0].rpc.call('getbestblockhash')
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if self.nodes[1].rpc.call('getbestblockhash') == target: return
            time.sleep(.1)
        raise TimeoutError('Two test nodes failed to synchronize')
    def mine(self,n=1):
        hashes=self.nodes[0].mine(n); self.sync(); return hashes
    def close(self):
        for node in reversed(self.nodes): node.close()
