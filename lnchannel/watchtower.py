"""A local breach resolver scanning actual blocks for the channel funding spend.

Not an outsourced watchtower: this helper uses the honest peer's private API.
"""
from .commitment import build

def find_funding_spend(rpc, txid, vout, start_height):
    for height in range(start_height, rpc.call('getblockcount')+1):
        block=rpc.call('getblock',rpc.call('getblockhash',height),2)
        for tx in block['tx']:
            if any(i.get('txid')==txid and i.get('vout')==vout for i in tx['vin']):
                return {'txid':tx['txid'],'height':height,'blockhash':block['hash']}
    return None

def classify(config, states, txid):
    for s in reversed(states):
        for owner in ('alice','bob'):
            c=build(config,s,owner)
            if c.tx.txid==txid:
                return {'owner':owner,'number':s['number'],'revoked':s['number']<states[-1]['number'],'commitment':c}
    return None

def respond_to_breach(rpc, honest_peer, config, states, start_height):
    spend=find_funding_spend(rpc,config['funding_txid'],config['funding_vout'],start_height)
    if not spend: return {'status':'open','penalties':[]}
    match=classify(config,states,spend['txid'])
    honest_peer.call('mark_closed')
    if not match: return {'status':'unknown_funding_spend','spend':spend,'penalties':[]}
    if not match['revoked']: return {'status':'latest_close','spend':spend,'penalties':[]}
    if match['owner']==honest_peer.name: return {'status':'own_revoked_state','spend':spend,'penalties':[]}
    penalties=[]
    for index,o in enumerate(match['commitment'].outputs):
        if o.kind=='remote': continue
        # If an HTLC was already moved to its second stage, sweep that instead.
        unspent=rpc.call('gettxout',spend['txid'],index)
        mode='justice'
        if not unspent:
            if o.kind!='htlc': continue
            second=match['commitment'].second_stage(index,config['feerate_per_kw'])
            if not rpc.call('gettxout',second.txid,0): continue
            mode='second_justice'
        result=honest_peer.call('sweep',owner=match['owner'],number=match['number'],index=index,mode=mode)
        check=rpc.call('testmempoolaccept',[result['hex']])[0]
        if not check['allowed']: raise ValueError(f'Penalty rejected: {check}')
        rpc.call('sendrawtransaction',result['hex'])
        penalties.append({**result,'acceptance':check,'mode':mode})
    return {'status':'breach_responded','spend':spend,'penalties':penalties}
