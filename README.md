# PolicyCourt

Appeals for community and DAO governance decisions, built as a GenLayer Intelligent Contract with a no-build frontend.

A community registers a written charter once. A steward records decisions under it (a ban, a rejected proposal, a removed role). The member affected can stake GEN and appeal. Validators read the charter, the decision and both sides' evidence, and publish a verdict with its reasons. The stake is returned or split according to the outcome.

## Roles

| Role | Who | What they can do |
| --- | --- | --- |
| Steward | Whoever registers the charter | Record decisions, respond to appeals, add evidence, concede, review remanded decisions |
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

## How the judgment works

Validators run the model on a prompt that contains the charter, the decision, the grounds, the evidence and the steward's response. All case text is treated as untrusted data. The model must answer three independent lenses, each as `SUPPORTS_DECISION`, `AGAINST_DECISION` or `INSUFFICIENT`:

| Lens | Question |
| --- | --- |
| text | Was a charter article actually broken? |
| proportion | Is the sanction proportionate to what the charter provides? |
| process | Was the procedure the charter requires followed? |

The outcome is computed in code from the lenses, never taken from the model's own label:

| Round | Lenses against the decision | Outcome |
| --- | --- | --- |
| 1 | 2 or 3 | OVERTURNED |
| 1 | exactly 1 | REMANDED |
| 1 | 0 | UPHELD |
| 2 (final) | 2 or 3 | OVERTURNED |
| 2 (final) | 0 or 1 | UPHELD |

Validators re-run the judgment and must reach the same outcome, and the leader's stated outcome must follow from the leader's own lens findings; only the free-text notes and reasoning may differ. Cited article numbers outside the charter are dropped. A missing or malformed model answer records nothing and the ruling can be retried.

## Stake rules

| Result | Appellant receives | Steward receives |
| --- | --- | --- |
| OVERTURNED, concession, steward reversal | 100% | 0 |
| UPHELD | upheld refund share (charter setting, 0 to 50%) | the rest |
| REMANDED, steward reaffirms | remand refund share (charter setting, 50 to 100%) | the rest |
| REMANDED, steward silent | 100% | 0 |
| Voided in round 1 (no ruling within 3 days of the response deadline) | 100% | 0 |
| Voided in round 2 | extra stake 100%, first stake split by the round 1 result | the rest |

A remanded decision goes back to the steward, who must `review_remand` with `REVERSE` or `REAFFIRM` within the response window.

## Second appeal

After an UPHELD ruling, or a REMANDED ruling that the steward reaffirmed or ignored, the appellant can call `appeal_again` with extra stake of at least the first stake, so the total at least doubles. The steward gets a fresh response window. The prompt includes the first ruling as context. The second ruling is final and can only be OVERTURNED or UPHELD.

## Rules worth knowing

- Rejected payable calls refund the GEN to the sender's withdrawable balance and return the reason, instead of stranding it.
- GEN only leaves the contract through `withdraw` (pull payment, ledger zeroed before the transfer).
- One open appeal per decision. Appeals must be filed within the charter's appeal window after the decision is recorded.
- Each side can add at most 6 evidence items of 800 characters.

## Methods

Writes: `register_charter`, `record_decision`, `file_appeal`, `add_evidence`, `respond_to_appeal`, `concede_appeal`, `rule_appeal`, `review_remand`, `appeal_again`, `accept_ruling`, `finalize_appeal`, `void_stalled_appeal`, `withdraw`.

Views: `get_charter`, `list_charters`, `get_decision`, `list_decisions`, `get_appeal`, `list_appeals`, `get_verdict`, `get_appeal_actions`, `get_decision_actions`, `get_stats`, `get_profile`, `get_charter_stats`, `get_pending_withdrawal`, `get_rules`.

## Frontend

`index.html` is a single file with no build step (genlayer-js from esm.sh, Public Sans from Google Fonts).

- Cases, Charters, New charter and Account pages; case, charter and decision detail pages.
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
