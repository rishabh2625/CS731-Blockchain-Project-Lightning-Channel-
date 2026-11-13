import json
from pathlib import Path

import pytest

from lnchannel.peer import Peer

BOLT3_VECTORS = json.loads((Path(__file__).parent / 'fixtures' / 'bolt3_vectors.json').read_text(encoding='utf-8'))

@pytest.fixture
def pair(tmp_path):
    peers={n:Peer(tmp_path/(n+'.sqlite'),n) for n in ('alice','bob')}
    config={'capacity':2_000_000,'funding_txid':'11'*32,'funding_vout':0,'funder':'alice','delay':6,'dust':546,
            'feerate_per_kw':5000,'initial_balances':{'alice':1_000_000,'bob':1_000_000},'public':{n:p.public() for n,p in peers.items()}}
    for p in peers.values(): p.configure(config)
    yield peers,config
    for p in peers.values(): p.store.close()

def update(peers,action=None,stop=None):
    number=peers['alice'].data.get('current',{}).get('state',{}).get('number',-1)+1
    points={n:p.point(number) for n,p in peers.items()}
    for p in peers.values(): p.prepare(points,action)
    if stop=='prepare': return
    signatures={n:p.sign_remote() for n,p in peers.items()}
    peers['alice'].accept_signatures(signatures['bob']); peers['bob'].accept_signatures(signatures['alice'])
    if stop=='sign': return
    messages={n:p.revoke() for n,p in peers.items()}
    peers['alice'].receive_revocation(messages['bob']); peers['bob'].receive_revocation(messages['alice'])
    for p in peers.values(): p.finalize()

def addition(amount=50_000):
    from lnchannel.crypto import sha256
    return {'type':'add','sender':'alice','amount':amount,'id':0,'hash':sha256(bytes(32)).hex(),'expiry':120,'height':100}
