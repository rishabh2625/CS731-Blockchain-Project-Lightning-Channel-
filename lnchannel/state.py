"""Deterministic whole-satoshi state transitions for the fixed one-HTLC profile."""
from copy import deepcopy
from .crypto import sha256
from .commitment import other, build

def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum: raise ValueError(f'Invalid {name}')
    return value

def validate(config, state):
    for name in ('alice', 'bob'): integer(state['balances'][name], 'balance')
    if sum(state['balances'].values()) + sum(h['amount'] for h in state['htlcs']) != config['capacity']:
        raise ValueError('Channel value not conserved')
    if len(state['htlcs']) > 1: raise ValueError('This profile allows one pending HTLC')
    for owner in ('alice', 'bob'): build(config, state, owner)

def transition(config, previous, action, points):
    state = deepcopy(previous)
    state['number'] += 1
    state['points'] = points
    kind = action['type']
    if kind == 'add':
        if state['htlcs']: raise ValueError('Pending HTLC limit reached')
        sender = action['sender']; other(sender)
        amount = integer(action['amount'], 'amount', 1)
        integer(action['id'], 'HTLC id')
        expiry = integer(action['expiry'], 'expiry', 1)
        height = integer(action['height'], 'height')
        if not height + 2 <= expiry < 500_000_000: raise ValueError('Expiry outside block-height window')
        if len(bytes.fromhex(action['hash'])) != 32: raise ValueError('Payment hash must be 32 bytes')
        if amount > state['balances'][sender]: raise ValueError('Insufficient balance')
        if action['id'] != state['next_id']: raise ValueError('Duplicate or out-of-order HTLC id')
        state['balances'][sender] -= amount
        state['htlcs'] = [{k: action[k] for k in ('id', 'sender', 'amount', 'hash', 'expiry')}]
        state['next_id'] += 1
    elif kind in ('fulfill', 'fail'):
        if not state['htlcs'] or action['id'] != state['htlcs'][0]['id']: raise ValueError('Unknown HTLC')
        h = state['htlcs'][0]
        if kind == 'fulfill':
            preimage = bytes.fromhex(action['preimage'])
            if len(preimage) != 32 or sha256(preimage).hex() != h['hash']: raise ValueError('Wrong preimage')
            recipient = other(h['sender'])
        else: recipient = h['sender']
        state['balances'][recipient] += h['amount']
        state['htlcs'] = []
    else: raise ValueError('Unknown transition')
    validate(config, state)
    return state
