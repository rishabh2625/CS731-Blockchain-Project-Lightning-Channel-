from copy import deepcopy
import pytest
from lnchannel.commitment import build
from lnchannel.peer import Peer
from conftest import update,addition

def test_revoke_requires_valid_replacement(pair):
    peers,_=pair; update(peers); update(peers,addition(),stop='prepare')
    with pytest.raises(ValueError,match='Cannot revoke'): peers['alice'].revoke()

def test_bad_signature_does_not_advance(pair):
    peers,_=pair; update(peers,stop='prepare')
    bundle=peers['bob'].sign_remote(); bundle['commitment']='00'*70
    with pytest.raises(ValueError,match='signature'): peers['alice'].accept_signatures(bundle)
    assert peers['alice'].data['pending']['remote_sigs'] is None

def test_missing_htlc_signature_rejected(pair):
    peers,_=pair; update(peers); update(peers,addition(),stop='prepare')
    bundle=peers['bob'].sign_remote(); bundle['htlcs']={}
    with pytest.raises(ValueError,match='signature set'): peers['alice'].accept_signatures(bundle)

@pytest.mark.parametrize('field,value',[('amount',0),('amount',-1),('amount',True),('amount',2_000_001),('id',7),('expiry',100),('hash','00')])
def test_invalid_payment_rejected(pair,field,value):
    peers,_=pair; update(peers); a=addition(); a[field]=value
    points={n:p.point(1) for n,p in peers.items()}
    with pytest.raises(ValueError): peers['alice'].prepare(points,a)
    assert 'pending' not in peers['alice'].data

@pytest.mark.parametrize('outcome',['fulfill','fail'])
def test_accounting_and_revocation(pair,outcome):
    peers,cfg=pair; update(peers); update(peers,addition())
    action={'type':outcome,'id':0}
    if outcome=='fulfill': action['preimage']='00'*32
    update(peers,action)
    a=peers['alice'].data['current']['state']; b=peers['bob'].data['current']['state']
    assert a==b and not a['htlcs']
    assert a['balances']['alice']==(950_000 if outcome=='fulfill' else 1_000_000)
    with pytest.raises(ValueError,match='revoked'): peers['alice'].commitment(0)
    assert peers['alice'].commitment(0,True)['txid']!=peers['bob'].commitment(0,True)['txid']

def test_wrong_preimage_and_pending_limit(pair):
    peers,_=pair; update(peers); update(peers,addition())
    points={n:p.point(2) for n,p in peers.items()}
    with pytest.raises(ValueError,match='preimage'): peers['alice'].prepare(points,{'type':'fulfill','id':0,'preimage':'11'*32})
    with pytest.raises(ValueError,match='limit'): peers['alice'].prepare(points,addition())

def test_restart_preserves_pending_exit(pair,tmp_path):
    peers,_=pair; update(peers); update(peers,addition(),stop='sign')
    peers['alice'].store.close()
    peers['alice']=Peer(tmp_path/'alice.sqlite','alice')
    assert peers['alice'].data['pending']['remote_sigs']
    message=peers['alice'].revoke(); assert message['number']==0
    # Replays return identical old-state information rather than advancing again.
    assert peers['alice'].revoke()==message

def test_wrong_revocation_and_no_early_finalize(pair):
    peers,_=pair; update(peers); update(peers,addition(),stop='sign')
    with pytest.raises(ValueError): peers['alice'].receive_revocation({'number':0,'secret':'11'*32})
    with pytest.raises(ValueError): peers['alice'].finalize()

def test_dust_and_fee_conservation(pair):
    peers,cfg=pair; update(peers); update(peers,addition(100))
    for name in peers:
        c=build(cfg,peers[name].data['current']['state'],name)
        assert not any(o.kind=='htlc' for o in c.outputs)
        assert cfg['capacity']-sum(o.value for o in c.outputs)==724*cfg['feerate_per_kw']//1000+100

def test_closed_peer_refuses_updates(pair):
    peers,_=pair; update(peers); peers['alice'].mark_closed()
    with pytest.raises(ValueError,match='closed'): peers['alice'].prepare({},addition())
