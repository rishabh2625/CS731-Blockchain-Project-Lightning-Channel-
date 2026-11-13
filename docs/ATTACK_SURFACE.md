# Fee inflation and pinning analysis

## 1. Security question and scope

A signature makes a transaction valid; it does not guarantee timely inclusion in a block. A penalty channel's protection depends on both valid spending conditions and access to block space before a competing spend becomes available. We analyze our static-remote-key, non-anchor profile with fixed feerate and Bitcoin Core 28.1. Core's policy is distinct from Bitcoin consensus.

## 2. Fee inflation: what becomes expensive?

Two mechanisms should be distinguished:

1. **External fee-market increases.** A transaction signed earlier may offer an unattractive fee when it later needs confirmation. An honest resolver may have only a limited response window. We do not generate an external competitive fee market or measure actual miner prioritization under congestion.
2. **Negotiated commitment fees and trimming.** Higher agreed rates increase settlement cost and can remove small HTLC outputs. This implementation fixes the rate at opening; it does not accept `update_fee` messages or simulate a malicious peer forcing fee updates. Its proposed-state checks reject negative funder balances.

For this profile, with rate `r` in sat/kw and `N` retained HTLCs:

```text
commitment base fee = floor((724 + 172*N) * r / 1000)
offered HTLC retention threshold = dust + floor(663*r/1000)
received HTLC retention threshold = dust + floor(703*r/1000)
actual fee = funding input amount - sum(commitment outputs)
```

The actual fee includes trimmed value. Trimming is part of the specified transaction format; it does not produce an independently spendable small HTLC output. This is why quoting only the base fee can understate settlement cost.

`tools/analyze_fees.py` reconstructs both no-HTLC and pending-HTLC commitments using recorded public keys and state, across rates from 1,000 to 100,000 sat/kw. It records both thresholds, retained outputs and actual fees. These are hypothetical alternative negotiated configurations, not newly signed or mined transactions and not unilateral repricing of old signatures. See [generated table and JSON](../evidence/FEE_ANALYSIS.md).

At 5,000 sat/kw the no-HTLC base fee is 3,620 sat; one retained HTLC raises it to 4,480 sat. At 100,000 sat/kw a 50,000-sat HTLC is below either retention threshold. Its trimmed value adds to the actual commitment fee. This illustrates sensitivity, not evidence that a remote party can arbitrarily raise this engine's fixed rate.

## 3. Controlled replacement-fee obstruction

Threat capability: the counterparty knows an offered HTLC's preimage, can construct a conflicting direct spend and can spend that output in a child. The channel owner already holds a presigned timeout with a fixed fee. The experiment is run after timeout maturity, when both conflicting spends can be valid.

```text
confirmed commitment HTLC output
  |-- owner timeout: fixed fee 3,315 sat, 165 vbytes
  `-- counterparty preimage spend: fee 500 sat
        `-- child: fee 10,000 sat
```

Before the child exists, Core accepts the owner's timeout as a replacement candidate. After the child is accepted, the same timeout is rejected with `insufficient fee`. The total fees that would be evicted increased from 500 to 10,500 sat. The timeout's 3,315 sat cannot cover that total even before considering incremental replacement requirements. The unchanged signature/transaction remains valid in isolation; the rejection is about relay policy in the current mempool.

Both regtest and private-signet runs retain the before/after RPC responses, actual transaction hex and confirmation records. The script extracts fees from those saved RPC records rather than guessing from a requested fee parameter. See [quantitative observations](../evidence/FEE_ANALYSIS.md) and [raw case](../evidence/regtest/fee_obstruction.json).

Interpretation: this demonstrates absolute replacement-fee obstruction in a controlled topology. The child itself costs the counterparty money if mined. Both preimage spend and child are subsequently mined; we do not establish a durable low-cost pin or loss of funds. The preimage was intentionally known for the experiment, so this is not a claim that the counterparty redeemed an unknown secret or stole an unpaid HTLC. A fixed-fee timeout being rejected does not alone prove theft.

## 4. Monitoring deadline and consequences

In `missed_window`, the revoked broadcaster waits until CSV maturity and confirms its delayed withdrawal. A subsequently constructed justice spend is rejected as `missing-inputs`: its target was already spent. In successful breach cases, justice spends confirm before that withdrawal. This demonstrates the timing assumption, not an empirical probability of an internet-wide congestion attack.

Fee obstruction can matter because response windows are finite. Our two experiments illustrate separate ingredients; they do not establish that the measured replacement obstruction caused the missed penalty in a combined end-to-end attack.

## 5. Defenses and their limits

| Direction | Purpose | Status in this repository |
| --- | --- | --- |
| Durable replacement signatures before revocation | Avoid losing an enforceable newer state through premature secret release | Implemented and unit tested |
| Timely monitoring / redundant watchtowers | Detect a revoked funding spend and respond within the delay | Invoked local resolver implemented; persistent outsourced service is future work |
| Fee bounds, exposure budgets, reserve checks | Limit accepted settlement expense and dust exposure | Fixed rate and nonnegative-balance checks only; negotiated policy budgets are future work |
| Anchor / modern commitment profiles and fee-bumping funds | Permit appropriate child-fee contributions and improve settlement flexibility | Future work; signatures and output formats must change together |
| Policy-aware package and replacement evaluation | Test whether a proposed rescue is relayable under the deployed version | Core acceptance checked in the lab; multi-version and adversarial-network evaluation is future work |
| Larger delay and operational monitoring margin | Give more time to respond | Six-block lab delay is a demonstration parameter, not a production recommendation |

Increasing a fee is not automatically possible on a presigned two-party transaction. It requires permitted signature semantics, an available child output or cooperation as appropriate to the channel profile. Anchors should not be described as a universal cure for every pinning topology.

## 6. Reproduction and primary references

Run `python tools/analyze_fees.py` for the sensitivity table and extraction of recorded observations. Run `python -m lnchannel demo --case fee_obstruction --case missed_window --output evidence/recheck-policy` for fresh Core-backed scenarios. Install and configure the pinned environment using the README first.

- [Pinned BOLT 3](https://github.com/lightning/bolts/blob/191462825ae341f0a27098765c075f01ca9bc6c2/03-transactions.md): fees, trimming, script format and alternative profiles.
- [Pinned BOLT 5](https://github.com/lightning/bolts/blob/191462825ae341f0a27098765c075f01ca9bc6c2/05-onchain.md): on-chain resolution responsibilities.
- [Core 28.1 replacement policy source](https://github.com/bitcoin/bitcoin/blob/v28.1/src/policy/rbf.cpp): version-specific policy context; actual acceptance is recorded in our RPC evidence.
- [Maintainer pinning analysis](https://github.com/t-bast/lightning-docs/blob/master/pinning-attacks.md): broader attack taxonomy, beyond our measured topology.
- [Harris and Zohar, Flood & Loot](https://www.avivz.net/pubs/2020/flood_loot.pdf): systemic settlement-pressure research; its network-wide results are not our results.

