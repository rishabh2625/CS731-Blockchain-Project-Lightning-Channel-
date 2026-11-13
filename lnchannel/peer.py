"""An independent, durable peer. The local harness transports JSON over stdio.

This is a deliberately serialized prepare/sign/revoke protocol, not BOLT wire
compatibility. Every peer derives and verifies its own transactions.
"""
import json
import sys
from copy import deepcopy
from . import crypto, shachain, state as model
from .storage import Store
from .commitment import build, other
from .bitcoin import Transaction, TxIn, TxOut, p2wsh, p2wpkh, p2pkh_code

class Peer:
    def __init__(self, path, name):
        other(name)
        self.store = Store(path)
        self.data = self.store.load()
        if self.data is None:
            self.data = {'name': name, 'keys': {k: crypto.new_secret().hex() for k in ('funding','payment','delayed','htlc','revocation')},
                         'seed': crypto.new_secret().hex(), 'history': [], 'chain': shachain.ShaChain().export(), 'preimages': {}, 'closed': False}
            self.save('create')
        if self.data['name'] != name: raise ValueError('Peer database belongs to another name')
        self.name = name

    def save(self, kind): self.store.save(self.data, kind)
    def key(self, name): return bytes.fromhex(self.data['keys'][name])
    def secret(self, number): return shachain.secret(bytes.fromhex(self.data['seed']), number)
    def public(self): return {k: crypto.pubkey(bytes.fromhex(v)).hex() for k,v in self.data['keys'].items()}
    def point(self, number): return crypto.pubkey(self.secret(number)).hex()

    def status(self):
        return {'name': self.name, 'public': self.public(), 'state': self.data.get('current', {}).get('state'),
                'pending': self.data.get('pending', {}).get('state'), 'closed': self.data['closed']}

    def configure(self, config):
        if 'config' in self.data:
            if self.data['config'] != config: raise ValueError('Configuration is immutable')
            return True
        if config['public'][self.name] != self.public(): raise ValueError('Local keys mismatch')
        for k in ('capacity','delay','dust','feerate_per_kw'): model.integer(config[k], k, 1)
        if not 1 <= config['delay'] <= 65535: raise ValueError('CSV delay range')
        if config['funder'] not in ('alice','bob'): raise ValueError('Invalid funder')
        self.data['config'] = config
        self.save('configure'); return True

    def prepare(self, points, action=None):
        if self.data['closed']: raise ValueError('Channel closed')
        config = self.data['config']
        if 'pending' in self.data: raise ValueError('Unfinished update: resume it before a new payment')
        current = self.data.get('current')
        if current:
            candidate = model.transition(config, current['state'], action, points)
        else:
            if action is not None: raise ValueError('Initial state has no payment action')
            candidate = {'number': 0, 'balances': config['initial_balances'], 'htlcs': [], 'next_id': 0, 'points': points}
            model.validate(config, candidate)
        if points[self.name] != self.point(candidate['number']): raise ValueError('Wrong local commitment point')
        for p in points.values(): crypto.PublicKey(bytes.fromhex(p))
        self.data['pending'] = {'state': candidate, 'remote_sigs': None, 'revealed': not current, 'received': not current}
        if action and action['type'] == 'fulfill':
            self.data['preimages'][current['state']['htlcs'][0]['hash']] = action['preimage']
        self.save('prepare')
        return candidate

    def sign_remote(self):
        pending = self.data['pending']
        c = build(self.data['config'], pending['state'], other(self.name))
        result = {'commitment': crypto.sign(self.key('funding'), c.tx.sighash(0, c.funding_script, self.data['config']['capacity'])).hex(), 'htlcs': {}}
        hkey = crypto.derive_private(self.key('htlc'), c.point)
        for i,o in enumerate(c.outputs):
            if o.kind == 'htlc':
                tx = c.second_stage(i, self.data['config']['feerate_per_kw'])
                result['htlcs'][str(i)] = crypto.sign(hkey, tx.sighash(0, o.witness_script, o.value)).hex()
        self.save('sign_remote')
        return result

    def accept_signatures(self, bundle):
        p = self.data['pending']; cfg = self.data['config']
        c = build(cfg, p['state'], self.name)
        remote = bytes.fromhex(cfg['public'][other(self.name)]['funding'])
        if not crypto.verify(remote, bytes.fromhex(bundle['commitment']), c.tx.sighash(0, c.funding_script, cfg['capacity'])):
            raise ValueError('Invalid commitment signature')
        expected = {str(i) for i,o in enumerate(c.outputs) if o.kind == 'htlc'}
        if set(bundle['htlcs']) != expected: raise ValueError('HTLC signature set mismatch')
        for i in expected:
            index = int(i); o = c.outputs[index]; tx = c.second_stage(index, cfg['feerate_per_kw'])
            if not crypto.verify(c.remote_htlc, bytes.fromhex(bundle['htlcs'][i]), tx.sighash(0, o.witness_script, o.value)):
                raise ValueError('Invalid HTLC signature')
        p['remote_sigs'] = bundle
        self.save('accept_signatures'); return True

    def revoke(self):
        p = self.data['pending']
        if not p['remote_sigs']: raise ValueError('Cannot revoke before durable replacement signatures')
        old = self.data.get('current')
        if not old: return None
        p['revealed'] = True
        self.save('reveal_old_secret')
        n = old['state']['number']
        return {'number': n, 'secret': self.secret(n).hex()}

    def receive_revocation(self, message):
        if message is None: return True
        p = self.data['pending']; old = self.data['current']['state']; value = bytes.fromhex(message['secret'])
        if message['number'] != old['number']: raise ValueError('Unexpected revoked state')
        if crypto.pubkey(value).hex() != old['points'][other(self.name)]: raise ValueError('Revocation point mismatch')
        chain = shachain.ShaChain(self.data['chain']); index = shachain.MAX_INDEX - old['number']
        if p['received']:
            if chain.get(index) != value: raise ValueError('Conflicting replay')
            return True
        chain.insert(index, value)
        self.data['chain'] = chain.export(); p['received'] = True
        self.save('receive_revocation'); return True

    def finalize(self):
        p = self.data.get('pending')
        if p is None: return self.data['current']['state']
        if not (p['remote_sigs'] and p['revealed'] and p['received']): raise ValueError('Update not fully secured')
        if 'current' in self.data: self.data['history'].append(self.data['current'])
        self.data['current'] = {'state': p['state'], 'remote_sigs': p['remote_sigs']}
        del self.data['pending']
        self.save('finalize'); return self.data['current']['state']

    def record(self, number=None):
        current = self.data['current']
        if number is None or number == current['state']['number']: return current
        for r in self.data['history']:
            if r['state']['number'] == number: return r
        raise ValueError('Unknown state')

    def commitment(self, number=None, allow_revoked=False):
        if 'pending' in self.data: raise ValueError('Update pending: resolve it before publishing')
        r = self.record(number)
        if r != self.data['current'] and not allow_revoked: raise ValueError('Refusing revoked state; explicit attack-demo flag required')
        cfg = self.data['config']; c = build(cfg, r['state'], self.name)
        own = crypto.sign(self.key('funding'), c.tx.sighash(0, c.funding_script, cfg['capacity'])) + b'\x01'
        remote = bytes.fromhex(r['remote_sigs']['commitment']) + b'\x01'
        pairs = [(bytes.fromhex(cfg['public'][self.name]['funding']), own), (bytes.fromhex(cfg['public'][other(self.name)]['funding']), remote)]
        c.tx.inputs[0].witness = [b''] + [s for _,s in sorted(pairs)] + [c.funding_script]
        return {'hex': c.tx.hex(), 'txid': c.tx.txid, 'number': r['state']['number'], 'vsize': c.tx.vsize,
                'fee_sat': cfg['capacity'] - sum(o.value for o in c.tx.outputs)}

    def sweep(self, owner, number, index, mode, fee=1000, preimage=None):
        """Construct a particular resolution path without requesting a new peer signature."""
        model.integer(fee, 'fee', 1)
        cfg = self.data['config']; r = self.record(number); c = build(cfg, r['state'], owner)
        if not 0 <= index < len(c.outputs): raise ValueError('Output index')
        o = c.outputs[index]
        destination = p2wpkh(crypto.pubkey(self.key('payment')))
        def single(amount=o.value, txid=c.tx.txid, vout=index, sequence=0xfffffffd, locktime=0):
            if amount - fee < 546: raise ValueError('Resolution fee leaves dust')
            return Transaction([TxIn(txid, vout, sequence)], [TxOut(amount-fee, destination)], locktime)
        if mode == 'remote':
            if owner == self.name or o.kind != 'remote': raise ValueError('Not our immediate output')
            tx = single(); key = self.key('payment')
            tx.inputs[0].witness = [crypto.sign(key, tx.sighash(0, p2pkh_code(crypto.pubkey(key)), o.value)) + b'\x01', crypto.pubkey(key)]
        elif mode in ('delayed','justice'):
            if mode == 'delayed':
                if owner != self.name or o.kind != 'local': raise ValueError('Not our delayed output')
                tx = single(sequence=cfg['delay']); key = crypto.derive_private(self.key('delayed'), c.point); branch = b''
            else:
                if owner == self.name or o.kind == 'remote': raise ValueError('Not a remote revocable output')
                revealed = shachain.ShaChain(self.data['chain']).get(shachain.MAX_INDEX-number)
                key = crypto.revocation_private(self.key('revocation'), revealed)
                tx = single(); branch = crypto.pubkey(key) if o.kind == 'htlc' else b'\x01'
            tx.inputs[0].witness = [crypto.sign(key, tx.sighash(0, o.witness_script, o.value)) + b'\x01', branch, o.witness_script]
        elif mode in ('htlc','second_delayed','second_justice'):
            if o.kind != 'htlc': raise ValueError('Not an HTLC output')
            second = c.second_stage(index, cfg['feerate_per_kw'])
            if mode == 'second_justice':
                if owner == self.name: raise ValueError('Cannot punish self')
                revealed = shachain.ShaChain(self.data['chain']).get(shachain.MAX_INDEX-number)
                key = crypto.revocation_private(self.key('revocation'), revealed)
                tx = single(second.outputs[0].value, second.txid, 0)
                tx.inputs[0].witness = [crypto.sign(key, tx.sighash(0, c.delayed_script, second.outputs[0].value)) + b'\x01', b'\x01', c.delayed_script]
            elif mode == 'second_delayed':
                if owner != self.name: raise ValueError('Not our second stage')
                key = crypto.derive_private(self.key('delayed'), c.point)
                tx = single(second.outputs[0].value, second.txid, 0, cfg['delay'])
                tx.inputs[0].witness = [crypto.sign(key, tx.sighash(0, c.delayed_script, second.outputs[0].value)) + b'\x01', b'', c.delayed_script]
            else:
                is_owner = owner == self.name
                needs_preimage = (is_owner and not o.offered) or (not is_owner and o.offered)
                value = bytes.fromhex(preimage or self.data['preimages'].get(o.htlc['hash'], '')) if needs_preimage else b''
                if needs_preimage and (len(value) != 32 or crypto.sha256(value).hex() != o.htlc['hash']): raise ValueError('Missing/wrong payment preimage')
                key = crypto.derive_private(self.key('htlc'), c.point)
                if is_owner:
                    tx = second
                    own = crypto.sign(key, tx.sighash(0, o.witness_script, o.value)) + b'\x01'
                    remote = bytes.fromhex(r['remote_sigs']['htlcs'][str(index)]) + b'\x01'
                    tx.inputs[0].witness = [b'', remote, own, value, o.witness_script]
                else:
                    tx = single(locktime=0 if needs_preimage else o.htlc['expiry'])
                    tx.inputs[0].witness = [crypto.sign(key, tx.sighash(0, o.witness_script, o.value)) + b'\x01', value, o.witness_script]
        else: raise ValueError('Unknown resolution mode')
        return {'hex': tx.hex(), 'txid': tx.txid, 'vsize': tx.vsize}

    def mark_closed(self):
        self.data['closed'] = True; self.save('close_detected'); return True

    def fee_child(self, txid, index, amount, fee):
        """Spend our own payment-key output, for CPFP and isolated policy tests."""
        for name,value in [('amount',amount),('fee',fee)]: model.integer(value,name,1)
        if amount-fee<546: raise ValueError('Child would be dust')
        key=self.key('payment'); pub=crypto.pubkey(key)
        tx=Transaction([TxIn(txid,index,0xfffffffd)],[TxOut(amount-fee,p2wpkh(pub))])
        tx.inputs[0].witness=[crypto.sign(key,tx.sighash(0,p2pkh_code(pub),amount))+b'\x01',pub]
        return {'hex':tx.hex(),'txid':tx.txid,'vsize':tx.vsize}

    def dispatch(self, method, params):
        methods = {'status':self.status, 'point':self.point, 'configure':self.configure, 'prepare':self.prepare,
                   'sign_remote':self.sign_remote, 'accept_signatures':self.accept_signatures, 'revoke':self.revoke,
                   'receive_revocation':self.receive_revocation, 'finalize':self.finalize, 'commitment':self.commitment,
                   'sweep':self.sweep, 'mark_closed':self.mark_closed, 'fee_child':self.fee_child}
        if method not in methods: raise ValueError('Unknown method')
        snapshot = deepcopy(self.data)
        try: return methods[method](**params)
        except Exception:
            self.data = snapshot
            raise

def serve(path, name):
    peer = Peer(path, name)
    try:
        for line in sys.stdin:
            try:
                if len(line) > 1_000_000: raise ValueError('Message too large')
                request = json.loads(line)
                result = {'ok': True, 'result': peer.dispatch(request['method'], request.get('params', {}))}
            except Exception as exc:
                result = {'ok':False, 'error':f'{type(exc).__name__}: {exc}'}
            print(json.dumps(result), flush=True)
    finally: peer.store.close()

if __name__ == '__main__': serve(sys.argv[1], sys.argv[2])
