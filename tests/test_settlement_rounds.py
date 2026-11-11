import unittest
from _bootstrap import *


def solvent(tc, c):
    acc = accounting(c)
    tc.assertTrue(acc["balanced"], acc)
    tc.assertEqual(int(acc["owed_to_users_wei"]), total_pending(c))
    tc.assertEqual(pending(c, STEWARD), 0, "a steward must never be credited from a forfeit")


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_upheld_splits_by_charter_and_conserves_gen(self):
        cid, did, aid = ruled_case(self.c, UPHOLD)
        set_caller(MEMBER)
        out = jl(self.c.accept_ruling(aid))
        self.assertEqual(out["final_outcome"], "UPHELD")
        self.assertEqual(pending(self.c, MEMBER), 5 * GEN * 2000 // 10000)
        self.assertEqual(treasury(self.c), 5 * GEN - 5 * GEN * 2000 // 10000)
        self.assertEqual(jl(self.c.get_decision(did))["status"], "upheld")
        solvent(self, self.c)

    def test_finalize_after_window_is_permissionless(self):
        cid, did, aid = ruled_case(self.c, UPHOLD)
        set_caller(STRANGER)
        expect_error(self, self.c.finalize_appeal, aid)
        CLOCK.advance(APPEAL_WINDOW + 1)
        self.assertIn("finalize_appeal", jl(self.c.get_appeal_actions(aid, STRANGER, CLOCK.now.isoformat()))["actions"])
        self.c.finalize_appeal(aid)
        self.assertEqual(jl(self.c.get_appeal(aid))["final_outcome"], "UPHELD")
        solvent(self, self.c)

    def test_only_appellant_accepts(self):
        cid, did, aid = ruled_case(self.c, UPHOLD)
        set_caller(STEWARD)
        expect_error(self, self.c.accept_ruling, aid)

    def test_remand_reaffirmed_uses_remand_split(self):
        cid, did, aid = ruled_case(self.c, REMAND)
        set_caller(MEMBER)
        expect_error(self, self.c.accept_ruling, aid)
        set_caller(STEWARD)
        self.c.review_remand(aid, "reaffirm", "Reviewed the log again and the ban stands.")
        set_caller(MEMBER)
        out = jl(self.c.accept_ruling(aid))
        self.assertEqual(out["final_outcome"], "REMANDED")
        self.assertEqual(pending(self.c, MEMBER), 5 * GEN * 7000 // 10000)
        self.assertEqual(treasury(self.c), 5 * GEN * 3000 // 10000)
        self.assertEqual(jl(self.c.get_decision(did))["status"], "reaffirmed")
        solvent(self, self.c)

    def test_remand_reversed_by_steward_refunds_all(self):
        cid, did, aid = ruled_case(self.c, REMAND)
        set_caller(MEMBER)
        expect_error(self, self.c.review_remand, aid, "REVERSE", "I am not the steward at all")
        set_caller(STEWARD)
        expect_error(self, self.c.review_remand, aid, "MAYBE", "Not a valid action value")
        expect_error(self, self.c.review_remand, aid, "REVERSE", "short")
        out = jl(self.c.review_remand(aid, "REVERSE", "The sanction was too harsh; ban lifted."))
        self.assertEqual(out["final_outcome"], "REVERSED")
        self.assertEqual(pending(self.c, MEMBER), 5 * GEN)
        self.assertEqual(jl(self.c.get_decision(did))["status"], "reversed")
        self.assertEqual(jl(self.c.get_profile(MEMBER))["overturned"], 1)
        solvent(self, self.c)

    def test_remand_review_cannot_happen_twice_or_late(self):
        cid, did, aid = ruled_case(self.c, REMAND)
        set_caller(STEWARD)
        self.c.review_remand(aid, "REAFFIRM", "Reviewed the log again and the ban stands.")
        expect_error(self, self.c.review_remand, aid, "REVERSE", "Changing my mind after reaffirming")

    def test_remand_review_window_closes(self):
        cid, did, aid = ruled_case(self.c, REMAND)
        CLOCK.advance(RESP_WINDOW + 1)
        set_caller(STEWARD)
        expect_error(self, self.c.review_remand, aid, "REVERSE", "Too late to review this remand now")

    def test_remand_ignored_by_steward_refunds_appellant_fully(self):
        cid, did, aid = ruled_case(self.c, REMAND)
        CLOCK.advance(RESP_WINDOW + APPEAL_WINDOW + 2)
        set_caller(STRANGER)
        out = jl(self.c.finalize_appeal(aid))
        self.assertEqual(out["final_outcome"], "REMANDED_UNANSWERED")
        self.assertEqual(pending(self.c, MEMBER), 5 * GEN)
        self.assertEqual(pending(self.c, STEWARD), 0)
        self.assertEqual(jl(self.c.get_decision(did))["status"], "stands")
        solvent(self, self.c)

    def test_stalled_appeal_is_voided_with_full_refund_and_can_be_refiled(self):
        cid, did, aid = full_case(self.c)
        set_caller(STRANGER)
        expect_error(self, self.c.void_stalled_appeal, aid)
        CLOCK.advance(RESP_WINDOW + 3 * DAY + 1)
        self.assertIn("void_stalled_appeal", jl(self.c.get_appeal_actions(aid, STRANGER, CLOCK.now.isoformat()))["actions"])
        out = jl(self.c.void_stalled_appeal(aid))
        self.assertEqual(out["status"], "void")
        self.assertEqual(pending(self.c, MEMBER), 5 * GEN)
        d = jl(self.c.get_decision(did))
        self.assertEqual((d["status"], d["appeal_id"]), ("in_force", ""))
        solvent(self, self.c)

    def test_withdraw_pays_out_and_zeroes_ledger(self):
        cid, did, aid = ruled_case(self.c, OVERTURN)
        set_caller(MEMBER)
        self.c.withdraw()
        self.assertEqual(gl.evm.transfers[-1], {"to": MEMBER, "value": 5 * GEN})
        self.assertEqual(pending(self.c, MEMBER), 0)
        expect_error(self, self.c.withdraw)
        set_caller(STRANGER)
        expect_error(self, self.c.withdraw)

    def test_forfeit_goes_to_treasury_and_is_ledgered(self):
        cid, did, aid = ruled_case(self.c, UPHOLD)
        set_caller(MEMBER)
        self.c.accept_ruling(aid)
        kept = 5 * GEN - 5 * GEN * 2000 // 10000
        self.assertEqual(jl(self.c.get_charter(cid))["forfeited_to_treasury_wei"], str(kept))
        self.assertEqual(jl(self.c.get_charter_stats(cid))["forfeited_to_treasury_wei"], str(kept))
        self.assertNotIn("earned_wei", jl(self.c.get_profile(STEWARD)))
        self.assertEqual(pending(self.c, STEWARD), 0)
        entry = jl(self.c.list_treasury_entries(0, 5))["rows"][0]
        self.assertEqual((entry["type"], entry["amount_wei"], entry["appeal_id"]), ("FORFEIT", str(kept), aid))
        self.assertEqual(jl(self.c.get_profile(MEMBER))["forfeited_wei"], str(kept))


class SecondAppealTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()
        self.cid, self.did, self.aid = ruled_case(self.c, UPHOLD)

    def again(self, extra=5, who=MEMBER, text="New evidence: the warning log has no entry for me at all."):
        set_caller(who)
        return jl(call_payable(self.c, "appeal_again", extra * GEN, self.aid, text))

    def test_second_appeal_needs_at_least_double_total_stake(self):
        with self.assertRaises(PaymentRejected):
            self.again(extra=4)
        a = self.again(extra=5)
        self.assertEqual(a["stake"], str(10 * GEN))
        self.assertEqual((a["round"], a["status"]), (2, "round2_filed"))

    def test_only_appellant_and_not_after_window(self):
        with self.assertRaises(PaymentRejected):
            self.again(who=STEWARD)
        with self.assertRaises(PaymentRejected):
            self.again(text="short")
        CLOCK.advance(APPEAL_WINDOW + 1)
        with self.assertRaises(PaymentRejected):
            self.again()
        self.assertEqual(jl(self.c.get_appeal(self.aid))["round"], 1)

    def test_no_second_appeal_before_remand_review_resolves(self):
        c = make_contract()
        cid, did, aid = ruled_case(c, REMAND)
        set_caller(MEMBER)
        with self.assertRaises(PaymentRejected):
            call_payable(c, "appeal_again", 5 * GEN, aid, "New evidence: the warning log has no entry for me.")
        set_caller(STEWARD)
        c.review_remand(aid, "REAFFIRM", "Reviewed the log again and the ban stands.")
        set_caller(MEMBER)
        a = jl(call_payable(c, "appeal_again", 5 * GEN, aid, "New evidence: the warning log has no entry for me."))
        self.assertEqual(a["round"], 2)

    def test_round_two_overturn_returns_whole_doubled_stake(self):
        self.again()
        CLOCK.advance(RESP_WINDOW + 1)
        a = rule(self.c, self.aid, OVERTURN)
        self.assertEqual((a["status"], a["final_outcome"]), ("final", "OVERTURNED"))
        self.assertEqual(pending(self.c, MEMBER), 10 * GEN)
        self.assertEqual(jl(self.c.get_decision(self.did))["status"], "overturned")
        solvent(self, self.c)

    def test_round_two_upheld_forfeits_by_charter_on_total_stake(self):
        self.again()
        CLOCK.advance(RESP_WINDOW + 1)
        a = rule(self.c, self.aid, UPHOLD)
        self.assertEqual(a["final_outcome"], "UPHELD")
        self.assertEqual(pending(self.c, MEMBER), 10 * GEN * 2000 // 10000)
        self.assertEqual(treasury(self.c), 10 * GEN * 8000 // 10000)
        solvent(self, self.c)

    def test_round_two_disproportionate_sanction_overturns(self):
        self.again()
        CLOCK.advance(RESP_WINDOW + 1)
        a = rule(self.c, self.aid, REMAND)
        self.assertEqual(a["final_outcome"], "OVERTURNED")
        self.assertEqual(pending(self.c, MEMBER), 10 * GEN)

    def test_round_two_procedure_failure_alone_overturns_like_the_live_case(self):
        self.again()
        CLOCK.advance(RESP_WINDOW + 1)
        live = lens("SUPPORTS_DECISION", "SUPPORTS_DECISION", "AGAINST_DECISION", "No written warning was issued, so the ban must be overturned.")
        a = rule(self.c, self.aid, live)
        self.assertEqual((a["final_outcome"], a["verdict"]["outcome"]), ("OVERTURNED", "OVERTURNED"))
        self.assertEqual(pending(self.c, MEMBER), 10 * GEN)
        self.assertEqual(jl(self.c.get_decision(self.did))["status"], "overturned")
        solvent(self, self.c)

    def test_round_two_prompt_includes_prior_ruling_and_new_grounds(self):
        self.again()
        CLOCK.advance(RESP_WINDOW + 1)
        prompts = []
        rule(self.c, self.aid, UPHOLD, prompts=prompts)
        for needle in ["APPEAL ROUND 2", "PRIOR RULING (round 1)", "warning log has no entry", "FINAL round"]:
            self.assertIn(needle, prompts[0])

    def test_steward_gets_a_fresh_response_window_in_round_two(self):
        self.again()
        set_caller(STEWARD)
        self.c.respond_to_appeal(self.aid, "Second round: the warning is in the private moderator log.")
        a = jl(self.c.get_appeal(self.aid))
        self.assertIn("ROUND 2", a["response"])
        self.assertEqual(a["responded_round"], 2)
        a = rule(self.c, self.aid, UPHOLD, caller=MEMBER)
        self.assertEqual(a["round"], 2)

    def test_round_two_cannot_be_appealed_again(self):
        self.again()
        with self.assertRaises(PaymentRejected):
            self.again()

    def test_concession_in_round_two_refunds_everything(self):
        self.again()
        set_caller(STEWARD)
        self.c.concede_appeal(self.aid, "The log really has no entry; we concede.")
        self.assertEqual(pending(self.c, MEMBER), 10 * GEN)
        solvent(self, self.c)

    def test_second_round_stalled_refunds_extra_stake_and_applies_round_one_ruling(self):
        self.again()
        CLOCK.advance(RESP_WINDOW + 3 * DAY + 1)
        set_caller(STRANGER)
        out = jl(self.c.void_stalled_appeal(self.aid))
        first_back = 5 * GEN * 2000 // 10000
        self.assertEqual(pending(self.c, MEMBER), 5 * GEN + first_back)
        self.assertEqual(treasury(self.c), 5 * GEN - first_back)
        self.assertEqual(out["settlement"]["applied_result"], "UPHELD")
        d = jl(self.c.get_decision(self.did))
        self.assertEqual((d["status"], d["appeal_id"]), ("upheld", self.aid))
        solvent(self, self.c)

    def test_second_round_void_after_unanswered_remand_refunds_everything(self):
        c = make_contract()
        cid, did, aid = ruled_case(c, REMAND)
        CLOCK.advance(RESP_WINDOW + 1)
        set_caller(MEMBER)
        call_payable(c, "appeal_again", 5 * GEN, aid, "New evidence: the warning log has no entry for me.")
        CLOCK.advance(RESP_WINDOW + 3 * DAY + 1)
        set_caller(STRANGER)
        out = jl(c.void_stalled_appeal(aid))
        self.assertEqual(out["settlement"]["applied_result"], "REMANDED_UNANSWERED")
        self.assertEqual(pending(c, MEMBER), 10 * GEN)
        self.assertEqual(jl(c.get_decision(did))["status"], "stands")
        solvent(self, c)

    def test_profile_counts_total_stake_once_per_deposit(self):
        self.again()
        self.assertEqual(jl(self.c.get_profile(MEMBER))["staked_wei"], str(10 * GEN))


if __name__ == "__main__":
    unittest.main()
