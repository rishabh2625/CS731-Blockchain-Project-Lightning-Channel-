# Fee sensitivity and replacement observations

Unsigned public commitment reconstruction at hypothetical negotiated rates; Core observations reused from saved runs.

| sat/kw | Approx. target sat/vB | State | Retained HTLCs | Base fee sat | Actual commitment fee sat | Offered / received threshold sat |
| ---: | ---: | --- | ---: | ---: | ---: | --- |
| 1000 | 4 | no HTLC | 0 | 724 | 724 | 1209 / 1249 |
| 1000 | 4 | 50,000-sat HTLC | 1 | 896 | 896 | 1209 / 1249 |
| 5000 | 20 | no HTLC | 0 | 3620 | 3620 | 3861 / 4061 |
| 5000 | 20 | 50,000-sat HTLC | 1 | 4480 | 4480 | 3861 / 4061 |
| 10000 | 40 | no HTLC | 0 | 7240 | 7240 | 7176 / 7576 |
| 10000 | 40 | 50,000-sat HTLC | 1 | 8960 | 8960 | 7176 / 7576 |
| 25000 | 100 | no HTLC | 0 | 18100 | 18100 | 17121 / 18121 |
| 25000 | 100 | 50,000-sat HTLC | 1 | 22400 | 22400 | 17121 / 18121 |
| 100000 | 400 | no HTLC | 0 | 72400 | 72400 | 66846 / 70846 |
| 100000 | 400 | 50,000-sat HTLC | 0 | 72400 | 122400 | 66846 / 70846 |

These are separate hypothetical negotiated configurations. They do not show unilateral repricing of an already signed commitment. The target conversion is rate/250; measured signed vsize can differ from the BOLT fee-weight estimate.

| Network | Conflicting spend fee | Descendant fee | Fixed timeout fee | Timeout vbytes | Before / after accepted | Rejection |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| regtest | 500 | 10000 | 3315 | 165 | True / False | insufficient fee |
| private-signet | 500 | 10000 | 3315 | 165 | True / False | insufficient fee |

The descendant increases total fees evicted by the replacement from 500 to 10,500 sat. The 3,315-sat timeout cannot cover that total, even before incremental replacement requirements. This is a controlled obstruction; it does not establish durable theft or confirmation delay under a competing external fee market.
