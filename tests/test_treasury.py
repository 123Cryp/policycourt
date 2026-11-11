import unittest
from _bootstrap import *

ADMIN = "0x" + "ee" * 20
OTHER = "0x" + "ff" * 20


def treasury_contract():
    set_caller(ADMIN)
    c = make_contract()
    return c


def forfeit_case(c, model=UPHOLD):
    cid, did, aid = ruled_case(c, model)
    set_caller(MEMBER)
    c.accept_ruling(aid)
    return cid, did, aid


DELAY = PolicyCourt.TREASURY_DELAY_SECONDS


def snapshot(c):
    return (dict(c.treasury_proposals), dict(c.treasury_entries), dict(c.settings), dict(c.pending_withdrawals),
            int(c.treasury_wei), int(c.treasury_reserved_wei), int(c.treasury_out_wei), int(c.owed_wei), int(c.treasury_proposal_count))


class TreasuryTests(unittest.TestCase):
    def setUp(self):
        self.c = treasury_contract()
        self.cid, self.did, self.aid = forfeit_case(self.c)
        self.fund = 5 * GEN - 5 * GEN * 2000 // 10000
        self.cap = self.fund * 2500 // 10000

    def propose(self, who=ADMIN, to=OTHER, amount=None, purpose="APPEAL_COSTS", ref="", note="Reimbursing validator costs for case 0"):
        set_caller(who)
        return jl(self.c.propose_treasury_payout(to, amount if amount is not None else GEN // 2, purpose, ref, note))

    def execute(self, pid, who=STRANGER):
        set_caller(who)
        return jl(self.c.execute_treasury_payout(pid))

    def test_deployer_is_admin(self):
        t = jl(self.c.get_treasury())
        self.assertEqual((t["admin"], t["balance_wei"], t["available_wei"]), (ADMIN, str(self.fund), str(self.fund)))
        set_caller(OTHER)
        expect_error(self, self.c.claim_treasury_admin)

    def test_full_payout_flow_updates_every_total_exactly_once(self):
        before_entries = int(self.c.treasury_entry_count)
        p = self.propose(amount=GEN // 2)
        self.assertEqual(p["status"], "pending")
        t = jl(self.c.get_treasury())
        self.assertEqual((t["reserved_wei"], t["available_wei"], t["balance_wei"]), (str(GEN // 2), str(self.fund - GEN // 2), str(self.fund)))
        self.assertEqual(int(self.c.treasury_entry_count), before_entries)
        CLOCK.advance(DELAY)
        e = self.execute(p["proposal_id"])
        self.assertEqual(e["status"], "executed")
        t = jl(self.c.get_treasury())
        self.assertEqual((t["balance_wei"], t["reserved_wei"], t["paid_out_wei"], t["paid_by_purpose_wei"]["APPEAL_COSTS"]),
                         (str(self.fund - GEN // 2), "0", str(GEN // 2), str(GEN // 2)))
        self.assertEqual(int(self.c.treasury_entry_count), before_entries + 1)
        led = jl(self.c.list_treasury_entries(0, 1))["rows"][0]
        self.assertEqual((led["type"], led["amount_wei"], led["to"], led["proposal_id"]), ("PAYOUT", str(GEN // 2), OTHER, p["proposal_id"]))
        self.assertEqual(pending(self.c, OTHER), GEN // 2)
        acc = accounting(self.c)
        self.assertTrue(acc["balanced"] and acc["treasury_flows_match"], acc)
        withdraw_as(self.c, OTHER)
        self.assertTrue(accounting(self.c)["balanced"])

    def test_delay_boundaries_and_replay(self):
        p = self.propose()
        CLOCK.advance(DELAY - 1)
        expect_error(self, self.execute, p["proposal_id"])
        CLOCK.advance(1)
        self.execute(p["proposal_id"])
        expect_error(self, self.execute, p["proposal_id"])
        set_caller(ADMIN)
        expect_error(self, self.c.cancel_treasury_payout, p["proposal_id"])

    def test_cancel_releases_the_reserve_and_cannot_be_executed(self):
        p = self.propose()
        set_caller(OTHER)
        expect_error(self, self.c.cancel_treasury_payout, p["proposal_id"])
        set_caller(ADMIN)
        self.c.cancel_treasury_payout(p["proposal_id"])
        self.assertEqual(jl(self.c.get_treasury())["reserved_wei"], "0")
        CLOCK.advance(DELAY + 1)
        expect_error(self, self.execute, p["proposal_id"])
        self.assertEqual(treasury(self.c), self.fund)

    def test_one_open_proposal_and_per_payout_cap(self):
        expect_error(self, self.propose, amount=self.cap + 1)
        self.propose(amount=self.cap)
        expect_error(self, self.propose, amount=1)

    def test_rejected_proposals_leave_no_trace(self):
        bad = [dict(who=STEWARD), dict(who=MEMBER), dict(to=ADMIN), dict(to=STEWARD), dict(purpose="BONUS"), dict(to="0x123"),
               dict(to="not-an-address"), dict(amount=0), dict(amount=-1), dict(amount=True), dict(amount=self.fund),
               dict(note="short"), dict(ref="99"), dict(purpose="COMPENSATION", ref=""), dict(purpose="COMPENSATION", ref=self.aid, to=MEMBER)]
        for over in bad:
            before = snapshot(self.c)
            expect_error(self, self.propose, **over)
            self.assertEqual(snapshot(self.c), before, over)

    def test_compensation_needs_an_appeal_that_went_against_the_steward(self):
        c = treasury_contract()
        forfeit_case(c)
        cid, did, aid = ruled_case(c, OVERTURN)
        fund = treasury(c)
        set_caller(ADMIN)
        p = jl(c.propose_treasury_payout(MEMBER, fund // 4, "COMPENSATION", aid, "Compensating a member after a procedural error"))
        self.assertEqual(p["purpose"], "COMPENSATION")
        set_caller(ADMIN)
        c.cancel_treasury_payout(p["proposal_id"])
        p = jl(c.propose_treasury_payout(MEMBER, fund // 4, "COMPENSATION", aid, "Compensating a member after a procedural error"))
        CLOCK.advance(DELAY)
        set_caller(STRANGER)
        c.execute_treasury_payout(p["proposal_id"])
        set_caller(ADMIN)
        msg = expect_error(self, c.propose_treasury_payout, MEMBER, 1, "COMPENSATION", aid, "Second compensation for the same case")
        self.assertIn("already", msg)
        expect_error(self, c.propose_treasury_payout, MEMBER2, 1, "COMPENSATION", aid, "Paying someone who did not appeal")

    def test_recipient_who_becomes_a_steward_cannot_be_paid(self):
        p = self.propose(to=OTHER)
        register(self.c, steward=OTHER, name="Other Guild")
        CLOCK.advance(DELAY)
        expect_error(self, self.execute, p["proposal_id"])
        self.assertEqual(jl(self.c.get_treasury())["reserved_wei"], str(GEN // 2))

    def test_two_step_admin_handover(self):
        set_caller(OTHER)
        expect_error(self, self.c.propose_treasury_admin, OTHER)
        expect_error(self, self.c.accept_treasury_admin)
        set_caller(ADMIN)
        expect_error(self, self.c.propose_treasury_admin, ADMIN)
        expect_error(self, self.c.propose_treasury_admin, "nope")
        self.c.propose_treasury_admin(OTHER)
        self.assertEqual(jl(self.c.get_treasury())["admin"], ADMIN)
        set_caller(MEMBER2)
        expect_error(self, self.c.accept_treasury_admin)
        set_caller(OTHER)
        self.c.accept_treasury_admin()
        t = jl(self.c.get_treasury())
        self.assertEqual((t["admin"], t["pending_admin"]), (OTHER, ""))
        expect_error(self, self.propose, who=ADMIN, to=MEMBER2)
        self.propose(who=OTHER, to=MEMBER2)

    def test_ledger_and_proposals_list_newest_first(self):
        p = self.propose()
        CLOCK.advance(DELAY)
        self.execute(p["proposal_id"])
        self.assertEqual([r["type"] for r in jl(self.c.list_treasury_entries(0, 10))["rows"]], ["PAYOUT", "FORFEIT"])
        self.assertEqual(jl(self.c.list_treasury_proposals(0, 10))["rows"][0]["status"], "executed")


class SurplusTests(unittest.TestCase):
    def test_unsolicited_gen_is_surplus_not_a_liability(self):
        c = make_contract()
        full_case(c)
        c.balance = c.balance + u256(3 * GEN)
        acc = accounting(c)
        self.assertEqual((acc["solvent"], acc["balanced"], acc["surplus_wei"]), (True, False, str(3 * GEN)))
        self.assertEqual(acc["accounted_wei"], str(5 * GEN))


class AccountingInvariantTests(unittest.TestCase):
    def check(self, c):
        acc = accounting(c)
        self.assertTrue(acc["balanced"], acc)
        self.assertEqual(int(acc["owed_to_users_wei"]), total_pending(c))
        self.assertEqual(pending(c, STEWARD), 0)

    def test_every_settlement_path_keeps_the_books_balanced(self):
        S, A, I = "SUPPORTS_DECISION", "AGAINST_DECISION", "INSUFFICIENT"
        paths = []

        def upheld(c, aid):
            set_caller(MEMBER); c.accept_ruling(aid)
        def remand_reaffirm(c, aid):
            set_caller(STEWARD); c.review_remand(aid, "REAFFIRM", "Reviewed again and it stands.")
            set_caller(MEMBER); c.accept_ruling(aid)
        def remand_reverse(c, aid):
            set_caller(STEWARD); c.review_remand(aid, "REVERSE", "Reviewed again and lifted it.")
        def remand_silent(c, aid):
            CLOCK.advance(RESP_WINDOW + APPEAL_WINDOW + 5); set_caller(STRANGER); c.finalize_appeal(aid)
        def round2(model):
            def go(c, aid):
                set_caller(MEMBER)
                call_payable(c, "appeal_again", 5 * GEN, aid, "New evidence: the warning log has no entry for me.")
                CLOCK.advance(RESP_WINDOW + 1)
                rule(c, aid, model)
            return go
        def remand_then_round2(c, aid):
            set_caller(STEWARD); c.review_remand(aid, "REAFFIRM", "We still hold the warning was sent.")
            round2(UPHOLD)(c, aid)
        def round2_void(c, aid):
            set_caller(MEMBER)
            call_payable(c, "appeal_again", 5 * GEN, aid, "New evidence: the warning log has no entry for me.")
            CLOCK.advance(RESP_WINDOW + 3 * DAY + 1); set_caller(STRANGER); c.void_stalled_appeal(aid)

        for model, after in [(UPHOLD, upheld), (lens(S, A, S), remand_reaffirm), (lens(S, A, S), remand_reverse),
                             (lens(S, A, S), remand_silent), (UPHOLD, round2(UPHOLD)), (UPHOLD, round2(OVERTURN)),
                             (lens(S, S, I), remand_then_round2), (UPHOLD, round2_void), (OVERTURN, None)]:
            c = make_contract()
            cid, did, aid = ruled_case(c, model)
            if after:
                after(c, aid)
            self.assertIn(jl(c.get_appeal(aid))["status"], ("final", "void"))
            self.check(c)
            s = jl(c.get_appeal(aid))["settlement"]
            self.assertEqual(int(s["to_appellant"]) + int(s["to_treasury"]), int(s["stake"]))
            self.assertEqual(treasury(c), int(s["to_treasury"]))
            withdraw_as(c, MEMBER)
            self.check(c)

    def test_concession_void_and_bounce_keep_the_books_balanced(self):
        c = make_contract()
        cid, did, aid = full_case(c)
        set_caller(STEWARD)
        c.concede_appeal(aid, "We concede after review.")
        self.check(c)
        c = make_contract()
        cid, did, aid = full_case(c)
        CLOCK.advance(RESP_WINDOW + 3 * DAY + 1)
        set_caller(STRANGER)
        c.void_stalled_appeal(aid)
        self.check(c)
        set_caller(STRANGER)
        with self.assertRaises(PaymentRejected):
            call_payable(c, "file_appeal", 3 * GEN, did, GROUNDS, "")
        self.check(c)
        self.assertEqual(int(accounting(c)["stakes_held_wei"]), 0)

    def test_open_stakes_are_counted_as_held(self):
        c = make_contract()
        full_case(c)
        acc = accounting(c)
        self.assertEqual((acc["stakes_held_wei"], acc["owed_to_users_wei"], acc["treasury_wei"]), (str(5 * GEN), "0", "0"))
        self.assertTrue(acc["balanced"])


if __name__ == "__main__":
    unittest.main()
