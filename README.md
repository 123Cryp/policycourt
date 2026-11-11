# PolicyCourt

Appeals for community and DAO governance decisions, built as a GenLayer Intelligent Contract with a no-build frontend.

A community registers a written charter once. A steward records decisions under it (a ban, a rejected proposal, a removed role). The member affected can stake GEN and appeal. Validators read the charter, the decision and both sides' evidence, and publish a verdict with its reasons. The stake is returned or split according to the outcome.

## Roles

| Role | Who | What they can do |
| --- | --- | --- |
| Steward | Whoever registers the charter | Record decisions, respond to appeals, add evidence, concede, review remanded decisions. Never receives forfeited stake |
| Treasury admin | The deployer, or whoever accepts the role from them | Propose and cancel purpose-labelled payouts from the Appeals Treasury |
| Anyone | Any address | Execute a treasury payout once its public delay has passed |
| Appellant | The member a decision was made against | File an appeal with a stake, add evidence, accept a ruling, file a second appeal with a larger stake |
| Anyone | Any address | Ask the panel to rule, finalize a case after its window, void a stalled case |

`get_appeal_actions` and `get_decision_actions` return exactly which actions an address may take, and the frontend shows only those buttons.

## Flow

1. `register_charter`: name, 2 to 12 articles separated by `|`, minimum stake in whole GEN, response and appeal windows in seconds, refund shares. Charters cannot be edited afterwards.
2. `record_decision`: the steward anchors the decision on-chain (member, kind, summary, rationale, articles relied on) before any appeal exists.
3. `file_appeal`: the member stakes at least the charter minimum and states grounds and evidence.
4. `respond_to_appeal`, `add_evidence`, or `concede_appeal` (steward concedes, stake returns in full).
5. `rule_appeal`: anyone can call it after the response deadline. Once the steward has responded, the appellant may call it earlier (waiving further rebuttal); the steward cannot rush a ruling before the appellant has had the full window to reply.
6. Verdict: `UPHELD`, `OVERTURNED` or `REMANDED`, stored with reasoning, three lens findings and the cited articles.
7. Settlement and, for non-overturned round 1 rulings, a window for a second appeal.

## Deployment

| Item | Value |
| --- | --- |
| Network | GenLayer Studio |
| Contract | `0x626EF71fEc12002Eee9F055862A6e1719B398b9D` |
| Explorer | https://explorer-studio.genlayer.com/address/0x626EF71fEc12002Eee9F055862A6e1719B398b9D |
| Frontend | https://123cryp.github.io/policycourt/ |
| Version | v1.5.0 |

The frontend uses this contract by default. Open `index.html?contract=ADDRESS` to point it at another deployment.

## Live test results

All on GenLayer Studio, contract `0x626EF71fEc12002Eee9F055862A6e1719B398b9D` (v1.5.0), 11 Nov 2026, using three Studio accounts: steward `0xBD767E…da35F6` (also treasury admin), member `0xaCd800…c6dC9E` and observer `0x99E48b…c0A514`. Hashes are shortened; every transaction is listed on the [explorer page](https://explorer-studio.genlayer.com/address/0x626EF71fEc12002Eee9F055862A6e1719B398b9D).

| Scenario | What happened on-chain | Transactions |
| --- | --- | --- |
| Charter | "Open Garden DAO", 4 articles, 1 GEN minimum stake | `0x0ccceaee…3277c154` |
| Case 0, ban for spam, round 1 | Steward claimed DM warnings without evidence. Panel: text SUPPORTS, proportion SUPPORTS, process INSUFFICIENT, so **REMANDED** ("sent back to the steward for substantiation") | file `0xc70feb0c…93f7d0c9`, reply `0x19fd5654…49493487`, ruling `0x86257286…a263f730` |
| Case 0, review and second appeal | Steward reaffirmed without copies of any warning; member staked 2 GEN more and filed a log showing no warning | review `0xc936c3e9…afc22585`, appeal again `0x6f74652a…1c9d478a`, evidence `0x02bc947b…05a1c31f` |
| Case 0, round 2 | Panel: process AGAINST (Article 3 written warning missing), so **OVERTURNED**; all 4 GEN returned | ruling `0x5fbb69e2…e2de7e59` |
| Case 1, rejected proposal | Steward conceded; 1 GEN returned | file `0xfb8e6901…d7300de8`, concede `0x65662a4f…8083c130` |
| Case 2, suspension for harassment | Written warning on record. Panel: all three lenses SUPPORTS, so **UPHELD**; member accepted: 1 GEN back, 4 GEN to the Appeals Treasury | file `0x349b8238…b0101485`, ruling `0x015c8364…281eb82f`, accept `0x066de074…04ae4386` |
| Rejected payment | Observer appealed a decision that was not about them with 1 GEN: refused, credited, withdrawn | appeal `0xf1375c85…0cde247a`, withdraw `0x68a156a0…bc7f9945`, transfer `0x58d7ef6e…3512bc0b` |
| Withdrawals | Member withdrew 6 GEN; a second withdrawal was refused | `0xf6e9a3a6…61d24516`, transfer `0xf36635d2…5f7c2ef0`, refused `0x42edb602…a6515623` |
| Treasury payout | Admin proposed 1 GEN for appeal costs (the 25% cap); execution before the 1-hour delay was refused; executed after the delay; three replays refused; recipient withdrew | propose `0x9c37b087…d6a795e6`, early `0xa8c02a32…3110755b`, execute `0xf9ee64d0…9d8e8d9c`, replays `0x30c64c82…71c705ca` `0x4c232791…5528a6a8` `0xad9b7411…4d48e826`, withdraw `0x23305b7f…7fbe6fb3` |
| Final books | `get_accounting`: balance 3 GEN = treasury 3 GEN, nothing owed, no stakes held, `balanced` and `treasury_flows_match` true | read |

The same ban case was run on the earlier deployment `0x190008d6d8E892ff8bE7b363C28c074B34d78C6E` (v1.2.1). There, round 2 was recorded as UPHELD although the panel's own reasoning said the ban must be overturned; that live result led to the outcome-rule fix in v1.3.0, and the run above shows the corrected behaviour.

## How the judgment works

Validators run the model on a prompt that contains the charter, the decision, the grounds, the evidence and the steward's response. All case text is treated as untrusted data. The model must answer three independent lenses, each as `SUPPORTS_DECISION`, `AGAINST_DECISION` or `INSUFFICIENT`:

| Lens | Question |
| --- | --- |
| text | Was a charter article actually broken? |
| proportion | Is the sanction proportionate to what the charter provides? |
| process | Was the procedure the charter requires followed? |

The outcome is computed in code from the lenses, never taken from the model's own label. The prompt states the same rule so the written reasoning matches the recorded outcome.

| Finding | Round 1 | Round 2 (final) |
| --- | --- | --- |
| text or process is AGAINST | OVERTURNED | OVERTURNED |
| only proportion is AGAINST | REMANDED | OVERTURNED |
| text or process is INSUFFICIENT (nothing AGAINST) | REMANDED | UPHELD |
| every lens SUPPORTS (proportion may be INSUFFICIENT) | UPHELD | UPHELD |

A broken charter rule is required for any sanction, and a mandatory procedure that was not followed voids the decision, so either one alone is enough to overturn. In round 1 the steward carries the burden of showing that a rule was broken and the procedure followed: if the material leaves either unproven, or the sanction looks excessive, the case goes back to the steward to substantiate or reconsider. In the final round an excessive sanction overturns, while leftover uncertainty is resolved in favour of the decision.

Validators re-run the judgment and must reach exactly the same finding on all three lenses; the leader's stated outcome must follow from those findings. The leader's result is checked strictly (types, normalized non-empty notes and reasoning, citations that are unique, sorted, in range and not booleans) and only those validated fields are stored. Notes, reasoning and citations may be worded differently by each validator. All party-supplied text (decision summary and rationale, grounds, evidence, responses) reaches the model as one delimited JSON block that the prompt marks as untrusted data. Cited article numbers outside the charter are dropped. A missing or malformed model answer records nothing and the ruling can be retried.

## Stake rules

| Result | Appellant receives | Appeals Treasury receives |
| --- | --- | --- |
| OVERTURNED, concession, steward reversal | 100% | 0 |
| UPHELD | upheld refund share (charter setting, 0 to 50%) | the rest |
| REMANDED, steward reaffirms | remand refund share (charter setting, 50 to 100%) | the rest |
| REMANDED, steward silent | 100% | 0 |
| Voided in round 1 (no ruling within 3 days of the response deadline) | 100% | 0 |
| Voided in round 2 | extra stake 100%, first stake split by the round 1 result | the rest |

The steward never receives any part of a forfeited stake, and neither does the other party.

## Appeals Treasury

Forfeited stake goes to a neutral Appeals Treasury held by the contract. Money leaves it only through a public, delayed proposal:

1. The treasury admin calls `propose_treasury_payout(recipient, amount_wei, purpose, appeal_id, note)`. The amount is reserved.
2. The proposal is public for `TREASURY_DELAY_SECONDS` (1 hour). During that time the admin can `cancel_treasury_payout`.
3. After the delay, anyone can call `execute_treasury_payout`. The amount is credited to the recipient's withdrawable balance and written to the ledger.

| Purpose | Use | What the contract checks |
| --- | --- | --- |
| `APPEAL_COSTS` | Costs of running appeals, such as validator fees | Recipient rules and limits below |
| `COMPENSATION` | Compensation for a member wronged by a decision | Must reference a settled appeal that went against the steward (OVERTURNED, REVERSED or remand unanswered), be paid to that appeal's appellant, not exceed its stake, and happen at most once per appeal |
| `SUSTAINABILITY` | Keeping the dispute-resolution system running | Recipient rules and limits below |

Limits on every payout:

- One pending proposal at a time, and at most 25% (`TREASURY_MAX_PAYOUT_BPS`) of the available treasury per payout.
- The recipient cannot be the admin, any address that registered a charter (a steward), or the steward of the referenced appeal. These checks are repeated at execution time.
- Every payout needs a written reason. Each executed payout creates exactly one ledger entry; per-purpose totals always add up to the total paid out.
- The admin role changes hands in two steps (`propose_treasury_admin`, then `accept_treasury_admin` by the new admin). The deployer is the first admin.

What the contract cannot do: it cannot verify that a stated purpose is genuine, and it cannot tell whether two wallets belong to the same person. The public delay, the cap and the ledger make misuse visible and slow, not impossible. The single admin is an explicit trust assumption (see `SECURITY_REVIEW.md`).

Accounting invariant, exposed by `get_accounting` and checked after every action in the tests:

```
contract balance = GEN owed to users + stakes held in open appeals + Appeals Treasury
```

`get_accounting` also reports `surplus_wei` (GEN that reached the contract without being owed to anyone), `solvent`, and `treasury_flows_match` (received minus paid out equals the treasury, and per-purpose totals equal the total paid out).

## Second appeal

After an UPHELD ruling, or a REMANDED ruling that the steward reaffirmed or ignored, the appellant can call `appeal_again` with extra stake of at least the first stake, so the total at least doubles. The steward gets a fresh response window. The prompt includes the first ruling as context. The second ruling is final and can only be OVERTURNED or UPHELD.

## Known limitations

- Prompt injection cannot be ruled out completely: the delimited JSON block and the instruction to distrust party text reduce it, and every validator must reach the same deciding findings, but all validators read the same material.
- Lens notes and reasoning are written by the leader; validators check that they match the deciding findings, not that every sentence is accurate.
- Treasury payouts depend on one admin's judgment. The contract limits what the admin can do (public delay, cap, purposes, no stewards, no self-payment, objective compensation rules, public ledger), but it cannot judge whether a given payout was wise.

## Rules worth knowing

- Rejected payable calls refund the GEN to the sender's withdrawable balance and return the reason, instead of stranding it.
- GEN only leaves the contract through `withdraw` (pull payment, ledger zeroed before the transfer).
- One open appeal per decision. Appeals must be filed within the charter's appeal window after the decision is recorded.
- Each side can add at most 6 evidence items of 800 characters, until the response deadline of the current round (inclusive), the same boundary as the steward's reply.

## Methods

Writes: `register_charter`, `record_decision`, `file_appeal`, `add_evidence`, `respond_to_appeal`, `concede_appeal`, `rule_appeal`, `review_remand`, `appeal_again`, `accept_ruling`, `finalize_appeal`, `void_stalled_appeal`, `withdraw`, `propose_treasury_payout`, `cancel_treasury_payout`, `execute_treasury_payout`, `propose_treasury_admin`, `accept_treasury_admin`, `claim_treasury_admin`.

Views: `get_charter`, `list_charters`, `get_decision`, `list_decisions`, `get_appeal`, `list_appeals`, `get_verdict`, `get_appeal_actions`, `get_decision_actions`, `get_stats`, `get_profile`, `get_charter_stats`, `get_pending_withdrawal`, `get_rules`, `get_treasury`, `list_treasury_entries`, `list_treasury_proposals`, `get_accounting`.

`get_appeal_actions(appeal_id, address, as_of)` and `get_decision_actions(decision_id, address, as_of)` take the current UTC time as `as_of` (for example `2026-11-11T09:30:00Z`). Read-only calls are not transactions, so their result should not depend on the node's clock; no view reads the clock itself and the frontend passes the browser's time. Write methods always use the transaction timestamp.

## Frontend

`index.html` is a single file with no build step (genlayer-js from esm.sh, Public Sans from Google Fonts).

- Home: a short introduction, live totals with real 30-day activity counted from on-chain timestamps, entry points by role (member, steward, observer), and a case grid with status colour, the next deadline as a live countdown, search and a grid/list toggle.
- Cases, Charters, New charter and Account pages; case, charter and decision detail pages. The Account page lists decisions recorded about the connected address so a member can appeal in one step.
- Light, dark or automatic theme, chosen in the sidebar, the top bar or Account settings.
- Each case page shows only the actions the connected wallet may take (from `get_appeal_actions`), a progress tracker with live deadlines, the verdict seal, the three lens findings, cited articles, the case file from both sides and where the stake went.
- Every transaction is previewed in a confirmation dialog, then tracked through four stages: wallet approval, submitted, accepted by validators, finalized. Success is only shown after the transaction is finalized. Wallet rejection, wrong network, insufficient GEN, network errors and contract rejections each get their own message.
- Forms validate inline with the same limits the contract enforces, and buttons lock while a transaction is in flight to prevent duplicate submissions.
- Mobile-first layout with a bottom tab bar; sidebar and a sticky action column from 1024px. Checked at 320, 360, 390, 430, 768, 1024, 1280 and 1440px wide.
- Keyboard and screen reader support: skip link, native modal dialogs, labelled fields, live regions for toasts, visible focus, reduced-motion support, light and dark themes.

## Repository layout

| Path | Purpose |
| --- | --- |
| `contract.py` | The contract, ready to paste into GenLayer Studio (two header lines, then code) |
| `index.html` | Single-file frontend (genlayer-js from esm.sh) |
| `tests/` | Offline tests with a self-written SDK stub |
| `.github/workflows/tests.yml` | Runs the tests on every push |

## Run the tests

```
python3 -m unittest discover -s tests
```

## Deploy

1. In GenLayer Studio create a new contract file and paste the full content of `contract.py`.
2. Deploy with no constructor arguments.
3. Open `index.html?contract=<deployed address>` once. The address is remembered in the browser.

## Limits

The offline tests use a stub SDK and mocked model answers; real validator behaviour is only covered by live runs on GenLayer Studio. Verdicts are produced by a language model and can be wrong, which is why a second appeal with a larger stake exists. This is testnet software, not legal advice.

## Changelog

### v1.5.0

Second security review (patch request covering treasury governance, consensus, deadlines and accounting). Full findings, accounting report and state table: `SECURITY_REVIEW.md`.

- Treasury payouts are public proposals with a 1-hour delay, cancellable by the admin, executable by anyone afterwards, capped at 25% of the available treasury, one at a time. Compensation has objective eligibility. Admin handover is two-step.
- Validators must agree on all three lens findings; leader results are validated strictly and only validated fields are stored. Invalid citations from the model make the answer unusable instead of being silently dropped.
- The charter and the round 1 ruling are also passed inside marked data blocks.
- Evidence closes at the response deadline, with the same boundary as the steward's reply; the actions view matches.
- `get_accounting` reports surplus, solvency and treasury-flow consistency separately; unsolicited GEN is never counted as a liability.
- Unfiltered lists read only the requested page.
- New tests: every pair of lens combinations in both rounds, deadline boundaries one second before, at and after, a check that the actions view never offers a rejected action, and randomized action sequences with the accounting invariant checked after every step.

### v1.4.0

Security and correctness review (external review of v1.3.0, each finding checked against the code):

- Forfeited stake now goes to a neutral Appeals Treasury instead of the steward, removing the steward's financial interest in upholding decisions. Payouts are admin-approved, purpose-labelled, ledgered and covered by a public accounting invariant.

- Write methods no longer fall back to the node's wall clock; without a transaction timestamp they fail with nothing recorded.
- Validators must agree on why an appeal is decided, not only on the outcome, and reject malformed citations.
- Party-supplied text is passed to the model as a single delimited JSON block marked as untrusted data.
- In round 1, an unproven rule or procedure (INSUFFICIENT on text or process) sends the case back to the steward instead of upholding it. Live testing showed exactly this case: the panel upheld while asking the steward to produce the missing warning.
- Charters keep decision counters per status instead of an ever-growing list of decision ids.
- List views stop after one look-ahead match instead of scanning the rest of the collection.
- A remand the steward reaffirmed is recorded as `reaffirmed` rather than `upheld`.

### v1.3.0

- Live testing on Studio showed a final-round ruling recorded as UPHELD although the panel found the mandatory written-warning procedure was not followed and its reasoning said the ban must be overturned (the old rule needed two lenses against). Now a text or process finding against the decision overturns on its own, proportion alone remands in round 1 and overturns in round 2, and the prompt states this rule.
- Lens notes (600 characters) and reasoning (1,500) are clipped on a word boundary instead of mid-word.

### v1.2.1

- `get_appeal_actions` and `get_decision_actions` take an `as_of` time instead of reading the node clock, so read-only results are deterministic and testable.
- Tabular numerals are limited to amounts, addresses and countdowns instead of the whole page.

### v1.2.0

- `list_appeals` rows now include `decision_kind`, `decision_summary`, `next_deadline` and `next_deadline_kind`, so case cards show the decision and a live countdown without extra reads.
- Home redesign: hero with live totals and 30-day activity, role entry points, case grid with countdowns, search and grid/list layouts.
- Account: decisions recorded about you, with a direct path to appeal.
- Theme switcher (automatic, light, dark) and a stronger single accent colour.

### v1.1.0

- Redesigned frontend: case-first layout, role-aware actions, transaction stages, confirmation previews, inline validation, accessibility and responsive layouts.

### v1.0.1

- Validators now reject a leader whose stated outcome does not follow from its own lens findings.
- Cited article numbers are range-checked (booleans and out-of-range numbers dropped).
- Only the appellant can request a ruling before the response deadline, so a steward cannot respond and rule at once.
- A stalled second appeal no longer erases the first-round ruling: the extra stake is refunded and the first stake is settled by the round 1 result.
- Boolean refund settings are rejected.

### v1.0.0

First release.

## License

MIT
