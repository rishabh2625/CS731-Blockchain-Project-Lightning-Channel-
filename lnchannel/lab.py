"""End-to-end scenarios with real Core validation and public evidence outputs."""
import json
import secrets
import time
from decimal import Decimal
from pathlib import Path
from .bitcoin import p2wsh
from .scripts import funding
from .crypto import sha256
from .commitment import build, other
from .transport import Session
from .network import Network
from .watchtower import respond_to_breach

class ChannelLab:
    def __init__(self, network, directory):
        self.network=network; self.node=network.nodes[0]; self.rpc=self.node.rpc
        if self.rpc.call('getblockchaininfo')['chain'] not in ('regtest','signet'):
            raise ValueError('This laboratory only operates on regtest or signet')
        self.session=Session(Path(directory)); self.states=[]; self.evidence=[]
        public=self.session.public()
        script=funding(bytes.fromhex(public['alice']['funding']),bytes.fromhex(public['bob']['funding']))
        address=self.rpc.call('decodescript',script.hex())['segwit']['address']
        capacity=2_000_000
        psbt=self.node.wallet.call('walletcreatefundedpsbt',[],[{address:str(Decimal(capacity)/100_000_000)}],0,{'fee_rate':2})['psbt']
        signed=self.node.wallet.call('walletprocesspsbt',psbt)['psbt']
        finished=self.node.wallet.call('finalizepsbt',signed)
        if not finished['complete']: raise RuntimeError('Funding signatures incomplete')
        raw=finished['hex']; decoded=self.rpc.call('decoderawtransaction',raw)
        index=next(o['n'] for o in decoded['vout'] if o['scriptPubKey']['hex']==p2wsh(script).hex())
        self.config={'capacity':capacity,'funding_txid':decoded['txid'],'funding_vout':index,'funder':'alice',
                     'initial_balances':{'alice':1_000_000,'bob':1_000_000},'public':public,'delay':6,'dust':546,'feerate_per_kw':5000}
        self.session.configure(self.config)
        self.states.append(self.session.update())
        # Both durable exits exist before the funding transaction leaves the wallet.
        for p in self.session.peers.values(): p.call('commitment')
        self.start_height=self.rpc.call('getblockcount')
        self.broadcast({'hex':raw,'txid':decoded['txid']},'funding')
        self.network.mine()

    def broadcast(self, tx, label):
        check=self.rpc.call('testmempoolaccept',[tx['hex']])[0]
        if not check['allowed']: raise ValueError(f'{label} rejected: {check}')
        txid=self.rpc.call('sendrawtransaction',tx['hex'])
        self.evidence.append({'label':label,**tx,'txid':txid,'acceptance':check})
        return txid

    def add(self, sender='alice', amount=50_000, preimage=None):
        preimage=preimage or secrets.token_bytes(32).hex()
        h=self.rpc.call('getblockcount')
        action={'type':'add','id':self.states[-1]['next_id'],'sender':sender,'amount':amount,
                'hash':sha256(bytes.fromhex(preimage)).hex(),'height':h,'expiry':h+12}
        self.states.append(self.session.update(action)); return preimage

    def finish(self, preimage=None):
        action={'type':'fulfill' if preimage else 'fail','id':self.states[-1]['htlcs'][0]['id']}
        if preimage: action['preimage']=preimage
        self.states.append(self.session.update(action))

    def publish(self, owner, number=None, revoked=False):
        p=self.session.peers[owner]
        tx=p.call('commitment',number=number,allow_revoked=revoked)
        self.broadcast(tx,'revoked_commitment' if revoked else 'latest_commitment'); self.network.mine()
        for peer in self.session.peers.values(): peer.call('mark_closed')
        return build(self.config,next(s for s in self.states if s['number']==tx['number']),owner)

    def save(self, path, scenario, extra=None):
        for entry in self.evidence:
            raw=self.rpc.call('getrawtransaction',entry['txid'],True)
            entry['confirmations']=raw.get('confirmations',0)
            entry['blockhash']=raw.get('blockhash')
        result={'scenario':scenario,'network':self.rpc.call('getblockchaininfo')['chain'],
                'network_description':'Private OP_TRUE signet' if self.rpc.call('getblockchaininfo')['chain']=='signet' else 'Isolated regtest',
                'nodes':[{'name':name,'height':node.rpc.call('getblockcount'),'tip':node.rpc.call('getbestblockhash')} for name,node in zip(('alice','bob'),self.network.nodes)],
                'core_version':self.rpc.call('getnetworkinfo')['subversion'],
                'config':self.config,'states':self.states,'transactions':self.evidence,**(extra or {})}
        Path(path).write_text(json.dumps(result,indent=2),encoding='utf-8'); return result

    def resolve_main_outputs(self):
        """Finish all still-unspent main outputs after a scenario has tested its target path."""
        from .watchtower import classify
        closed=next((e for e in self.evidence if e['label'] in ('latest_commitment','revoked_commitment')),None)
        if not closed: return
        match=classify(self.config,self.states,closed['txid']); c=match['commitment']; owner=match['owner']
        self.network.mine(self.config['delay'])
        for i,o in enumerate(c.outputs):
            if o.kind=='htlc' or not self.rpc.call('gettxout',c.tx.txid,i): continue
            name=owner if o.kind=='local' else other(owner)
            tx=self.session.peers[name].call('sweep',owner=owner,number=match['number'],index=i,mode='delayed' if o.kind=='local' else 'remote')
            self.broadcast(tx,'remaining_main_output')
        self.network.mine()

    def close(self): self.session.close()

def run_scenarios(output, cases=None, chain='regtest'):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    runtime=Path('.runtime')/('run-'+str(time.time_ns())); runtime.mkdir(parents=True)
    network=Network(runtime/'chain',chain); summary=[]
    cases=cases or ['honest_alice','honest_bob','breach_alice','breach_bob','htlc_success','htlc_timeout','htlc_direct_success','htlc_direct_timeout','htlc_breach','second_stage_breach','missed_window','fee_obstruction']
    try:
        for case in cases:
            lab=ChannelLab(network,runtime/case)
            try:
                extra={}
                if case.startswith('honest'):
                    owner=case.split('_')[1]
                    for sender in ('alice','bob'):
                        preimage=lab.add(sender); lab.finish(preimage)
                    lab.add(); lab.finish()  # explicit off-chain failure
                    c=lab.publish(owner)
                    for i,o in enumerate(c.outputs):
                        if o.kind=='local':
                            tx=lab.session.peers[owner].call('sweep',owner=owner,number=lab.states[-1]['number'],index=i,mode='delayed')
                            early=lab.rpc.call('testmempoolaccept',[tx['hex']])[0]
                            if early['allowed']: raise AssertionError('CSV delay was not enforced')
                            extra['premature_spend']=early
                            network.mine(lab.config['delay'])
                            lab.broadcast(tx,'delayed_sweep')
                        elif o.kind=='remote':
                            tx=lab.session.peers[other(owner)].call('sweep',owner=owner,number=lab.states[-1]['number'],index=i,mode='remote')
                            lab.broadcast(tx,'immediate_sweep')
                    network.mine()
                elif case=='missed_window':
                    preimage=lab.add(); lab.finish(preimage)
                    c=lab.publish('alice',0,True)
                    i=next(i for i,o in enumerate(c.outputs) if o.kind=='local')
                    network.mine(lab.config['delay'])
                    tx=lab.session.peers['alice'].call('sweep',owner='alice',number=0,index=i,mode='delayed')
                    lab.broadcast(tx,'cheater_withdrawal_after_delay'); network.mine()
                    justice=lab.session.peers['bob'].call('sweep',owner='alice',number=0,index=i,mode='justice')
                    check=lab.rpc.call('testmempoolaccept',[justice['hex']])[0]
                    if check['allowed']: raise AssertionError('Already spent output accepted')
                    extra['late_penalty_rejection']=check
                elif case=='fee_obstruction':
                    preimage=lab.add(amount=500_000); c=lab.publish('alice')
                    i=next(i for i,o in enumerate(c.outputs) if o.kind=='htlc')
                    expiry=c.outputs[i].htlc['expiry']; network.mine(max(1,expiry-lab.rpc.call('getblockcount')))
                    timeout=lab.session.peers['alice'].call('sweep',owner='alice',number=1,index=i,mode='htlc')
                    success=lab.session.peers['bob'].call('sweep',owner='alice',number=1,index=i,mode='htlc',preimage=preimage,fee=500)
                    lab.broadcast(success,'conflicting_preimage_spend')
                    before=lab.rpc.call('testmempoolaccept',[timeout['hex']])[0]
                    child=lab.session.peers['bob'].call('fee_child',txid=success['txid'],index=0,amount=499_500,fee=10_000)
                    lab.broadcast(child,'descendant_increasing_replacement_cost')
                    after=lab.rpc.call('testmempoolaccept',[timeout['hex']])[0]
                    if not before['allowed'] or after['allowed']: raise AssertionError(f'Unexpected pinned-version policy: {before}, {after}')
                    extra['replacement_probe']={'before_descendant':before,'after_descendant':after,
                        'scope':'Absolute replacement-fee obstruction, not a sustained network-wide theft reproduction',
                        'fixed_timeout':timeout}
                    network.mine()
                elif case.startswith('breach'):
                    owner=case.split('_')[1]
                    preimage=lab.add(owner); lab.finish(preimage)
                    lab.publish(owner,0,True)
                    response=respond_to_breach(lab.rpc,lab.session.peers[other(owner)],lab.config,lab.states,lab.start_height)
                    for tx in response['penalties']: lab.evidence.append({'label':'justice',**tx})
                    extra['watcher']=response; network.mine()
                elif case in ('htlc_breach','second_stage_breach'):
                    owner='alice'; preimage=lab.add('bob'); old=lab.states[-1]['number']
                    lab.finish(preimage); c=lab.publish(owner,old,True)
                    if case=='second_stage_breach':
                        i=next(i for i,o in enumerate(c.outputs) if o.kind=='htlc')
                        tx=lab.session.peers[owner].call('sweep',owner=owner,number=old,index=i,mode='htlc',preimage=preimage)
                        lab.broadcast(tx,'cheater_htlc_success'); network.mine()
                    response=respond_to_breach(lab.rpc,lab.session.peers['bob'],lab.config,lab.states,lab.start_height)
                    for tx in response['penalties']: lab.evidence.append({'label':'justice',**tx})
                    extra['watcher']=response; network.mine()
                else:
                    owner='alice'
                    sender='bob' if case in ('htlc_success','htlc_direct_timeout') else 'alice'
                    preimage=lab.add(sender); c=lab.publish(owner)
                    i=next(i for i,o in enumerate(c.outputs) if o.kind=='htlc')
                    if 'timeout' in case:
                        expiry=c.outputs[i].htlc['expiry']; network.mine(max(1,expiry-lab.rpc.call('getblockcount')))
                    resolver='bob' if 'direct' in case else owner
                    tx=lab.session.peers[resolver].call('sweep',owner=owner,number=lab.states[-1]['number'],index=i,mode='htlc',preimage=preimage)
                    lab.broadcast(tx,case); network.mine()
                    if resolver==owner:
                        network.mine(lab.config['delay'])
                        tx=lab.session.peers[owner].call('sweep',owner=owner,number=lab.states[-1]['number'],index=i,mode='second_delayed')
                        lab.broadcast(tx,'second_stage_sweep'); network.mine()
                lab.resolve_main_outputs()
                result=lab.save(output/(case+'.json'),case,extra)
                if any(t['confirmations']<1 for t in result['transactions']): raise AssertionError('Unconfirmed evidence')
                summary.append({'scenario':case,'result':'passed','transactions':len(result['transactions'])})
                print(case+': PASS',flush=True)
            finally: lab.close()
        (output/'summary.json').write_text(json.dumps({'network':chain,'private_signet':chain=='signet','cases':summary},indent=2))
        return summary
    finally: network.close()
