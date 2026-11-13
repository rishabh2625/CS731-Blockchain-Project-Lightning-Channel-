"""Reproduce a sensitivity analysis and explain saved Core policy observations.

The rate sweep reconstructs public commitments; it is not a new mining experiment.
"""
import copy
import json
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lnchannel.commitment import build


def main():
    source = ROOT / 'evidence/regtest/htlc_success.json'
    data = json.loads(source.read_text())
    pending = next(s for s in data['states'] if s['htlcs'])
    empty = data['states'][0]
    rows = []
    for rate in (1000, 5000, 10000, 25000, 100000):
        for name, state in (('no HTLC', empty), ('50,000-sat HTLC', pending)):
            config = copy.deepcopy(data['config'])
            config['feerate_per_kw'] = rate
            c = build(config, state, 'alice')
            count = sum(o.kind == 'htlc' for o in c.outputs)
            rows.append({'rate_sat_per_kw': rate, 'approx_target_sat_per_vb': rate / 250,
                         'state': name, 'untrimmed_htlcs': count,
                         'base_fee_sat': (724 + 172 * count) * rate // 1000,
                         'actual_commitment_fee_sat': config['capacity'] - sum(o.value for o in c.tx.outputs),
                         'offered_htlc_threshold_sat': config['dust'] + 663 * rate // 1000,
                         'received_htlc_threshold_sat': config['dust'] + 703 * rate // 1000})
    observations = []
    for chain in ('regtest', 'private-signet'):
        path = ROOT / 'evidence' / chain / 'fee_obstruction.json'
        d = json.loads(path.read_text())
        txs = {t['label']: t for t in d['transactions']}
        def fee(label):
            return int(Decimal(str(txs[label]['acceptance']['fees']['base'])) * 100_000_000)
        p = d['replacement_probe']
        observations.append({'network': chain, 'core_version': d['core_version'],
                             'conflicting_spend_fee_sat': fee('conflicting_preimage_spend'),
                             'descendant_fee_sat': fee('descendant_increasing_replacement_cost'),
                             'timeout_fee_sat': int(Decimal(str(p['before_descendant']['fees']['base'])) * 100_000_000),
                             'timeout_vsize': p['fixed_timeout']['vsize'],
                             'before_allowed': p['before_descendant']['allowed'],
                             'after_allowed': p['after_descendant']['allowed'],
                             'reject_reason': p['after_descendant']['reject-reason']})
    result = {'method': 'Unsigned public commitment reconstruction at hypothetical negotiated rates; Core observations reused from saved runs',
              'source': 'regtest/htlc_success.json', 'sensitivity': rows, 'policy_observations': observations}
    (ROOT / 'evidence/fee-analysis.json').write_text(json.dumps(result, indent=2) + '\n')
    lines = ['# Fee sensitivity and replacement observations', '', result['method'] + '.', '',
             '| sat/kw | Approx. target sat/vB | State | Retained HTLCs | Base fee sat | Actual commitment fee sat | Offered / received threshold sat |',
             '| ---: | ---: | --- | ---: | ---: | ---: | --- |']
    for r in rows:
        lines.append(f"| {r['rate_sat_per_kw']} | {r['approx_target_sat_per_vb']:g} | {r['state']} | {r['untrimmed_htlcs']} | {r['base_fee_sat']} | {r['actual_commitment_fee_sat']} | {r['offered_htlc_threshold_sat']} / {r['received_htlc_threshold_sat']} |")
    lines += ['', 'These are separate hypothetical negotiated configurations. They do not show unilateral repricing of an already signed commitment. The target conversion is rate/250; measured signed vsize can differ from the BOLT fee-weight estimate.', '',
              '| Network | Conflicting spend fee | Descendant fee | Fixed timeout fee | Timeout vbytes | Before / after accepted | Rejection |',
              '| --- | ---: | ---: | ---: | ---: | --- | --- |']
    for r in observations:
        lines.append(f"| {r['network']} | {r['conflicting_spend_fee_sat']} | {r['descendant_fee_sat']} | {r['timeout_fee_sat']} | {r['timeout_vsize']} | {r['before_allowed']} / {r['after_allowed']} | {r['reject_reason']} |")
    lines += ['', 'The descendant increases total fees evicted by the replacement from 500 to 10,500 sat. The 3,315-sat timeout cannot cover that total, even before incremental replacement requirements. This is a controlled obstruction; it does not establish durable theft or confirmation delay under a competing external fee market.', '']
    (ROOT / 'evidence/FEE_ANALYSIS.md').write_text('\n'.join(lines), encoding='utf-8')
    print('Wrote evidence/fee-analysis.json and evidence/FEE_ANALYSIS.md')


if __name__ == '__main__':
    main()
