# Implementing a Lightning Payment Channel

## 1. Problem and objective

Bitcoin's base layer records transactions in a shared blockchain. Repeated small payments between the same participants each consume block space if settled individually. A payment channel commits funds once, allows the participants to update their allocation privately, and retains an enforceable exit through Bitcoin transactions.

The engineering question is: **How can Alice and Bob repeatedly change their balances while retaining a usable exit if their peer disappears or publishes an old state?** This project implements the mechanism and demonstrates its assumptions with actual Bitcoin Core validation. The project does not propose a new consensus protocol or claim a new cryptographic construction.

Suppose a channel contains 2,000,000 satoshis, initially allocated 1,000,000 to each party. Alice pays Bob 50,000, changing their allocations to 950,000 and 1,050,000 before settlement costs. An old commitment that favors Alice still has valid signatures. Bitcoin does not know that a later off-chain agreement exists. The protocol must therefore make publication of a revoked state punishable rather than assuming the old transaction has disappeared.

Applications motivating the work include repeated small payments, payment streaming and services where settling each interaction individually is inefficient. The implementation demonstrates the building block for such applications; it does not implement a complete merchant payment system.

## 2. Existing approaches and current context

There are several ways to account for repeated transfers:

| Approach | Benefit | Relevant tradeoff |
| --- | --- | --- |
| Individual on-chain payments | Settlement is visible and validated by Bitcoin nodes | Every payment competes for block space and confirmation |
| A custodial balance service | Internal transfers can be fast and inexpensive | Users rely on the custodian for control and redemption |
| A penalty payment channel | Parties keep signed unilateral exits while updating off-chain | Requires liquidity, careful state storage, monitoring and timely on-chain response |

Poon and Dryja's 2016 whitepaper provides the foundational channel design. BOLT 2, 3 and 5 provide the operational specifications used for this implementation. The repository fixes one non-anchor, static-remote-key profile so its behavior can be reviewed and reproduced. [Lightning whitepaper](https://lightning.network/lightning-network-paper.pdf) · [Pinned BOLT 2](https://github.com/lightning/bolts/blob/191462825ae341f0a27098765c075f01ca9bc6c2/02-peer-protocol.md) · [Pinned BOLT 3](https://github.com/lightning/bolts/blob/191462825ae341f0a27098765c075f01ca9bc6c2/03-transactions.md) · [Pinned BOLT 5](https://github.com/lightning/bolts/blob/191462825ae341f0a27098765c075f01ca9bc6c2/05-onchain.md)

*Flood & Loot* examines systemic settlement pressure when many channels need timely blockchain access. *Congestion Attacks in Payment Channel Networks* studies pending-payment resource exhaustion inside channels. [Harris and Zohar, ACM AFT 2020](https://doi.org/10.1145/3419614.3423248) · [Mizrahi and Zohar, Financial Cryptography 2021](https://doi.org/10.1007/978-3-662-64331-0_9)

Fee bumping depends on how unconfirmed transactions are linked and how nodes apply their replacement policies. Our experiment records Bitcoin Core 28.1's behavior and the observed rejection reason for the tested format. [Maintainer pinning analysis](https://github.com/t-bast/lightning-docs/blob/master/pinning-attacks.md) · [BIP 431](https://github.com/bitcoin/bips/blob/master/bip-0431.mediawiki)

## 3. Our approach

We separate mechanism construction from its external correctness oracle. Python builds the transactions and implements channel transitions. Coincurve performs secp256k1 operations. Two independent Python peer processes own separate secrets and SQLite databases. Two Bitcoin Core nodes independently validate the resulting transactions on a local chain.

The test controller schedules user actions and transfers messages between peer processes. It does not supply private-key operations itself. Each peer independently constructs and checks the transaction for which it receives a signature. This makes errors in layout or signing observable as failed signature validation or rejected Bitcoin transactions.

We develop on regtest and also exercise a private signet. The private signet uses the explicit `OP_TRUE` challenge for controlled infrastructure, with actual signet block validation and proof-of-work. It is not the default public signet. The saved evidence identifies the network clearly; public signet funding, public relay conditions and public block timing have not been evaluated.

## 4. Implemented solution

### 4.1 Funding and safe opening

The engine constructs a P2WSH funding script with lexicographically sorted funding public keys and a 2-of-2 condition. Core's wallet creates and signs a transaction paying that output. The funding transaction is held locally while both peers obtain and durably store signatures for their initial commitment transactions. Only then does the lab broadcast funding and mine a confirmation.

This order matters: publishing funding before receiving an enforceable exit could leave the funder dependent on further cooperation. The test wallet is allowed to choose inputs and change because wallet coin selection is not the channel mechanism being implemented.

### 4.2 Commitments and accounting

Each party has its own commitment transaction spending the same funding output. For the broadcaster, its local output is delayed and revocable; the other participant receives an immediate P2WPKH output under the fixed profile. Pending HTLCs appear as additional conditional outputs when they exceed the applicable trimming threshold.

Balances are integers. Adding a pending payment moves its amount out of spendable balance into the pending HTLC record. Fulfillment credits the recipient; failure restores the sender. The implementation checks conservation at every proposed transition and subtracts the commitment fee from the configured funder. Trimmed outputs become additional fee. See the design document for exact units, formulas and rounding choices.

### 4.3 Revocation and state protection

The project implements the BOLT key-combination formulas and descending 48-bit per-commitment secret sequence. A compact receiving shachain checks consistency as new secrets become available. Revealing a particular old secret allows the counterparty to derive that commitment's revocation private key together with its own revocation base secret.

The peer only releases an old secret after verifying and persisting the replacement commitment and HTLC signatures. The local harness uses a serialized prepare/sign/revoke/finalize protocol. This preserves an explicit safety ordering for the educational implementation, while differing from the complete asynchronous BOLT 2 protocol and its wire messages.

State is saved using SQLite transactions, write-ahead logging and FULL synchronous mode. The snapshot contains everything needed by the peer; the audit table records transition labels without logging secrets. Replaying a completed secret exchange is idempotent. Ambiguous partial preparation is rejected rather than silently advancing a balance.

### 4.4 Conditional payments and exit paths

The code supports one active HTLC, with a block-height expiry and a SHA256 payment hash. It verifies the supplied preimage before fulfillment. An off-chain failure is a mutually committed state change, not a shortcut around an on-chain timelock.

The resolution builder implements the broadcaster's HTLC-success/HTLC-timeout second stage, the counterparty's direct success/timeout path, and delayed withdrawal from a second stage. It also implements revocation spending directly from an HTLC or after that HTLC has moved into a second-stage output. The latter is essential: a cheater should not escape the penalty by first taking its permitted second-stage path.

### 4.5 Monitoring and penalty enforcement

The local breach resolver scans actual blocks for a spend of the funding outpoint, matches the spending transaction to retained commitments, and identifies a latest-state close, known revoked state or unknown spend. On a known remote breach, it asks the honest peer to construct penalties and broadcasts transactions accepted by Core. It checks for a second-stage HTLC output when the original HTLC has already been spent.

This helper is a local chain monitor, despite its module name `watchtower.py`; it is not an outsourced encrypted watchtower service. It currently requires a known state history from the lab and does not implement a durable, continuously running reorg-aware service.

### 4.6 Fee and timing analysis

The repository includes two deliberately adverse scenarios. `missed_window` demonstrates that after the delayed owner spend confirms, a late penalty targeting that same output is rejected. `fee_obstruction` demonstrates a fixed-fee HTLC timeout being acceptable as a replacement before a descendant is attached, and unacceptable after that descendant increases the required replacement fee.

The second scenario is a transaction-policy constraint demonstration, not a reproduction of network-wide theft. Its high-fee child may confirm promptly; we do not claim persistent pinning under realistic adversarial network partitions. The script retains the exact transaction graph, Core acceptance responses and rejection detail so that the result is inspectable.

## 5. Design decisions and alternatives

| Decision | Reason | Cost or limitation |
| --- | --- | --- |
| Python with explicit serialization | Makes the channel transaction format easy to inspect | Not tuned for throughput |
| Native curve primitives | Reuses tested elliptic-curve and ECDSA operations | Depends on the pinned Coincurve version |
| Independent peer subprocesses | Keeps peer secrets and signing decisions separate | A local trusted controller still orchestrates inputs |
| SQLite snapshots and events | Atomic persistence is easy to inspect and replay | Snapshots grow with retained history; secrets are not encrypted at rest |
| One pending HTLC | Makes the state-space and demonstrations manageable | Does not exercise Lightning's full concurrency limits |
| Fixed non-anchor profile | Small, deterministic transaction model with published vectors | Fee flexibility differs from modern anchor-based profiles |
| Actual Core validation | Avoids mistaking an internal model for a Bitcoin-valid transaction | Requires a Core binary and local RPC access |
| Private signet | Reproducible two-node signet execution without faucet dependence | Does not test public default-signet operations |
| Full retained history plus compact secrets | Simplifies breach identification and evidence | Commitment retention is not production-scale storage optimization |

The companion [implementation document](IMPLEMENTATION.md) records the smaller choices as well: byte order, signature flags, sorting, dust, checkpoint ordering, subprocess transport, error propagation, confirmation claims, version pinning and source ownership.

## 6. Evaluation methodology and evidence

There are three layers of validation:

1. **Independent specification vectors.** Tests check BOLT key derivation, secret generation and published storage sequences. A complete signed commitment is compared byte for byte with the BOLT Appendix C fixture, jointly checking scripts, ordering, serialization, fees and signing digest.
2. **State safety tests.** Tests cover invalid signatures, missing HTLC signatures, incorrect preimages, amounts and expiries, double-pending requests, premature revocation/finalization, restart persistence, dust and refusal to publish an old state without an explicit attack-demo flag.
3. **Core-backed scenarios.** Every scenario supplies transaction hex to `testmempoolaccept`, broadcasts accepted transactions, mines them and retains confirmations/block hashes. Both honest and malicious close directions are exercised, along with all implemented HTLC resolution branches.

The authoritative measured counts, costs and latency summaries are generated in [RESULTS.md](../evidence/RESULTS.md). Its JSON source files contain reproducible detail. Tests of the mechanism do not constitute an independent security audit or a general proof of protocol safety.

The dedicated [fee-inflation and pinning analysis](ATTACK_SURFACE.md) separates external fee-market pressure, hypothetical negotiated-rate sensitivity, and our measured replacement obstruction. Its [quantitative appendix](../evidence/FEE_ANALYSIS.md) accounts for trimmed value and extracts actual RPC fees.

The benchmark measures an HTLC add followed by fulfillment, including both durable channel transitions between separate local Python processes. It measures 50 payments in each of three runs and records every sample. Blockchain confirmation time is outside that off-chain latency metric. The filesystem, background load and process placement influence results; measured local speed should not be advertised as public-network throughput.

## 7. Limitations and future prospects

The next development steps are ordered by their connection to present limitations:

1. **Crash/reconnect completeness:** implement formal per-message recovery rules for every interruption point, including asymmetric preparation and a valid close while a transition is in flight. Add fault injection across all persistence boundaries.
2. **Continuous monitoring and reorganizations:** persist scan checkpoints, detect common ancestors, rescan orphaned transactions, rebroadcast necessary spends and track outputs to a configured finality depth.
3. **Modern fee management:** add an explicitly negotiated anchor or newer commitment profile, dynamic fee policy and version-specific package-relay tests. Compare actual costs and failure modes rather than claiming that anchors solve every pin.
4. **Transport and interoperability:** implement BOLT 1/8 framing/transport and feature negotiation, then cross-check with an external Lightning implementation. The present local JSON interface is not a compatibility claim.
5. **More channel functionality:** multiple simultaneous HTLCs, cooperative close, more complete reserve/limit negotiation, multiple channels and routing, with a correspondingly larger test suite.
6. **Public test-network evaluation:** operate the same supported mechanism against two public-signet-backed nodes, collect confirmations under external block scheduling and test recovery from real peer disconnects.
7. **Usability and auditing:** an explanatory interface, encrypted local secrets, dependency/release-signature verification and external review before any consideration of real funds.

These are future engineering tasks. No claim is made that this repository implements them or resolves the broader research problems in the cited literature.

## 8. Reproduction and references

Follow the [README](../README.md) to install the environment, execute tests, run the regtest/private-signet scenarios and regenerate the results summary. Its [repository structure](../README.md#repository-structure) shows where the engine, tests, and evidence live. The [implementation notes](IMPLEMENTATION.md#12-dependency-justification) explain the dependencies.
