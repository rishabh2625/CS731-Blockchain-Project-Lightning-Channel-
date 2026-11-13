"""Render measured evidence into a Markdown summary without inventing results."""
import json
from pathlib import Path
from decimal import Decimal
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
lines=['# Recorded validation results','','Generated from the saved JSON/XML evidence. These are test-network results, not a production safety claim.','']
xml=root/'evidence/unit-tests.xml'
if xml.exists():
    suites=ET.parse(xml).getroot().findall('testsuite')
    tests=sum(int(s.get('tests',0)) for s in suites)
    failures=sum(int(s.get('failures',0))+int(s.get('errors',0)) for s in suites)
    skipped=sum(int(s.get('skipped',0)) for s in suites)
    lines += [f'Unit/vector suite: **{tests-skipped-failures} passed, {failures} failed, {skipped} skipped**.',
              'The opt-in Core integration test is normally skipped by the fast unit command; Core runs are reported separately below.','']
lines += ['## Core-backed scenarios','','| Network | Scenario | Confirmed recorded transactions | Outcome |','| --- | --- | ---: | --- |']
for directory in ('regtest','private-signet'):
    path=root/'evidence'/directory/'summary.json'
    if not path.exists(): continue
    summary=json.loads(path.read_text())
    for case in summary['cases']:
        evidence=root/'evidence'/directory/(case['scenario']+'.json')
        data=json.loads(evidence.read_text())
        count=sum(t.get('confirmations',0)>0 for t in data['transactions'])
        label='private OP_TRUE signet' if summary.get('private_signet') else summary['network']
        lines.append(f"| {label} | [{case['scenario']}]({directory}/{case['scenario']}.json) | {count} | {case['result']} |")
lines += ['','A passed negative scenario means the expected rejection or loss of rescue opportunity was observed. Signet here is private, not the public default network.','',
          '## Actual commitment cost examples','','| Example | vbytes | Fee (sat) | Effective sat/vB |','| --- | ---: | ---: | ---: |']
for name in ('honest_alice','htlc_success','htlc_timeout'):
    path=root/'evidence/regtest'/(name+'.json')
    if not path.exists(): continue
    data=json.loads(path.read_text())
    tx=next(t for t in data['transactions'] if t['label']=='latest_commitment')
    fee=tx['fee_sat']; size=tx['vsize']
    lines.append(f'| {name} | {size} | {fee} | {fee/size:.2f} |')
lines += ['','The commitment rate input is sat/kw; the effective measured rate above is sat/vB. Fixed presigned transactions cannot be changed unilaterally merely by choosing a new target rate.','']
path=root/'evidence/benchmark.json'
if path.exists():
    data=json.loads(path.read_text())
    lines += ['## Off-chain local latency','',data['metric']+'.',data['environment']+'.','',
              '| Run | Payments | Durable updates | Median ms/payment | p95 ms/payment |','| --- | ---: | ---: | ---: | ---: |']
    for r in data['runs']:
        lines.append(f"| {r['run']+1} | {r['payments']} | {r['updates']} | {r['median_ms']:.2f} | {r['p95_ms']:.2f} |")
    lines += ['',f"Runtime: Python {data['python']}; Core {data['core']}; {data['platform']}.",
              'These timings include durable peer state transitions, exclude blockchain confirmation, and do not estimate public Lightning throughput. Raw samples are in [benchmark.json](benchmark.json).','']
for name,key in [('fee_obstruction','replacement_probe'),('missed_window','late_penalty_rejection')]:
    path=root/'evidence/regtest'/(name+'.json')
    if path.exists():
        value=json.loads(path.read_text())[key]
        if name=='fee_obstruction':
            lines += ['## Replacement-policy observation','',
                f"Before descendant: allowed={value['before_descendant']['allowed']}. After descendant: allowed={value['after_descendant']['allowed']}; rejection: `{value['after_descendant'].get('reject-reason')}`.",
                value['scope']+'.','']
        else:
            lines += ['## Missed response window','',f"Late penalty acceptance: {value['allowed']}; rejection: `{value.get('reject-reason')}`. The broadcaster's delayed withdrawal had already confirmed.",'']
lines += ['## Interpretation limits','','No public-default-signet, mainnet, cross-implementation interoperability, WAN performance or independent security audit is claimed. Core 28.1 policy is version-specific. Inspect the source evidence for transaction hex, block hashes and parameters.']
(root/'evidence/RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Wrote evidence/RESULTS.md')
