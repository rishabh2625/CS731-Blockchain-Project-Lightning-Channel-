"""Byte-for-byte independent BOLT 3 Appendix C commitment fixture."""
from conftest import BOLT3_VECTORS
from lnchannel.crypto import pubkey,sign
from lnchannel.commitment import build

def test_published_complete_commitment():
    def public(secret): return pubkey(bytes.fromhex(secret)).hex()
    local_funding='30ff4956bbdd3222d44cc5e8a1261dab1e07957bdac5ae88fe3261ef321f3749'
    remote_funding='1552dfba4f6cf29a62a0af13c8d6981d36d0ef8d61ba10fb0fe90da7634d7e13'
    local={'funding':public(local_funding),'payment':public('11'*32),'delayed':public('33'*32),'htlc':public('11'*32),'revocation':public('22'*32)}
    remote={'funding':public(remote_funding),'payment':public('44'*32),'delayed':public('33'*32),'htlc':public('44'*32),'revocation':public('22'*32)}
    point=pubkey(bytes(reversed(range(32)))).hex()
    config={'public':{'alice':local,'bob':remote},'capacity':10_000_000,'funder':'alice','delay':144,'dust':546,'feerate_per_kw':15000,
        'funding_txid':'8984484a580b825b9972d7adb15050b3ab624ccd731946b3eeddb92f4e7ef6be','funding_vout':0}
    state={'number':42,'balances':{'alice':7_000_000,'bob':3_000_000},'htlcs':[],'points':{'alice':point,'bob':point}}
    c=build(config,state,'alice'); digest=c.tx.sighash(0,c.funding_script,config['capacity'])
    c.tx.inputs[0].witness=[b'',sign(bytes.fromhex(local_funding),digest)+b'\x01',sign(bytes.fromhex(remote_funding),digest)+b'\x01',c.funding_script]
    assert c.tx.hex() == BOLT3_VECTORS['commitment_tx_hex']
