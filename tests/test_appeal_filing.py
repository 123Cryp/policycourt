import unittest
from _bootstrap import *


class FilingTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()
        self.cid = register(self.c)
        self.did = decide(self.c, self.cid)

    def file(self, stake=5, who=MEMBER, did=None, grounds=GROUNDS):
        set_caller(who)
        return call_payable(self.c, "file_appeal", stake * GEN, did or self.did, grounds, "evidence text here")

    def test_subject_files_with_stake(self):
        a = jl(self.file())
        self.assertEqual(a["status"], "filed")
        self.assertEqual(a["stake"], str(5 * GEN))
        self.assertEqual(a["round"], 1)
        self.assertEqual(len(a["evidence"]), 1)
        self.assertEqual(jl(self.c.get_decision(self.did))["status"], "under_appeal")
        self.assertEqual(jl(self.c.get_decision(self.did))["appeal_id"], a["appeal_id"])

    def test_bigger_stake_is_kept_exactly(self):
        self.assertEqual(jl(self.file(stake=9))["stake"], str(9 * GEN))

    def test_rejections_refund_the_gen_without_state_change(self):
        for stake, who, grounds in [(4, MEMBER, GROUNDS), (5, STRANGER, GROUNDS), (5, STEWARD, GROUNDS), (5, MEMBER, "too short")]:
            before = pending(self.c, who)
            with self.assertRaises(PaymentRejected):
                self.file(stake=stake, who=who, grounds=grounds)
            self.assertEqual(pending(self.c, who) - before, stake * GEN)
        self.assertEqual(int(self.c.appeal_count), 0)
        self.assertEqual(jl(self.c.get_decision(self.did))["status"], "in_force")

    def test_unknown_decision_is_bounced(self):
        with self.assertRaises(PaymentRejected):
            self.file(did="55")

    def test_zero_value_rejection_reverts(self):
        set_caller(MEMBER)
        expect_error(self, call_payable, self.c, "file_appeal", 0, self.did, GROUNDS, "")

    def test_only_one_open_appeal_per_decision(self):
        self.file()
        with self.assertRaises(PaymentRejected):
            self.file()

    def test_filing_window_closes(self):
        CLOCK.advance(APPEAL_WINDOW + 1)
        with self.assertRaises(PaymentRejected):
            self.file()

    def test_evidence_is_optional(self):
        set_caller(MEMBER)
        a = jl(call_payable(self.c, "file_appeal", 5 * GEN, self.did, GROUNDS))
        self.assertEqual(a["evidence"], [])

    def test_add_evidence_by_both_sides_only(self):
        a = jl(self.file())["appeal_id"]
        set_caller(MEMBER)
        self.c.add_evidence(a, "A second piece of evidence from the member")
        set_caller(STEWARD)
        self.c.add_evidence(a, "The warning log entry from last month")
        by = [e["by"] for e in jl(self.c.get_appeal(a))["evidence"]]
        self.assertEqual(by, ["appellant", "appellant", "steward"])
        set_caller(STRANGER)
        expect_error(self, self.c.add_evidence, a, "I have an opinion about this case")
        set_caller(MEMBER)
        expect_error(self, self.c.add_evidence, a, "short")

    def test_evidence_cap_per_side(self):
        a = jl(self.file())["appeal_id"]
        set_caller(MEMBER)
        for i in range(5):
            self.c.add_evidence(a, f"Extra evidence item number {i} for the case")
        expect_error(self, self.c.add_evidence, a, "One more than the cap allows")
        self.assertNotIn("add_evidence", jl(self.c.get_appeal_actions(a, MEMBER, CLOCK.now.isoformat()))["actions"])

    def test_response_by_steward_only_and_once(self):
        a = jl(self.file())["appeal_id"]
        set_caller(MEMBER)
        expect_error(self, self.c.respond_to_appeal, a, "I would like to respond to myself here")
        set_caller(STEWARD)
        self.c.respond_to_appeal(a, "The member was warned twice in direct messages before the ban.")
        expect_error(self, self.c.respond_to_appeal, a, "A second response in the same round")
        self.assertEqual(jl(self.c.get_appeal(a))["responded_round"], 1)

    def test_response_after_deadline_refused(self):
        a = jl(self.file())["appeal_id"]
        after_response_window(self.c)
        set_caller(STEWARD)
        expect_error(self, self.c.respond_to_appeal, a, "Too late to respond to this appeal now")

    def test_concession_overturns_and_refunds_everything(self):
        a = jl(self.file())["appeal_id"]
        set_caller(MEMBER)
        expect_error(self, self.c.concede_appeal, a, "I concede my own appeal")
        set_caller(STEWARD)
        out = jl(self.c.concede_appeal(a, "On review no written warning was ever sent."))
        self.assertEqual(out["final_outcome"], "OVERTURNED")
        self.assertEqual(out["final_source"], "concession")
        self.assertEqual(pending(self.c, MEMBER), 5 * GEN)
        self.assertEqual(pending(self.c, STEWARD), 0)
        self.assertEqual(jl(self.c.get_decision(self.did))["status"], "overturned")
        self.assertEqual(jl(self.c.get_profile(MEMBER))["conceded"], 1)


if __name__ == "__main__":
    unittest.main()
