import copy
import datetime
import random
import unittest
from unittest.mock import patch
from _bootstrap import *

S, A, I = "SUPPORTS_DECISION", "AGAINST_DECISION", "INSUFFICIENT"
STEWARDS = ["0x" + "a1" * 20, "0x" + "a2" * 20]
MEMBERS = ["0x" + "b1" * 20, "0x" + "b2" * 20, "0x" + "b3" * 20]
ADMIN = "0x" + "e1" * 20
OUTSIDER = "0x" + "d1" * 20
TEXT = "Plenty of words to pass every minimum length check here."


def at(iso, offset):
    CLOCK.now = PolicyCourt._parse_iso(iso) + datetime.timedelta(seconds=offset)


def allowed(fn, *args):
    try:
        fn(*args)
        return True
    except gl.vm.UserError:
        return False


class DeadlineBoundaryTests(unittest.TestCase):
    def fresh(self):
        c = make_contract()
        cid, did, aid = full_case(c)
        return c, cid, did, aid

    def check(self, setup, deadline_of, action, expect):
        for offset, ok in zip((-1, 0, 1), expect):
            c, extra = setup()
            at(deadline_of(c, extra), offset)
            self.assertEqual(allowed(action, c, extra), ok, (action.__name__, offset))

    def test_reply_evidence_and_rule_share_one_boundary(self):
        def setup():
            c, cid, did, aid = self.fresh()
            return c, aid
        dl = lambda c, aid: jl(c.get_appeal(aid))["response_deadline"]
        def respond(c, aid):
            set_caller(STEWARD); c.respond_to_appeal(aid, TEXT)
        def appellant_evidence(c, aid):
            set_caller(MEMBER); c.add_evidence(aid, TEXT)
        def steward_evidence(c, aid):
            set_caller(STEWARD); c.add_evidence(aid, TEXT)
        def stranger_rules(c, aid):
            rule(c, aid, UPHOLD)
        self.check(setup, dl, respond, (True, True, False))
        self.check(setup, dl, appellant_evidence, (True, True, False))
        self.check(setup, dl, steward_evidence, (True, True, False))
        self.check(setup, dl, stranger_rules, (False, False, True))

    def test_filing_window(self):
        def setup():
            c = make_contract()
            cid = register(c)
            return c, decide(c, cid)
        def file(c, did):
            set_caller(MEMBER); call_payable(c, "file_appeal", 5 * GEN, did, GROUNDS, "")
        def file_ok(c, did):
            try:
                file(c, did)
                return None
            except PaymentRejected as e:
                raise gl.vm.UserError(str(e))
        self.check(setup, lambda c, did: jl(c.get_decision(did))["filing_deadline"], file_ok, (True, True, False))

    def test_remand_review_second_appeal_finalize_and_void(self):
        def remanded():
            c, cid, did, aid = self.fresh()
            after_response_window(c)
            rule(c, aid, REMAND)
            return c, aid
        def upheld():
            c, cid, did, aid = self.fresh()
            after_response_window(c)
            rule(c, aid, UPHOLD)
            return c, aid
        def review(c, aid):
            set_caller(STEWARD); c.review_remand(aid, "REAFFIRM", "Reviewed and it stands.")
        def again(c, aid):
            set_caller(MEMBER)
            try:
                call_payable(c, "appeal_again", 5 * GEN, aid, TEXT)
            except PaymentRejected as e:
                raise gl.vm.UserError(str(e))
        def finalize(c, aid):
            set_caller(STRANGER); c.finalize_appeal(aid)
        def void(c, aid):
            set_caller(STRANGER); c.void_stalled_appeal(aid)
        self.check(remanded, lambda c, aid: jl(c.get_appeal(aid))["review_deadline"], review, (True, True, False))
        self.check(upheld, lambda c, aid: jl(c.get_appeal(aid))["appeal_deadline"], again, (True, True, False))
        self.check(upheld, lambda c, aid: jl(c.get_appeal(aid))["appeal_deadline"], finalize, (False, False, True))
        def stalled():
            c, cid, did, aid = self.fresh()
            return c, aid
        limit = lambda c, aid: (PolicyCourt._parse_iso(jl(c.get_appeal(aid))["response_deadline"])
                                + datetime.timedelta(seconds=PolicyCourt.RULING_TIMEOUT_SECONDS)).isoformat()
        self.check(stalled, limit, void, (False, False, True))

    def test_steward_may_concede_after_the_reply_deadline_until_a_ruling(self):
        c, cid, did, aid = self.fresh()
        after_response_window(c)
        set_caller(STEWARD)
        c.concede_appeal(aid, "Conceding before the panel rules.")
        self.assertEqual(jl(c.get_appeal(aid))["final_outcome"], "OVERTURNED")

    def test_terminal_appeals_cannot_be_reopened_or_settled_twice(self):
        c, cid, did, aid = self.fresh()
        after_response_window(c)
        rule(c, aid, OVERTURN)
        attempts = [
            lambda: (set_caller(STEWARD), c.concede_appeal(aid, "Too late to concede now.")),
            lambda: (set_caller(STEWARD), c.respond_to_appeal(aid, TEXT)),
            lambda: (set_caller(MEMBER), c.add_evidence(aid, TEXT)),
            lambda: rule(c, aid, UPHOLD),
            lambda: (set_caller(MEMBER), c.accept_ruling(aid)),
            lambda: (set_caller(STRANGER), c.finalize_appeal(aid)),
            lambda: (set_caller(STRANGER), c.void_stalled_appeal(aid)),
            lambda: (set_caller(STEWARD), c.review_remand(aid, "REVERSE", "Trying to reverse again.")),
        ]
        before = (dict(c.appeals), dict(c.pending_withdrawals), int(c.final_count))
        CLOCK.advance(30 * DAY)
        for attempt in attempts:
            with self.assertRaises(gl.vm.UserError):
                attempt()
        set_caller(MEMBER)
        with self.assertRaises(PaymentRejected):
            call_payable(c, "appeal_again", 5 * GEN, aid, TEXT)
        self.assertEqual(jl(c.get_appeal(aid))["status"], "final")
        self.assertEqual(sum(1 for h in jl(c.get_appeal(aid))["history"] if h["event"] == "settled"), 1)


def act(c, name, aid, who):
    set_caller(who)
    if name == "add_evidence":
        return c.add_evidence(aid, TEXT)
    if name == "respond_to_appeal":
        return c.respond_to_appeal(aid, TEXT)
    if name == "concede_appeal":
        return c.concede_appeal(aid, "Conceding after review.")
    if name == "rule_appeal":
        with patch.object(gl.nondet, "exec_prompt", return_value=UPHOLD):
            return c.rule_appeal(aid)
    if name == "review_remand":
        return c.review_remand(aid, "REAFFIRM", "Reviewed and it stands.")
    if name == "appeal_again":
        stake = int(jl(c.get_appeal(aid))["stake"])
        out = call_payable(c, "appeal_again", stake, aid, TEXT)
        return out
    return getattr(c, name)(aid)


class ActionsViewTests(unittest.TestCase):
    def test_the_view_never_offers_an_action_the_contract_rejects(self):
        rng = random.Random(7)
        checked = 0
        models = [UPHOLD, OVERTURN, REMAND, lens(S, S, I)]
        for run in range(40):
            c = make_contract()
            cid, did, aid = full_case(c)
            for step in range(8):
                when = CLOCK.now.isoformat()
                for who in (MEMBER, STEWARD, STRANGER):
                    for name in jl(c.get_appeal_actions(aid, who, when))["actions"]:
                        trial = copy.deepcopy(c)
                        saved = copy.deepcopy(c.balance)
                        try:
                            act(trial, name, aid, who)
                        except (gl.vm.UserError, PaymentRejected) as e:
                            self.fail(f"view offered {name} to {who} at step {step} but it failed: {e}")
                        checked += 1
                CLOCK.advance(rng.choice([1, 60, RESP_WINDOW // 2, RESP_WINDOW + 1, APPEAL_WINDOW + 1, 4 * DAY]))
                status = jl(c.get_appeal(aid))["status"]
                if status in ("final", "void"):
                    break
                try:
                    choice = rng.choice(["rule", "respond", "review", "again", "accept", "none"])
                    if choice == "rule":
                        rule(c, aid, rng.choice(models), caller=rng.choice([MEMBER, STRANGER]))
                    elif choice == "respond":
                        act(c, "respond_to_appeal", aid, STEWARD)
                    elif choice == "review":
                        act(c, "review_remand", aid, STEWARD)
                    elif choice == "again":
                        act(c, "appeal_again", aid, MEMBER)
                    elif choice == "accept":
                        act(c, "accept_ruling", aid, MEMBER)
                except (gl.vm.UserError, PaymentRejected):
                    pass
        self.assertGreater(checked, 100)


class RandomizedInvariantTests(unittest.TestCase):
    def assert_books(self, c, where):
        acc = accounting(c)
        self.assertTrue(acc["balanced"], (where, acc))
        self.assertTrue(acc["treasury_flows_match"], (where, acc))
        self.assertEqual(int(acc["owed_to_users_wei"]), total_pending(c), where)
        for s in STEWARDS:
            self.assertEqual(pending(c, s), 0, where)
        for key in list(c.appeals.keys()):
            a = jl(c.appeals[key])
            self.assertLessEqual(sum(1 for h in a["history"] if h["event"] == "settled"), 1, where)
            if a["settlement"]:
                self.assertEqual(int(a["settlement"]["to_appellant"]) + int(a["settlement"]["to_treasury"]), int(a["settlement"]["stake"]), where)

    def test_random_sequences_keep_every_invariant(self):
        models = [UPHOLD, OVERTURN, REMAND, lens(S, S, I), lens(A, S, S), lens(I, I, I), {}]
        successes = 0
        by_op = {}
        for seed in range(80):
            rng = random.Random(seed)
            set_caller(ADMIN)
            c = make_contract()
            for i, s in enumerate(STEWARDS):
                register(c, steward=s, name=f"Guild number {i}", min_stake_gen=rng.choice([1, 2, 5]),
                         upheld_refund_bps=rng.choice([0, 1, 2000, 4999, 5000]), remand_refund_bps=rng.choice([5000, 7001, 9999, 10000]))
            for step in range(160):
                n_dec, n_app = int(c.decision_count), int(c.appeal_count)
                op = rng.choice(["decide", "decide", "file", "file", "file", "file_bad", "evidence", "respond", "respond",
                                 "rule", "rule", "rule", "concede", "review", "review", "again", "again", "accept",
                                 "accept", "accept", "finalize", "finalize", "void", "withdraw", "propose", "propose", "propose",
                                 "cancel", "execute", "execute", "execute", "execute",
                                 "time", "time", "time"])
                aid = str(rng.randrange(n_app)) if n_app else "0"
                did = str(rng.randrange(n_dec)) if n_dec else "0"
                case = jl(c.appeals[aid]) if aid in c.appeals else None
                dec = jl(c.decisions[did]) if did in c.decisions else None
                appellant = case["appellant"] if case else rng.choice(MEMBERS)
                steward = case["steward"] if case else rng.choice(STEWARDS)
                try:
                    if op == "decide":
                        cid = str(rng.randrange(2))
                        decide(c, cid, subject=rng.choice(MEMBERS), steward=STEWARDS[int(cid)])
                    elif op in ("file", "file_bad"):
                        set_caller(dec["subject"] if (dec and op == "file") else OUTSIDER)
                        call_payable(c, "file_appeal", rng.choice([1, 2, 5, 7]) * GEN + rng.choice([0, 1, 3]), did, GROUNDS, "")
                    elif op == "evidence":
                        set_caller(rng.choice([appellant, steward])); c.add_evidence(aid, TEXT)
                    elif op == "respond":
                        set_caller(steward); c.respond_to_appeal(aid, TEXT)
                    elif op == "rule":
                        rule(c, aid, rng.choice(models), caller=rng.choice([appellant, OUTSIDER]))
                    elif op == "concede":
                        set_caller(steward); c.concede_appeal(aid, "Conceding after review.")
                    elif op == "review":
                        set_caller(steward); c.review_remand(aid, rng.choice(["REAFFIRM", "REVERSE"]), "Reviewed with reasons.")
                    elif op == "again":
                        set_caller(appellant)
                        stake = int(case["stake"]) if case else GEN
                        call_payable(c, "appeal_again", stake + rng.choice([0, 1, GEN]), aid, TEXT)
                    elif op == "accept":
                        set_caller(appellant); c.accept_ruling(aid)
                    elif op == "finalize":
                        set_caller(OUTSIDER); c.finalize_appeal(aid)
                    elif op == "void":
                        set_caller(OUTSIDER); c.void_stalled_appeal(aid)
                    elif op == "withdraw":
                        withdraw_as(c, rng.choice(MEMBERS + [OUTSIDER]))
                    elif op == "propose":
                        set_caller(ADMIN)
                        avail = int(jl(c.get_treasury())["available_wei"])
                        kind = rng.choice(["APPEAL_COSTS", "SUSTAINABILITY", "COMPENSATION"])
                        to = appellant if kind == "COMPENSATION" else rng.choice([OUTSIDER] + MEMBERS)
                        c.propose_treasury_payout(to, max(1, avail // rng.choice([4, 8, 5])), kind,
                                                  aid if kind == "COMPENSATION" or rng.random() < 0.3 else "", "Randomized payout for testing")
                    elif op == "cancel":
                        set_caller(ADMIN); c.cancel_treasury_payout(jl(c.get_treasury())["open_proposal_id"] or "0")
                    elif op == "execute":
                        set_caller(OUTSIDER); c.execute_treasury_payout(jl(c.get_treasury())["open_proposal_id"] or "0")
                    else:
                        CLOCK.advance(rng.choice([30, RESP_WINDOW + 1, APPEAL_WINDOW + 1, 3600, 4 * DAY]))
                    successes += 1
                    by_op[op] = by_op.get(op, 0) + 1
                except (gl.vm.UserError, PaymentRejected):
                    pass
                self.assert_books(c, (seed, step, op))
        self.assertGreater(successes, 400)
        for op in ("decide", "file", "rule", "respond", "concede", "review", "again", "accept", "finalize", "void", "withdraw", "propose", "execute"):
            self.assertGreater(by_op.get(op, 0), 0, (op, by_op))
        RandomizedInvariantTests.coverage = (successes, by_op)


if __name__ == "__main__":
    unittest.main()
