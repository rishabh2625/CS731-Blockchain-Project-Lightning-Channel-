"""Construct commitments from public data; never require the counterparty secret."""
from dataclasses import dataclass
from . import scripts
from .bitcoin import Transaction, TxIn, TxOut, p2wsh, p2wpkh
from .crypto import sha256, derive_public, revocation_public

def other(name):
    if name not in ('alice', 'bob'): raise ValueError('Unknown peer')
    return 'bob' if name == 'alice' else 'alice'

@dataclass
class Output:
    kind: str
    value: int
    script: bytes
    witness_script: bytes = b''
    htlc: dict | None = None
    offered: bool = False

@dataclass
class Commitment:
    tx: Transaction
    outputs: list[Output]
    funding_script: bytes
    delayed_script: bytes
    revocation: bytes
    local_htlc: bytes
    remote_htlc: bytes
    owner: str
    point: bytes
    def second_stage(self, index, feerate):
        output = self.outputs[index]
        if output.kind != 'htlc': raise ValueError('Not an HTLC')
        fee = (663 if output.offered else 703) * feerate // 1000
        return Transaction([TxIn(self.tx.txid, index, 0)],
                           [TxOut(output.value - fee, p2wsh(self.delayed_script))],
                           output.htlc['expiry'] if output.offered else 0)

def build(config, state, owner):
    remote = other(owner)
    keys = {p: {k: bytes.fromhex(v) for k, v in config['public'][p].items()} for p in ('alice', 'bob')}
    point = bytes.fromhex(state['points'][owner])
    rev = revocation_public(keys[remote]['revocation'], point)
    delayed = derive_public(keys[owner]['delayed'], point)
    local_htlc = derive_public(keys[owner]['htlc'], point)
    remote_htlc = derive_public(keys[remote]['htlc'], point)
    delayed_script = scripts.to_local(rev, delayed, config['delay'])
    funding_script = scripts.funding(keys['alice']['funding'], keys['bob']['funding'])
    outputs = []
    rate, dust = config['feerate_per_kw'], config['dust']
    for h in state['htlcs']:
        offered = h['sender'] == owner
        second_fee = (663 if offered else 703) * rate // 1000
        if h['amount'] < dust + second_fee: continue
        ws = scripts.htlc(rev, local_htlc, remote_htlc, bytes.fromhex(h['hash']), h['expiry'], offered)
        outputs.append(Output('htlc', h['amount'], p2wsh(ws), ws, h, offered))
    fee = (724 + 172 * len(outputs)) * rate // 1000
    balances = dict(state['balances'])
    balances[config['funder']] -= fee
    if min(balances.values()) < 0: raise ValueError('Funder cannot afford commitment fee')
    if balances[owner] >= dust:
        outputs.append(Output('local', balances[owner], p2wsh(delayed_script), delayed_script))
    if balances[remote] >= dust:
        outputs.append(Output('remote', balances[remote], p2wpkh(keys[remote]['payment'])))
    outputs.sort(key=lambda o: (o.value, o.script, o.htlc['expiry'] if o.htlc else 0))
    mask = int.from_bytes(sha256(keys[config['funder']]['payment'] + keys[other(config['funder'])]['payment'])[-6:], 'big')
    obscured = state['number'] ^ mask
    tx = Transaction([TxIn(config['funding_txid'], config['funding_vout'], 0x80000000 | (obscured >> 24))],
                     [TxOut(o.value, o.script) for o in outputs], 0x20000000 | (obscured & 0xffffff))
    if not outputs: raise ValueError('Commitment would have no outputs')
    return Commitment(tx, outputs, funding_script, delayed_script, rev, local_htlc, remote_htlc, owner, point)
