# Lightning Payment Channel Engine

A runnable Python implementation of one Bitcoin penalty channel: funding, commitment updates, per-commitment secrets, HTLCs, unilateral settlement and revoked-state penalties. It includes two independent peer processes, two Bitcoin Core nodes, reproducible scenarios and a documented security evaluation.

The programs produce real signed Bitcoin transactions. Bitcoin Core checks and confirms them on isolated regtest and a **private OP_TRUE signet**. The private signet is not the public default signet. This is an educational mechanism implementation with a deliberately restricted protocol profile, not a production Lightning wallet or a wire-compatible LND/CLN peer.

## Start here

1. [Full project report](docs/PROJECT_REPORT.md): problem, existing approaches, our solution, evaluation and future work.
2. [Implementation and design decisions](docs/IMPLEMENTATION.md): transaction construction, update protocol, persistence, validation and every deliberate scope restriction.
3. [Validation results](evidence/RESULTS.md): generated from actual saved runs.
4. [Run the demos](#run-the-demos): run individual cases or the full suite and inspect the transactions.
5. [Fee-inflation and pinning analysis](docs/ATTACK_SURFACE.md): threat model, quantitative fee sensitivity, observed obstruction and mitigation limits.

## Repository structure

```text
lightning-payment-channel/
├── lnchannel/             Python channel engine and local Bitcoin Core test harness
├── tests/                 Unit tests, published vector fixtures, and opt-in Core integration tests
├── tools/                 Core installer, test runner, results summarizer, and fee analysis
├── references/            Bitcoin Core download provenance and the pinned BOLT revision
├── evidence/              Saved validation results, raw benchmark data, and fee analysis
│   ├── regtest/           Scenario records from the local regtest chain
│   └── private-signet/    Scenario records from the two-node private signet
├── docs/                  Project report, implementation details, and security analysis
├── run.ps1                Windows entry point for demos and benchmarks
├── pyproject.toml         Python package metadata, dependencies, and test configuration
├── requirements-lock.txt  Pinned dependencies for reproducing the tested environment
└── LICENSE                License for the project code
```

Inside `lnchannel/`, `peer.py` and `state.py` handle channel updates, `commitment.py` and `scripts.py` build the closing transactions and spending rules, and `watchtower.py` handles on-chain breach recovery. `cli.py` starts the requested demo or benchmark, and `lab.py` coordinates the demo with the Python peers and Bitcoin Core.

The [test fixture](tests/fixtures/bolt3_vectors.json) contains selected published BOLT #3 vectors with their source revision and license attribution. The [revision record](references/spec-revision.json) identifies the specification version used.

Local setup creates `.venv/` (or `.venv312/` in the prepared workspace) for Python dependencies and `.tools/` for downloaded Core binaries. Running a scenario creates `.runtime/` for the temporary blockchains, wallets, logs, and peer databases. Git ignores these generated folders.

## Fresh installation

The prepared Windows workspace already has Python and Bitcoin Core. For a fresh checkout, run these commands from the repository root in PowerShell.

Use **Python 3.12** (3.11-3.13 supported by project metadata) and Bitcoin Core **28.1** for the reproduced policy results. The pinned dependency wheel was tested with Python 3.12 on Windows. Python 3.14 is intentionally excluded.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe tools/fetch_core.py
```

`fetch_core.py` downloads the official Windows archive and verifies its published SHA256. Independent release-signature verification is not automated; see `references/core-download.json` for the exact checksum and provenance.

On Linux/macOS create a virtual environment normally and set `BITCOIND` to an installed Bitcoin Core 28.1 executable. For private signet, the matching `bitcoin-util` must be beside it. Then use `python -m lnchannel ...`. The portable Python code is supplied; the recorded validation environment is Windows, not an assertion of cross-platform test coverage.

## Run the demos

Open PowerShell in the repository root. The Windows runner selects `.venv312` or `.venv`. From an activated environment on Linux or macOS, use `python -m lnchannel` in place of `.\run.ps1`.

### Short demonstration

```powershell
.\run.ps1 demo --chain regtest --case honest_alice --case breach_alice --output .runtime/class-demo
```

The honest case uses the latest commitment. Core rejects an early withdrawal and accepts it after the delay. The breach case publishes a revoked commitment. The other peer detects it and submits a penalty. Each case prints `PASS` after the expected behavior is verified and its JSON record is saved.

To show the node tips and confirmed transactions in the new breach run, use these commands:

```powershell
$run = Get-Content -LiteralPath .runtime/class-demo/breach_alice.json -Raw | ConvertFrom-Json
$run.nodes | Format-Table name, height, tip
$run.transactions | Format-Table label, confirmations, txid
```

Look for `funding`, `revoked_commitment`, and `justice` in the transaction table. The [saved private-signet breach run](evidence/private-signet/breach_alice.json) used in the presentation has those transactions in blocks 134, 135, and 136. New runs generate their own transaction IDs.

### Run all 12 cases

```powershell
.\run.ps1 demo --chain regtest --output .runtime/demo-regtest
.\run.ps1 demo --chain signet --output .runtime/demo-private-signet
```

Each command starts two local Bitcoin Core nodes and saves one JSON file per case plus `summary.json`. The `signet` option runs a private `OP_TRUE` signet and takes longer to start because it mines its own test blocks. Fresh results go into `.runtime`, and the [original regtest](evidence/regtest/summary.json) and [private-signet](evidence/private-signet/summary.json) records are in `evidence/`.

### Run one case at a time

Set `$demoChain` to `regtest` or `signet`, then run the line for the case you want. Each case has its own output folder.

```powershell
$demoChain = 'regtest'
.\run.ps1 demo --chain $demoChain --case honest_alice --output ".runtime/demo-$demoChain/honest_alice"
.\run.ps1 demo --chain $demoChain --case honest_bob --output ".runtime/demo-$demoChain/honest_bob"
.\run.ps1 demo --chain $demoChain --case breach_alice --output ".runtime/demo-$demoChain/breach_alice"
.\run.ps1 demo --chain $demoChain --case breach_bob --output ".runtime/demo-$demoChain/breach_bob"
.\run.ps1 demo --chain $demoChain --case htlc_success --output ".runtime/demo-$demoChain/htlc_success"
.\run.ps1 demo --chain $demoChain --case htlc_timeout --output ".runtime/demo-$demoChain/htlc_timeout"
.\run.ps1 demo --chain $demoChain --case htlc_direct_success --output ".runtime/demo-$demoChain/htlc_direct_success"
.\run.ps1 demo --chain $demoChain --case htlc_direct_timeout --output ".runtime/demo-$demoChain/htlc_direct_timeout"
.\run.ps1 demo --chain $demoChain --case htlc_breach --output ".runtime/demo-$demoChain/htlc_breach"
.\run.ps1 demo --chain $demoChain --case second_stage_breach --output ".runtime/demo-$demoChain/second_stage_breach"
.\run.ps1 demo --chain $demoChain --case missed_window --output ".runtime/demo-$demoChain/missed_window"
.\run.ps1 demo --chain $demoChain --case fee_obstruction --output ".runtime/demo-$demoChain/fee_obstruction"
```

Use `--case` more than once to run several cases in one session, as in the short demonstration.

| Case | What it demonstrates |
| --- | --- |
| honest_alice / honest_bob | Successful and failed payments; latest-state close; CSV enforcement; both main outputs recovered |
| breach_alice / breach_bob | Either peer publishes a revoked commitment and the honest peer enforces a penalty |
| htlc_success / htlc_timeout | Owner's second-stage resolution followed by a delayed sweep |
| htlc_direct_success / htlc_direct_timeout | Counterparty's direct preimage/timeout resolution |
| htlc_breach | Direct penalty spending of a revoked HTLC and main delayed output |
| second_stage_breach | Penalty after the cheater has moved the HTLC to its second stage |
| missed_window | Confirmed late withdrawal makes the old output unavailable to a late penalty |
| fee_obstruction | A descendant changes acceptance of a fixed-fee conflicting HTLC timeout |

## Reproduce the 50-payment benchmark

The original [benchmark JSON](evidence/benchmark.json) contains **three runs of 50 payments**, including all 150 timing samples and each run’s median and p95. Each payment includes the HTLC add and fulfill, for **100 durable updates per run**. The [results summary](evidence/RESULTS.md#off-chain-local-latency) shows the reported numbers.

```powershell
.\run.ps1 benchmark --payments 50 --runs 3 --output .runtime/class-benchmark.json
```

## Other reproducibility commands

Run these from the repository root with the project's Python environment active.

```powershell
python tools/test.py
python tools/summarize.py
python tools/analyze_fees.py
```

The test runner writes `evidence/unit-tests.xml`. The summarizer reads the saved evidence and writes `evidence/RESULTS.md`. The fee analysis reads the recorded scenarios and regenerates `evidence/fee-analysis.json` and `evidence/FEE_ANALYSIS.md`.

## What we implement ourselves

Channel-specific key derivation, shachain generation/storage, Bitcoin serialization and BIP 143 signing digest, funding/commitment/HTLC scripts, commitment layout and fees, signature exchange and revocation ordering, SQLite persistence, chain monitoring, resolution transactions and scenario orchestration. Coincurve supplies elliptic-curve primitives. Core supplies consensus validation, a wallet for test funding and the chain.

## Scope and limitations

One channel, two peers, one outstanding HTLC, integer satoshis, static remote payment keys, non-anchor commitments, fixed commitment feerate and serialized updates. Local JSON over process pipes replaces Lightning wire transport. There is no gossip, routing, BOLT 8 encryption, full channel negotiation, cooperative close, comprehensive reorg recovery or external-client interoperability. The local controller is trusted to issue user commands; it does not hold peer private keys. Some interrupted stages fail closed rather than automatically recovering. Read the detailed threat model before describing the software as secure.

The repository contains **public test transaction evidence**, not private peer databases. `.runtime`, `.tools` and virtual environments are excluded from Git. All automatic node operations use newly created test directories. No mainnet funds or public-network attack traffic are used.
