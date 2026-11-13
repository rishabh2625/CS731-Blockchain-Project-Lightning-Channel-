"""Measure durable local-process payment latency; never imply public-network TPS."""
import json
import platform
import statistics
import time
from pathlib import Path
from .network import Network
from .lab import ChannelLab

def run(output='evidence/benchmark.json',payments=50,runs=3):
    if not 1<=payments<=1000 or not 1<=runs<=10: raise ValueError('Invalid benchmark size')
    root=Path('.runtime')/('benchmark-'+str(time.time_ns())); root.mkdir(parents=True)
    network=Network(root/'chain'); results=[]
    try:
        for run_id in range(runs):
            lab=ChannelLab(network,root/f'channel-{run_id}')
            try:
                samples=[]
                for i in range(payments):
                    start=time.perf_counter_ns()
                    preimage=lab.add('alice' if i%2==0 else 'bob',10_000)
                    lab.finish(preimage)
                    samples.append((time.perf_counter_ns()-start)/1_000_000)
                ordered=sorted(samples)
                results.append({'run':run_id,'payments':payments,'updates':payments*2,'milliseconds':samples,
                    'median_ms':statistics.median(samples),'p95_ms':ordered[max(0,__import__('math').ceil(.95*len(samples))-1)]})
            finally: lab.close()
        result={'metric':'HTLC add plus fulfill including both durable transitions',
            'environment':'Two peer processes on one Windows host, SQLite FULL synchronous, loopback Core; no artificial network latency',
            'python':platform.python_version(),'platform':platform.platform(),'processor':platform.processor(),
            'core':network.nodes[0].rpc.call('getnetworkinfo')['subversion'],'runs':results}
        path=Path(output); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(result,indent=2))
        print(json.dumps({str(r['run']):{'median_ms':r['median_ms'],'p95_ms':r['p95_ms']} for r in results},indent=2))
    finally: network.close()
