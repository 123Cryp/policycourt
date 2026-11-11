# PolicyCourt security and correctness review (v1.5.0)

This document answers the second external patch request against PolicyCourt. Every item was checked against the code; confirmed issues were fixed with regression tests. Nothing was deployed as part of this work.

## A. Findings

| # | Severity | Function(s) | Scenario | Impact | Fix | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | High | `treasury_disburse` (removed) | The admin pays any non-steward address instantly under any purpose label | Treasury can be drained in one transaction with no chance to object | Payouts are now public proposals with a 1-hour delay, admin-cancellable, executable by anyone after the delay, one at a time, capped at 25% of the available treasury. Recipient checks repeat at execution. Admin handover is two-step. | High |
| 1b | Info | `propose_treasury_payout` | Admin pays a second wallet they control | Cannot be prevented on-chain | Documented as a trust assumption; delay, cap and public ledger make it visible and slow | High |
| 2 | High | `_validate_judgment` | Leader returns findings that differ from the validator's but give the same outcome and deciding lenses (e.g. text SUPPORTS vs INSUFFICIENT next to process AGAINST) | Stored lens findings and notes were not agreed by validators | Validators must match all three findings exactly. Leader results are validated strictly (types, normalized non-empty notes and reasoning, citations unique, sorted, in range, not bool) and only those fields are stored | High |
| 2b | Medium | `_judge` | Model cites an article that does not exist | Previously dropped silently, hiding a wrong answer | The model answer is now unusable; nothing is recorded and the ruling can be retried | High |
| 2c | Medium | `_build_prompt` | Instructions planted in the charter or carried into the round 1 ruling | Could steer the model | Charter and round 1 ruling now sit in marked JSON data blocks like the other party text | Medium (injection cannot be ruled out) |
| 3 | Medium | `add_evidence`, `get_appeal_actions` | A party adds evidence after the response deadline, right before someone rules | The other side has no chance to answer it | Evidence closes at the response deadline (inclusive), the same boundary as the steward's reply; the view matches | High |
| 4 | Low | `get_appeal_actions` | View offered `add_evidence` after the deadline | Button that would fail | Fixed with item 3; a randomized test now checks the view never offers an action the write rejects | High |
| 5 | Info | `get_accounting` | GEN reaches the contract without being owed to anyone | `balanced` would read false although no user funds are missing | Reports `surplus_wei`, `solvent` and `balanced` separately; surplus is never a liability | High |
| 6 | Medium | `propose_treasury_payout` | `COMPENSATION` with any case id | A label is not proof | Compensation requires a settled appeal that went against the steward, pays only its appellant, at most its stake, once | High |
| 7 | Low | `_page` | Unfiltered list with a large offset | Read every record before the page | Unfiltered lists index directly; filtered lists stop one match past the page; missing keys are skipped | High |
| — | Not a bug | `concede_appeal` after the response deadline | Steward concedes before a ruling | Intended: conceding only helps the appellant | Kept, tested | High |
| — | Not a bug | Appellant rules early after the steward replied | Appellant waives the rest of the reply window | Intended; the steward cannot rush a ruling | Kept, tested | High |
| — | Not a bug | Both leader and validator return `ok: false` | Consensus agrees on failure | `rule_appeal` raises; nothing is recorded (tested) | Kept | High |

## B. Economic and governance choices

- Forfeits go to the Appeals Treasury, never to the steward or the other party (decided by the project owner in v1.4.0; unchanged).
- A single treasury admin remains an explicit trust assumption. A multi-signer approval process was considered. GenLayer offers no built-in multisig primitive in this contract model, and a home-made one would add more risk than it removes at this scale. The admin's power is instead bounded by the delay, cap, single pending proposal, purpose rules, recipient rules and public ledger.
- Exact agreement on all three findings makes consensus stricter. When validators disagree, no ruling is recorded and the call can be retried; the 3-day timeout returns the stake if no ruling ever lands. Live runs on GenLayer Studio produced identical findings on all three lenses in repeated rulings of the same case, so the stricter rule is not expected to block normal cases.

## C. Tests

```
python3 -m unittest discover -s tests -v
```

Result: 132 tests, all passing.

| File | What it proves |
| --- | --- |
| `test_ruling.py` | Outcome rule for all findings; strict validator over every pair of the 27 finding combinations in both rounds (accepts exactly when findings match); malformed leaders rejected; only validated fields stored; party text, charter and round 1 ruling only inside marked data blocks |
| `test_boundaries_and_properties.py` | Every deadline one second before, at and after; terminal appeals cannot be reopened or settled twice; the actions view never offers an action the write rejects (randomized); 80 randomized sequences (about 2,500 successful actions, all operations) with the accounting invariant checked after every action, accepted or rejected |
| `test_treasury.py` | Proposal, delay, cancel, execute, replay, cap, single pending proposal, compensation eligibility, steward and admin exclusions, two-step handover, rejected calls leave state unchanged, exact ledger and totals, every settlement path balanced, unsolicited GEN reported as surplus |
| `test_settlement_rounds.py`, `test_appeal_filing.py`, `test_views_and_actions.py`, `test_charters_decisions.py`, `test_files_and_frontend.py` | Settlement amounts, filing and bounces, views, counters, frontend wiring |

The browser journey (Playwright against the real contract code with stubbed network calls) also passes at 320 to 1440 px.

## D. Accounting report

Invariant: `contract balance = owed_wei + held_wei + treasury_wei`, where `treasury_wei` includes GEN reserved for a pending payout.

| Path | Formula | Effect |
| --- | --- | --- |
| `file_appeal` (accepted) | held += value (all of it, including any amount above the minimum) | stake held |
| `appeal_again` (accepted) | held += value; stake = first stake + value | stake held |
| Rejected payable call (`_bounce`) | owed += value | sender can withdraw it |
| OVERTURNED, concession, REVERSED, remand unanswered, round 1 VOID | to_appellant = stake | held -= stake, owed += stake |
| UPHELD | to_appellant = stake × upheld_bps / 10000 (floor) | held -= stake, owed += share, treasury += stake − share |
| REMANDED then reaffirmed | to_appellant = stake × remand_bps / 10000 (floor) | same, with the remand share |
| Round 2 VOID | to_appellant = (stake − first) + share(first, round 1 result) | extra stake fully refunded; first stake settled by round 1 |
| Treasury proposal | reserved += amount | no balance change |
| Treasury cancel | reserved −= amount | no balance change |
| Treasury execute | treasury −= amount, reserved −= amount, owed += amount, paid_by_purpose += amount, one ledger entry | moves treasury to owed |
| `withdraw` | owed −= amount; balance −= amount (transfer deducted immediately) | GEN leaves |

Rounding always favours the appellant's floor share and puts the remainder in the treasury, so `to_appellant + to_treasury = stake` exactly. `_finalize` is reachable only from states that are not `final` or `void` and sets one of those states, so an appeal is settled at most once (tested by replay attempts and in randomized sequences). All counters stay non-negative in every tested sequence.

## E. State transitions

| From | Caller | Action | Time condition | To | Money |
| --- | --- | --- | --- | --- | --- |
| (decision in force) | subject | `file_appeal` | now ≤ filing deadline | filed | stake held |
| filed / round2_filed | steward | `respond_to_appeal` | now ≤ response deadline, once per round | same | none |
| filed / round2_filed | appellant or steward | `add_evidence` | now ≤ response deadline | same | none |
| filed / round2_filed | steward | `concede_appeal` | any time before a ruling | final (OVERTURNED) | stake to appellant |
| filed / round2_filed | anyone | `rule_appeal` | now > response deadline | see below | |
| filed / round2_filed | appellant | `rule_appeal` | steward replied this round | see below | |
| filed (round 1) | ruling | OVERTURNED | | final | stake to appellant |
| filed (round 1) | ruling | UPHELD | | ruled | held until settled |
| filed (round 1) | ruling | REMANDED | | remanded | held |
| round2_filed | ruling | UPHELD or OVERTURNED | | final | settled by outcome |
| remanded | steward | `review_remand` REVERSE | now ≤ review deadline | final (REVERSED) | stake to appellant |
| remanded | steward | `review_remand` REAFFIRM | now ≤ review deadline | remanded (reviewed) | held |
| ruled / remanded (reviewed or review deadline passed) | appellant | `appeal_again` | now ≤ appeal deadline; extra ≥ first stake | round2_filed | extra held |
| ruled / remanded (open) | appellant | `accept_ruling` | any | final | settled by round 1 result |
| ruled / remanded (open) | anyone | `finalize_appeal` | now > appeal deadline | final | settled by round 1 result |
| filed / round2_filed | anyone | `void_stalled_appeal` | now > response deadline + 3 days | void | round 1: full refund; round 2: extra refunded, first stake by round 1 result |
| final / void | anyone | any action | | rejected | none |

Boundaries: a party may act exactly at its own deadline; actions that depend on a deadline having passed require strictly later. A treasury payout may execute exactly at `executable_at`.

## F. Unresolved risks and assumptions

- Payable rollback: the GenLayer docs do not state whether GEN attached to a payable call that raises is returned. PolicyCourt never raises with value attached in its validation paths: `_bounce` credits the value and returns normally, which is correct under either behaviour and was confirmed on Studio (section G). An unexpected internal exception with value attached is not covered by the docs.
- Transfers: per the docs, `emit_transfer` deducts value immediately and does not return it if the recipient-side transaction fails. A failed delivery in `withdraw` would leave the user's GEN outside the contract. Recipients are user wallets, where this is not expected; deliveries succeeded on Studio (section G) but are not verified on mainnet.
- `run_nondet_unsafe`: per the SDK source, the validator receives `Return`, `VMError` or `UserError`, and validator errors count as disagreement. PolicyCourt's validator accepts only `Return` and never raises. The installed SDK version could not be inspected here (no network); behaviour was confirmed by live rulings on GenLayer Studio (section G).
- Prompt injection can be reduced but not ruled out, because every validator reads the same material.
- Notes and reasoning are written by the leader; validators agree on the findings, not on every sentence.
- One treasury admin; on-chain code cannot tell whether two wallets belong to one person.
- Filtered list views can still read many records when few match; write methods contain no unbounded loops.
- Studio simulates balances locally; mainnet behaviour of balances and transfers should be re-checked there.

## G. Confirmed on GenLayer Studio (contract 0x626EF71fEc12002Eee9F055862A6e1719B398b9D)

- Rejected payable call: an observer's 1 GEN appeal was refused, credited and withdrawn (`0xf1375c85…`, `0x68a156a0…`), and the transfer was delivered (`0x58d7ef6e…`).
- Withdrawals deliver GEN (`0xf36635d2…`), and a second withdrawal with nothing owed is refused (`0x42edb602…`).
- Strict consensus (all three findings must match) reached agreement in all three live rulings: REMANDED, OVERTURNED and UPHELD.
- The treasury delay held (early execution refused), the payout executed once, and three replays were refused.
- Final `get_accounting`: balance 3 GEN equals treasury 3 GEN; `balanced` and `treasury_flows_match` are true.

Sources consulted: GenLayer documentation on value transfers (docs.genlayer.com/developers/intelligent-contracts/features/value-transfers.md) and the SDK source of `genlayer.vm` (sdk.genlayer.com/main/_modules/genlayer/vm.html).
