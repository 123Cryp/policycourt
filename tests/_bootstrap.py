import datetime as _dt
import importlib.util
import json as _json
import os
import sys
from unittest.mock import patch as _patch

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_STUB_DIR = os.path.join(_THIS_DIR, "genlayer_stub")
if _STUB_DIR not in sys.path:
    sys.path.insert(0, _STUB_DIR)

CONTRACT_PATH = os.environ.get("PC_CONTRACT") or os.path.join(os.path.dirname(_THIS_DIR), "contract.py")
_spec = importlib.util.spec_from_file_location("policycourt_contract", CONTRACT_PATH)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

PolicyCourt = m.PolicyCourt
gl = m.gl
Address = m.Address
u256 = m.u256
GEN = 10 ** 18

UTC = _dt.timezone.utc
BASE = _dt.datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
HOUR = 3600
DAY = 86400


class Clock:
    def __init__(self):
        self.now = BASE

    def reset(self):
        self.now = BASE

    def advance(self, seconds):
        self.now = self.now + _dt.timedelta(seconds=seconds)


CLOCK = Clock()
PolicyCourt._now_utc = staticmethod(lambda: CLOCK.now)

STEWARD = "0x" + "aa" * 20
MEMBER = "0x" + "bb" * 20
MEMBER2 = "0x" + "cc" * 20
STRANGER = "0x" + "dd" * 20

ARTICLES = (
    "Members must treat each other with respect and may not harass others.|"
    "Spam and unsolicited advertising are not allowed in any channel.|"
    "A ban requires a written warning first, except for threats of violence.|"
    "Proposals must include a budget and a named owner to be accepted."
)
RESP_WINDOW = 2 * HOUR
APPEAL_WINDOW = 4 * HOUR


def make_contract():
    CLOCK.reset()
    gl.evm.transfers.clear()
    return PolicyCourt()


def set_caller(address):
    gl.message.sender_address = Address(address)


class PaymentRejected(gl.vm.UserError):
    pass


def call_payable(contract, name, value, *args, **kwargs):
    gl.message.value = u256(value)
    contract.balance = contract.balance + u256(value)
    sender = str(gl.message.sender_address).lower()
    before = int(contract.pending_withdrawals[sender]) if sender in contract.pending_withdrawals else 0
    snapshot = (dict(contract.appeals), dict(contract.decisions), dict(contract.profiles), int(contract.appeal_count))
    try:
        result = getattr(contract, name)(*args, **kwargs)
    except Exception:
        contract.balance = contract.balance - u256(value)
        raise
    finally:
        gl.message.value = u256(0)
    if isinstance(result, str) and result.startswith('{"refunded_wei"'):
        data = _json.loads(result)
        after = int(contract.pending_withdrawals[sender]) if sender in contract.pending_withdrawals else 0
        assert data["refunded_wei"] == str(int(value)), data
        assert after - before == int(value)
        assert snapshot == (dict(contract.appeals), dict(contract.decisions), dict(contract.profiles), int(contract.appeal_count)), \
            "a rejected payable call changed state"
        raise PaymentRejected(data["rejected"])
    return result


def jl(text):
    return _json.loads(text)


def register(c, steward=STEWARD, **over):
    set_caller(steward)
    args = dict(name="Open Garden DAO", articles_text=ARTICLES, min_stake_gen=5, response_window_secs=RESP_WINDOW,
                appeal_window_secs=APPEAL_WINDOW, upheld_refund_bps=2000, remand_refund_bps=7000)
    args.update(over)
    return jl(c.register_charter(**args))["charter_id"]


def decide(c, cid, subject=MEMBER, kind="BAN", cited="2", summary="Banned for repeated spam in the general channel",
           rationale="Posted the same advertisement in four channels after one request to stop", steward=STEWARD):
    set_caller(steward)
    return jl(c.record_decision(cid, subject, kind, summary, rationale, cited))["decision_id"]


GROUNDS = "The posts were one announcement relevant to the channel and Article 3 requires a written warning, which I never received."


def appeal(c, did, stake=5, who=MEMBER, grounds=GROUNDS, evidence="Screenshot of channel rules showing announcements allowed"):
    set_caller(who)
    return jl(call_payable(c, "file_appeal", stake * GEN, did, grounds, evidence))["appeal_id"]


def full_case(c, **over):
    cid = register(c, **over)
    did = decide(c, cid)
    aid = appeal(c, did)
    return cid, did, aid


def lens(text="SUPPORTS_DECISION", proportion="SUPPORTS_DECISION", process="SUPPORTS_DECISION", reasoning="Article 2 covers the repeated posting."):
    return {
        "lenses": {
            "text": {"finding": text, "note": "n"},
            "proportion": {"finding": proportion, "note": "n"},
            "process": {"finding": process, "note": "n"},
        },
        "cited_articles": [2, 3],
        "reasoning": reasoning,
    }


UPHOLD = lens()
OVERTURN = lens("AGAINST_DECISION", "AGAINST_DECISION", "SUPPORTS_DECISION", "No article was violated and no warning was given.")
REMAND = lens("SUPPORTS_DECISION", "AGAINST_DECISION", "SUPPORTS_DECISION", "The sanction looks too harsh for first offense.")


def rule(c, aid, model, caller=STRANGER, prompts=None):
    calls = prompts if prompts is not None else []

    def exec_prompt(prompt, response_format="json"):
        calls.append(prompt)
        if isinstance(model, Exception):
            raise model
        return model

    set_caller(caller)
    with _patch.object(gl.nondet, "exec_prompt", side_effect=exec_prompt):
        c.rule_appeal(aid)
    return jl(c.get_appeal(aid))


def after_response_window(c):
    CLOCK.advance(RESP_WINDOW + 1)


def ruled_case(c, model=UPHOLD, **over):
    cid, did, aid = full_case(c, **over)
    after_response_window(c)
    rule(c, aid, model)
    return cid, did, aid


def pending(c, address):
    return int(c.get_pending_withdrawal(address))


def total_pending(c):
    return sum(int(v) for v in c.pending_withdrawals.values())


def expect_error(testcase, fn, *args, **kwargs):
    with testcase.assertRaises(gl.vm.UserError) as ctx:
        fn(*args, **kwargs)
    return str(ctx.exception)


def treasury(c):
    return int(jl(c.get_treasury())["balance_wei"])


def accounting(c):
    return jl(c.get_accounting())


def withdraw_as(c, who):
    set_caller(who)
    before = len(gl.evm.transfers)
    out = c.withdraw()
    for tx in gl.evm.transfers[before:]:
        c.balance = c.balance - u256(int(tx["value"]))
    return out
