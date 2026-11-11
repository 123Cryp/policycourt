import json
import unittest
from _bootstrap import *


def actions(c, aid, who):
    return jl(c.get_appeal_actions(aid, who, CLOCK.now.isoformat()))["actions"]


class ActionMatrixTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()
        self.cid = register(self.c)
        self.did = decide(self.c, self.cid)

    def test_decision_actions_per_role(self):
        self.assertEqual(jl(self.c.get_decision_actions(self.did, MEMBER, CLOCK.now.isoformat()))["actions"], ["file_appeal"])
        self.assertEqual(jl(self.c.get_decision_actions(self.did, MEMBER, CLOCK.now.isoformat()))["role"], "subject")
        self.assertEqual(jl(self.c.get_decision_actions(self.did, STEWARD, CLOCK.now.isoformat()))["actions"], [])
        self.assertEqual(jl(self.c.get_decision_actions(self.did, STEWARD, CLOCK.now.isoformat()))["role"], "steward")
        self.assertEqual(jl(self.c.get_decision_actions(self.did, STRANGER, CLOCK.now.isoformat()))["role"], "observer")
        CLOCK.advance(APPEAL_WINDOW + 1)
        self.assertEqual(jl(self.c.get_decision_actions(self.did, MEMBER, CLOCK.now.isoformat()))["actions"], [])

    def test_filed_appeal_actions(self):
        aid = appeal(self.c, self.did)
        self.assertEqual(sorted(actions(self.c, aid, MEMBER)), ["add_evidence"])
        self.assertEqual(sorted(actions(self.c, aid, STEWARD)), ["add_evidence", "concede_appeal", "respond_to_appeal"])
        self.assertEqual(actions(self.c, aid, STRANGER), [])
        after_response_window(self.c)
        self.assertIn("rule_appeal", actions(self.c, aid, STRANGER))
        self.assertNotIn("respond_to_appeal", actions(self.c, aid, STEWARD))

    def test_every_listed_action_is_actually_allowed_and_vice_versa_for_rule(self):
        aid = appeal(self.c, self.did)
        set_caller(STEWARD)
        self.c.respond_to_appeal(aid, "The member was warned twice in direct messages before the ban.")
        self.assertNotIn("rule_appeal", actions(self.c, aid, STRANGER))
        self.assertNotIn("rule_appeal", actions(self.c, aid, STEWARD))
        self.assertIn("rule_appeal", actions(self.c, aid, MEMBER))
        rule(self.c, aid, UPHOLD, caller=MEMBER)
        self.assertEqual(sorted(actions(self.c, aid, MEMBER)), ["accept_ruling", "appeal_again"])
        self.assertEqual(actions(self.c, aid, STEWARD), [])
        CLOCK.advance(APPEAL_WINDOW + 1)
        self.assertEqual(actions(self.c, aid, MEMBER), ["finalize_appeal"])

    def test_remand_actions(self):
        aid = appeal(self.c, self.did)
        after_response_window(self.c)
        rule(self.c, aid, REMAND)
        self.assertEqual(actions(self.c, aid, STEWARD), ["review_remand"])
        self.assertEqual(actions(self.c, aid, MEMBER), [])
        set_caller(STEWARD)
        self.c.review_remand(aid, "REAFFIRM", "Reviewed the log again and the ban stands.")
        self.assertEqual(sorted(actions(self.c, aid, MEMBER)), ["accept_ruling", "appeal_again"])

    def test_final_appeal_has_no_actions(self):
        aid = appeal(self.c, self.did)
        set_caller(STEWARD)
        self.c.concede_appeal(aid, "On review no written warning was sent.")
        for who in (MEMBER, STEWARD, STRANGER):
            self.assertEqual(actions(self.c, aid, who), [])


class ViewClockTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()
        self.cid = register(self.c)
        self.did = decide(self.c, self.cid)
        self.aid = appeal(self.c, self.did)

    def test_views_never_read_the_wall_clock(self):
        original = PolicyCourt.__dict__["_now_utc"]
        def boom():
            raise AssertionError("a view read the clock")
        PolicyCourt._now_utc = staticmethod(boom)
        try:
            when = CLOCK.now.isoformat()
            jl(self.c.get_appeal_actions(self.aid, MEMBER, when))
            jl(self.c.get_decision_actions(self.did, MEMBER, when))
            for fn, args in [(self.c.get_stats, ()), (self.c.get_profile, (MEMBER,)), (self.c.list_appeals, ("", 0, 5)),
                             (self.c.list_decisions, ("", 0, 5)), (self.c.list_charters, (0, 5)), (self.c.get_verdict, (self.aid,)),
                             (self.c.get_charter_stats, (self.cid,)), (self.c.get_rules, ())]:
                fn(*args)
        finally:
            PolicyCourt._now_utc = original

    def test_as_of_drives_deadlines(self):
        early = CLOCK.now.isoformat()
        late = (CLOCK.now + __import__("datetime").timedelta(seconds=RESP_WINDOW + 1)).isoformat()
        self.assertNotIn("rule_appeal", jl(self.c.get_appeal_actions(self.aid, STRANGER, early))["actions"])
        self.assertIn("rule_appeal", jl(self.c.get_appeal_actions(self.aid, STRANGER, late))["actions"])

    def test_browser_style_and_z_times_are_accepted(self):
        for stamp in ["2026-11-01T12:00:00Z", "2026-11-01T12:00:00+00:00", "2026-11-01T12:00:00"]:
            jl(self.c.get_appeal_actions(self.aid, MEMBER, stamp))

    def test_missing_or_bad_as_of_gives_a_clear_error(self):
        msg = expect_error(self, self.c.get_appeal_actions, self.aid, MEMBER, "")
        self.assertIn("as_of", msg)
        msg = expect_error(self, self.c.get_decision_actions, self.did, MEMBER, "yesterday")
        self.assertIn("ISO-8601", msg)


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_stats_and_lists(self):
        self.assertEqual(jl(self.c.get_stats()), {"charters": 0, "decisions": 0, "appeals": 0, "final": 0, "open": 0})
        cid, did, aid = ruled_case(self.c, OVERTURN)
        cid2 = register(self.c, steward=MEMBER2, name="Pixel Guild")
        did2 = decide(self.c, cid2, steward=MEMBER2, subject=STRANGER)
        aid2 = appeal(self.c, did2, who=STRANGER)
        self.assertEqual(jl(self.c.get_stats()), {"charters": 2, "decisions": 2, "appeals": 2, "final": 1, "open": 1})
        self.assertEqual([r["appeal_id"] for r in jl(self.c.list_appeals("", 0, 10))["rows"]], [aid2, aid])
        self.assertEqual([r["appeal_id"] for r in jl(self.c.list_appeals("final", 0, 10))["rows"]], [aid])
        self.assertEqual([r["appeal_id"] for r in jl(self.c.list_appeals("filed", 0, 10))["rows"]], [aid2])
        row = jl(self.c.list_appeals("final", 0, 10))["rows"][0]
        self.assertEqual((row["latest_outcome"], row["final_outcome"]), ("OVERTURNED", "OVERTURNED"))

    def test_case_summaries_carry_decision_and_next_deadline(self):
        cid, did, aid = full_case(self.c)
        row = jl(self.c.list_appeals("", 0, 5))["rows"][0]
        self.assertEqual((row["decision_kind"], row["next_deadline_kind"]), ("BAN", "reply"))
        self.assertEqual(row["next_deadline"], jl(self.c.get_appeal(aid))["response_deadline"])
        self.assertIn("spam", row["decision_summary"])
        after_response_window(self.c)
        rule(self.c, aid, REMAND)
        row = jl(self.c.list_appeals("", 0, 5))["rows"][0]
        self.assertEqual(row["next_deadline_kind"], "review")
        set_caller(STEWARD)
        self.c.review_remand(aid, "REAFFIRM", "Reviewed the log again and the ban stands.")
        row = jl(self.c.list_appeals("", 0, 5))["rows"][0]
        self.assertEqual(row["next_deadline_kind"], "appeal")
        set_caller(MEMBER)
        self.c.accept_ruling(aid)
        row = jl(self.c.list_appeals("", 0, 5))["rows"][0]
        self.assertEqual((row["next_deadline"], row["next_deadline_kind"]), ("", ""))

    def test_list_limits_and_offsets(self):
        cid = register(self.c)
        for i in range(5):
            decide(self.c, cid, subject="0x" + hex(0x100 + i)[2:].rjust(40, "0"))
        page = jl(self.c.list_decisions("", 0, 2))
        self.assertEqual(([r["decision_id"] for r in page["rows"]], page["more"]), (["4", "3"], True))
        page = jl(self.c.list_decisions("", 4, 2))
        self.assertEqual(([r["decision_id"] for r in page["rows"]], page["more"]), (["0"], False))
        self.assertEqual(len(jl(self.c.list_decisions("", 0, 1000))["rows"]), 5)

    def test_profile_roles_and_money(self):
        cid, did, aid = ruled_case(self.c, UPHOLD)
        set_caller(MEMBER)
        self.c.accept_ruling(aid)
        p = jl(self.c.get_profile(MEMBER))
        self.assertEqual((p["appeals_filed"], p["upheld"], p["overturned"]), (1, 1, 0))
        self.assertEqual(p["staked_wei"], str(5 * GEN))
        self.assertEqual(int(p["returned_wei"]) + int(p["forfeited_wei"]), 5 * GEN)
        self.assertEqual(p["withdrawable_wei"], str(pending(self.c, MEMBER)))
        s = jl(self.c.get_profile(STEWARD))
        self.assertEqual((s["charters"], s["decisions_recorded"]), (1, 1))
        empty = jl(self.c.get_profile(STRANGER))
        self.assertEqual((empty["appeals_filed"], empty["withdrawable_wei"]), (0, "0"))
        self.assertEqual(self.c.get_pending_withdrawal(STRANGER), "0")

    def test_status_counters_follow_every_transition(self):
        cid, did, aid = full_case(self.c)
        st = lambda: jl(self.c.get_charter_stats(cid))["decisions_by_status"]
        self.assertEqual(st(), {"under_appeal": 1})
        after_response_window(self.c)
        rule(self.c, aid, REMAND)
        set_caller(STEWARD)
        self.c.review_remand(aid, "REAFFIRM", "Reviewed the log again and the ban stands.")
        set_caller(MEMBER)
        self.c.accept_ruling(aid)
        self.assertEqual(st(), {"reaffirmed": 1})
        decide(self.c, cid, subject=MEMBER2)
        self.assertEqual(st(), {"reaffirmed": 1, "in_force": 1})
        self.assertEqual(jl(self.c.get_charter_stats(cid))["decisions"], 2)

    def test_void_moves_the_counter_back_to_in_force(self):
        cid, did, aid = full_case(self.c)
        CLOCK.advance(RESP_WINDOW + 3 * DAY + 1)
        set_caller(STRANGER)
        self.c.void_stalled_appeal(aid)
        self.assertEqual(jl(self.c.get_charter_stats(cid))["decisions_by_status"], {"in_force": 1})

    def test_paging_reads_only_one_record_past_the_page(self):
        cid = register(self.c)
        for i in range(8):
            decide(self.c, cid, subject="0x" + hex(0x200 + i)[2:].rjust(40, "0"))
        reads = []
        real = self.c.decisions
        class Spy(dict):
            def __getitem__(s, k):
                reads.append(k)
                return real[k]
            def __contains__(s, k):
                return k in real
        self.c.decisions = Spy()
        try:
            page = jl(self.c.list_decisions("", 0, 2))
        finally:
            self.c.decisions = real
        self.assertEqual((len(page["rows"]), page["more"]), (2, True))
        self.assertLessEqual(len(reads), 3)
        reads.clear()
        self.c.decisions = Spy()
        try:
            page = jl(self.c.list_decisions(cid, 0, 2))
        finally:
            self.c.decisions = real
        self.assertEqual((len(page["rows"]), page["more"]), (2, True))
        self.assertEqual(len(reads), 3)

    def test_writes_fail_closed_without_a_transaction_clock(self):
        import importlib.util
        import _bootstrap
        spec = importlib.util.spec_from_file_location("pc_fresh_clock", _bootstrap.CONTRACT_PATH)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        try:
            PolicyCourt._now_utc = fresh.PolicyCourt.__dict__["_now_utc"]
            set_caller(STEWARD)
            msg = expect_error(self, self.c.register_charter, "Open Garden DAO", ARTICLES, 5, RESP_WINDOW, APPEAL_WINDOW, 2000, 7000)
            self.assertIn("timestamp", msg)
        finally:
            PolicyCourt._now_utc = staticmethod(lambda: CLOCK.now)

    def test_charter_stats_group_decisions_by_status(self):
        cid, did, aid = ruled_case(self.c, OVERTURN)
        decide(self.c, cid, subject=MEMBER2)
        self.assertEqual(jl(self.c.get_charter_stats(cid))["decisions_by_status"], {"overturned": 1, "in_force": 1})

    def test_rules_view_is_static_and_complete(self):
        r = jl(self.c.get_rules())
        self.assertEqual(r["outcomes"], ["UPHELD", "OVERTURNED", "REMANDED"])
        self.assertEqual(r["lenses"], ["text", "proportion", "process"])
        self.assertIn("BAN", r["decision_kinds"])

    def test_views_reject_unknown_ids(self):
        for fn, args in [(self.c.get_decision, ("1",)), (self.c.get_appeal, ("1",)), (self.c.get_verdict, ("1",)),
                         (self.c.get_charter_stats, ("1",)), (self.c.get_appeal_actions, ("1", MEMBER, "2026-11-01T12:00:00Z")),
                         (self.c.get_decision_actions, ("1", MEMBER, "2026-11-01T12:00:00Z"))]:
            expect_error(self, fn, *args)

    def test_get_verdict_before_ruling_has_no_verdict(self):
        cid, did, aid = full_case(self.c)
        v = jl(self.c.get_verdict(aid))
        self.assertIsNone(v["verdict"])
        self.assertEqual(v["cited_article_texts"], [])

    def test_every_view_returns_json_text(self):
        cid, did, aid = ruled_case(self.c, REMAND)
        for text in [self.c.get_charter(cid), self.c.list_charters(0, 5), self.c.get_decision(did), self.c.list_decisions("", 0, 5),
                     self.c.get_appeal(aid), self.c.list_appeals("", 0, 5), self.c.get_verdict(aid), self.c.get_stats(),
                     self.c.get_profile(MEMBER), self.c.get_charter_stats(cid), self.c.get_rules()]:
            json.loads(text)


if __name__ == "__main__":
    unittest.main()
