# Recorded validation results

Generated from the saved JSON/XML evidence. These are test-network results, not a production safety claim.

Unit/vector suite: **30 passed, 0 failed, 1 skipped**.
The opt-in Core integration test is normally skipped by the fast unit command; Core runs are reported separately below.

## Core-backed scenarios

| Network | Scenario | Confirmed recorded transactions | Outcome |
| --- | --- | ---: | --- |
| regtest | [honest_alice](regtest/honest_alice.json) | 4 | passed |
| regtest | [honest_bob](regtest/honest_bob.json) | 4 | passed |
| regtest | [breach_alice](regtest/breach_alice.json) | 4 | passed |
| regtest | [breach_bob](regtest/breach_bob.json) | 4 | passed |
| regtest | [htlc_success](regtest/htlc_success.json) | 6 | passed |
| regtest | [htlc_timeout](regtest/htlc_timeout.json) | 6 | passed |
| regtest | [htlc_direct_success](regtest/htlc_direct_success.json) | 5 | passed |
| regtest | [htlc_direct_timeout](regtest/htlc_direct_timeout.json) | 5 | passed |
| regtest | [htlc_breach](regtest/htlc_breach.json) | 5 | passed |
| regtest | [second_stage_breach](regtest/second_stage_breach.json) | 6 | passed |
| regtest | [missed_window](regtest/missed_window.json) | 4 | passed |
| regtest | [fee_obstruction](regtest/fee_obstruction.json) | 6 | passed |
| private OP_TRUE signet | [honest_alice](private-signet/honest_alice.json) | 4 | passed |
| private OP_TRUE signet | [honest_bob](private-signet/honest_bob.json) | 4 | passed |
| private OP_TRUE signet | [breach_alice](private-signet/breach_alice.json) | 4 | passed |
| private OP_TRUE signet | [breach_bob](private-signet/breach_bob.json) | 4 | passed |
| private OP_TRUE signet | [htlc_success](private-signet/htlc_success.json) | 6 | passed |
| private OP_TRUE signet | [htlc_timeout](private-signet/htlc_timeout.json) | 6 | passed |
| private OP_TRUE signet | [htlc_direct_success](private-signet/htlc_direct_success.json) | 5 | passed |
| private OP_TRUE signet | [htlc_direct_timeout](private-signet/htlc_direct_timeout.json) | 5 | passed |
| private OP_TRUE signet | [htlc_breach](private-signet/htlc_breach.json) | 5 | passed |
| private OP_TRUE signet | [second_stage_breach](private-signet/second_stage_breach.json) | 6 | passed |
| private OP_TRUE signet | [missed_window](private-signet/missed_window.json) | 4 | passed |
| private OP_TRUE signet | [fee_obstruction](private-signet/fee_obstruction.json) | 6 | passed |

A passed negative scenario means the expected rejection or loss of rescue opportunity was observed. Signet here is private, not the public default network.

## Actual commitment cost examples

| Example | vbytes | Fee (sat) | Effective sat/vB |
| --- | ---: | ---: | ---: |
| honest_alice | 181 | 3620 | 20.00 |
| htlc_success | 224 | 4480 | 20.00 |
| htlc_timeout | 224 | 4480 | 20.00 |

The commitment rate input is sat/kw; the effective measured rate above is sat/vB. Fixed presigned transactions cannot be changed unilaterally merely by choosing a new target rate.

## Off-chain local latency

HTLC add plus fulfill including both durable transitions.
Two peer processes on one Windows host, SQLite FULL synchronous, loopback Core; no artificial network latency.

| Run | Payments | Durable updates | Median ms/payment | p95 ms/payment |
| --- | ---: | ---: | ---: | ---: |
| 1 | 50 | 100 | 126.61 | 182.60 |
| 2 | 50 | 100 | 133.28 | 187.06 |
| 3 | 50 | 100 | 128.84 | 219.49 |

Runtime: Python 3.12.14; Core /Satoshi:28.1.0/; Windows-11-10.0.26200-SP0.
These timings include durable peer state transitions, exclude blockchain confirmation, and do not estimate public Lightning throughput. Raw samples are in [benchmark.json](benchmark.json).

## Replacement-policy observation

Before descendant: allowed=True. After descendant: allowed=False; rejection: `insufficient fee`.
Absolute replacement-fee obstruction, not a sustained network-wide theft reproduction.

## Missed response window

Late penalty acceptance: False; rejection: `missing-inputs`. The broadcaster's delayed withdrawal had already confirmed.

## Interpretation limits

No public-default-signet, mainnet, cross-implementation interoperability, WAN performance or independent security audit is claimed. Core 28.1 policy is version-specific. Inspect the source evidence for transaction hex, block hashes and parameters.
