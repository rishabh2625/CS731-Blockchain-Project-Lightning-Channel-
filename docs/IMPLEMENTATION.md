# Implementation and design rationale

This document describes the code that exists in this repository. It distinguishes implemented behavior from the broader BOLT protocol. The source walkthrough explains individual functions; this file explains why they are connected this way.

## 1. System boundaries and threat model

Alice and Bob are separate Python processes with separate databases and independently generated keys. The controller transports requests over local process pipes. Core nodes communicate only over loopback in the automatic harness. Peers verify received signatures and revocation secrets; Core validates consensus and mempool policy independently.

The controller is trusted as the local user-command source. We do not model a hostile operating system, compromised controller, arbitrary internet clients or theft of peer databases. A malicious remote channel participant can be simulated by publishing a previously revoked commitment. Invalid remote cryptographic material is rejected. This is not a general proof against every adversarial asynchronous message schedule.

`ChannelLab` checks that the connected chain is regtest or signet. The automatic `Network` class only constructs those test chains, in fresh directories, and never opens the user's ordinary Bitcoin wallet directory.

## 2. Public channel configuration

The fixed configuration includes capacity, funding outpoint, funder, initial allocations, both public key bundles, the CSV delay, dust limit and feerate in satoshis per 1,000 weight units. It becomes immutable once configured.

Each peer has separate funding, payment, delayed-payment, HTLC and revocation base secrets, plus an independent per-commitment seed. Distinct keys make their roles visible and avoid accidentally using a funding key for a delayed or revocation spend. Public configuration never contains these secrets.

The demo uses Alice as the single funder and an initial allocation to Bob. This is an agreed opening allocation, not dual funding. The raw funding transaction is finalized by the Core wallet before its txid is used in commitments; SegWit funding inputs avoid witness changes altering that txid. Funding is broadcast only after both initial exits are stored.

Both parties use the same fixed delay/dust/rate in this profile. A full implementation would negotiate and maintain per-peer values. Whole-satoshi amounts avoid a hidden msat rounding layer in the state machine; the transaction model nevertheless handles dust trimming explicitly.

## 3. Encoding and signatures

`bitcoin.py` constructs transaction bytes directly. Integer transaction fields use little-endian encoding. Human-readable txids are reversed for wire outpoints. CompactSize prefixes lengths. The txid is the double-SHA256 of stripped serialization, reversed for display. Weight is `3 * stripped_length + total_length`; virtual size is `(weight + 3) // 4`.

Only SegWit v0 `SIGHASH_ALL` is implemented. The BIP 143 digest commits to prevouts, sequences, the current outpoint, serialized scriptCode, spent amount, sequence, all outputs, locktime and the four-byte sighash type. The DER signature is produced with `hasher=None` because the digest has already been calculated. The one-byte `01` sighash flag is appended when constructing the witness.

Signature verification uses the same independently built transaction on the receiving peer, rather than trusting a received transaction hex blob. Coincurve supplies optimized curve operations and low-S signing. We implement key combinations and Bitcoin preimages ourselves.

For P2WPKH spends the BIP 143 scriptCode is the corresponding P2PKH script. For P2WSH it is the witness script. Confusing the witness program with scriptCode would produce invalid signatures; real Core acceptance and the complete published vector test cover this distinction.

The serializer handles the channel's transaction formats. Core decodes the signed funding transaction and provides its outpoint, while our structured transaction objects handle channel transactions. General raw-transaction parsing, legacy script interpretation, and alternate sighash modes are outside the serializer's scope.

## 4. Keys, revocation and secret storage

`crypto.py` implements:

```text
derived_pub = basepoint + SHA256(per_commitment_point || basepoint) * G
derived_priv = base_secret + SHA256(per_commitment_point || basepoint) mod n

revocation_pub = revocation_basepoint * SHA256(basepoint || point)
               + point * SHA256(point || basepoint)
```

The revocation private scalar combines the corresponding two secrets with those two hashes, modulo the secp256k1 group order. It is available to the counterparty only after the old per-commitment secret is disclosed. The payment key for `to_remote` is static under the selected profile.

`shachain.py` maps commitment number `n` to descending index `(2**48 - 1) - n`. Generation flips selected bits of a 32-byte value and hashes, processing bits from 47 downward. The receiver's bucket is selected by the index's trailing-zero count. A new secret must derive the already-known lower-bucket secrets correctly before insertion. Storage uses at most 49 bucket entries; the peer separately retains old transaction states for convenient breach matching.

The first individual shachain entry cannot by itself establish consistency with an undisclosed seed. The peer additionally checks every revealed secret against the previously committed public point. Published storage vectors include cases where inconsistency becomes detectable only when a parent arrives.

## 5. Funding and commitment construction

Funding uses a P2WSH script with two compressed funding keys sorted lexicographically. Commitment input witnesses preserve that same signature order and include the CHECKMULTISIG dummy item.

The commitment number is obscured with the lower six bytes of SHA256 of the funder's payment basepoint followed by the other payment basepoint. The high and low 24-bit parts are placed into sequence and locktime with the specified marker bits. This is encoded even though a small teaching demo could ignore it, because the signed transaction should match the profile's actual format.

`build()` constructs a different transaction for each owner. Its `to_local` script selects either an immediate revocation spend or a CSV-delayed owner spend. Its `to_remote` output pays the other peer's static payment key. Output records retain semantic metadata alongside their serialized scripts so later resolution code can select the correct branch without parsing scripts back into an internal model.

Untrimmed outputs are sorted by amount, script and, for otherwise identical HTLCs, expiry. The number of untrimmed HTLCs determines the commitment's base fee:

```text
base_fee_sat = floor((724 + 172 * untrimmed_htlcs) * feerate_per_kw / 1000)
```

The fee is deducted from the funder. A non-anchor offered HTLC uses weight 663 for its timeout fee; a received HTLC uses 703 for success. If an HTLC amount cannot cover that fee plus dust, its output is trimmed. Main outputs below dust after fee deduction are also trimmed. The actual transaction fee includes all value that does not appear in outputs, not just the base estimate.

These weights and formats come from the pinned BOLT 3. `test_transactions.py` verifies a complete signed commitment against a published independent fixture; integration checks enforce valid spending paths rather than only comparing our functions with one another.

## 6. State transitions and exchange protocol

The supported public payment actions are `add`, `fulfill` and `fail`. The state contains commitment number, balances, active HTLC list, next HTLC identifier and both commitment points. Identifiers are monotonic. One active HTLC is permitted. Expiries must be block heights and be at least two blocks beyond the action's supplied observed height. The local controller supplies that height; the peer does not independently poll Core for every user action.

The transition function copies the previous state, applies a validated operation, checks conservation and constructs both commitments to ensure the funder can afford them. Preparation does not overwrite the current secured state.

The controller's normal update sequence is:

1. Collect each peer's next public commitment point.
2. Ask both to prepare the same deterministic next state.
3. Ask each peer to sign the other's commitment and all applicable second-stage HTLC transactions.
4. Deliver those signatures. Each recipient verifies the exact expected signature set and commits it to SQLite.
5. Ask each peer to reveal its old secret. A peer refuses until step 4 is durably complete.
6. Deliver and validate revocation secrets; persist the shachain and acknowledgement flags.
7. Finalize each peer, archiving the old record and promoting the prepared record.

This is a deliberately serialized, two-sided protocol with BOLT-derived transactions and security ordering. It is not a complete BOLT 2 asynchronous state machine. In particular, it does not implement crossed updates, full retransmission wire semantics, channel_reestablish data-loss protection or negotiation. Calling it fully Lightning-compatible would be inaccurate.

Before finalization, `commitment()` refuses to publish while an update is pending. This avoids accidentally broadcasting a state already revoked during an interrupted exchange, but sacrifices availability until the transition can be reconciled. A production implementation should choose an enforceable latest exit from explicit per-direction state and recover without needing the controller's cooperation.

## 7. Persistence and replay

`Store` uses one JSON snapshot row and a separate event table. Every save wraps both in one SQLite transaction. WAL and FULL synchronous mode provide clear durable boundaries before responses containing signatures or secrets are returned. There is no claim that this resists a dishonest disk or backups restored to stale versions.

The snapshot contains private keys and seeds in plaintext under `.runtime`. These are test-only databases and are excluded from Git. Public evidence contains transaction hex and public channel states; it does not export private-key snapshots. The simple event log records event kind, state number and database timestamp, not full secret-bearing protocol messages.

`complete_pending()` can repeat the signing/revocation phase when both peers have the same pending state. It also completes a remaining finalization when the other peer already finalized the same state. A one-sided preparation with incompatible journals fails closed and needs manual recovery. The code does not promise uninterrupted operation through arbitrary crashes.

The peer dispatcher restores its in-memory snapshot if a command raises, so an unsuccessful command does not leave accidental partial memory changes. Core publication and database writes are not a distributed atomic transaction; the saved evidence and chain scan are the recovery tools for this laboratory.

## 8. HTLC spending matrix

An HTLC output is offered or received relative to the commitment owner, not permanently relative to Alice.

| Output relative to owner | Owner's path | Counterparty's path |
| --- | --- | --- |
| Offered HTLC | Presigned timeout transaction with absolute expiry, then delayed sweep | Direct preimage spend |
| Received HTLC | Presigned success transaction with correct preimage, then delayed sweep | Direct timeout spend |
| Either, revoked | Owner's paths remain transaction-valid | Revocation spend directly, or from a known second-stage output |

Both second-stage paths output to the same delayed/revocable script for that commitment. The counterparty's signature for the second stage is collected with the commitment signatures, so exiting does not require the peer to be online later.

The payment preimage and per-commitment revocation secret are different secrets with different purposes. `fulfill` checks a 32-byte preimage against the HTLC's hash. Revocation checks the disclosed scalar's public point against the old commitment point. Mixing them up would break the security argument.

The resolution API validates ownership and output kind before choosing a witness. It supports immediate main output, delayed main output, justice, HTLC resolution, second-stage delayed and second-stage justice modes. A generic payment-key `fee_child` supports the fee-policy experiment. Every transaction path is subsequently checked by Core.

## 9. Chain monitoring, deadlines and confirmations

The monitor scans blocks from a known starting height, looking for a matching funding outpoint. It does not assume the funding spend appeared in a public mempool. It compares the discovered txid with commitments constructed from retained public history.

For a revoked remote commitment it sweeps unspent revocable outputs. If a revoked HTLC was already spent, it computes the known second-stage txid and checks that output instead. It raises on a rejected penalty rather than reporting a successful rescue. It marks the local peer closed on any discovered funding spend.

The monitor is invoked by the scenario runner rather than running as a permanent service. It has no persistent scan cursor or full reorg recovery. One confirmation is sufficient for a controlled demonstration assertion, not an assertion of irreversible real-world finality. All saved evidence reports the actual confirmation count.

CSV maturity is a relative output-age condition. HTLC expiry is an absolute locktime condition. The tests use Core's acceptance decisions at the boundary rather than a parallel Python approximation of consensus. The six-block demo delay is chosen to keep isolated demonstrations short and is not a production policy recommendation.

## 10. Network infrastructure

`Network` creates two Core processes with fresh data directories, loopback-only listening, no DNS seeds, no discovery and explicit local connectivity. It waits for RPC readiness, funds a test wallet with mature coinbase outputs, and checks the nodes reach the same tip after mining. Processes are hidden on Windows and stopped in cleanup blocks.

Regtest uses `generatetoaddress`. Private signet uses an `OP_TRUE` challenge and a small block builder: construct the coinbase and witness commitment, append the BIP 325 signet solution, calculate the transaction Merkle root, solve the header with the matching `bitcoin-util grind`, and submit the block to Core. The first private block is constructed without requiring a pre-existing mined signet tip; subsequent blocks use Core's template and selected transactions.

The private signet choice exercises signet validation while keeping the demonstration self-contained. It does not evaluate signing-authority availability or external public-signet peers. Both networks use real UTXOs and validation; neither is an internal balance-only simulation.

## 11. Experiments and interpretation

The deadline experiment intentionally allows the revoked broadcaster to wait out the delay and confirm a withdrawal. The late justice transaction then references a spent input. This illustrates why revocation does not provide protection without timely action.

The replacement experiment uses a real offered HTLC. After expiry, the fixed timeout can replace a lower-fee conflicting preimage spend under the pinned policy. Attaching a descendant with additional fee changes the replacement requirement and Core rejects that timeout. This demonstrates fee obstruction, not a claim of durable theft or a sophisticated mempool partition attack. The output includes Core's exact rejection details.

The benchmark times complete add+fulfill payment pairs across local peer processes, including verification and SQLite persistence. It records individual samples, per-run medians and nearest-rank p95. It does not measure routing, WAN delays or block settlement. Concurrent local workload and OneDrive-backed storage can affect the observed values.

## 12. Dependency justification

Coincurve delegates secp256k1 point operations, signing and signature verification to libsecp256k1. It does not construct a channel or derive its revocation mechanism. Bitcoin Core supplies the reference consensus/mempool implementation, test wallet and node infrastructure. Its wallet constructs the funding transaction around the funding script that we specified; all channel transactions are constructed by this repository. SQLite, subprocess, hashing, JSON and urllib come from Python's standard library. Pytest is a test runner. No LND or Core Lightning library implements the channel for us.

The dependency versions, Core archive checksum and exact BOLT commit are retained. The original cryptographic formulas and script templates are attributed to BOLT; implementing a known mechanism is the project objective, not a claim of inventing those formulas.
