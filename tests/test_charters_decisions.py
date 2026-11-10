import unittest
from _bootstrap import *


class CharterTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()

    def test_register_stores_numbered_articles_and_settings(self):
        cid = register(self.c)
        ch = jl(self.c.get_charter(cid))
        self.assertEqual(len(ch["articles"]), 4)
        self.assertEqual(ch["steward"], STEWARD)
        self.assertEqual(ch["min_stake"], str(5 * GEN))
        self.assertEqual(ch["response_window_secs"], RESP_WINDOW)

    def test_several_charters_get_distinct_ids(self):
        a = register(self.c)
        b = register(self.c, steward=MEMBER2, name="Pixel Guild")
        self.assertNotEqual(a, b)
        page = jl(self.c.list_charters(0, 10))
        self.assertEqual(page["total"], 2)
        self.assertEqual(page["rows"][0]["name"], "Pixel Guild")

    def test_newlines_also_separate_articles(self):
        cid = register(self.c, articles_text="First rule is long enough\nSecond rule is long enough")
        self.assertEqual(len(jl(self.c.get_charter(cid))["articles"]), 2)

    def test_rejects_bad_input(self):
        set_caller(STEWARD)
        bad = [
            dict(name="x"), dict(articles_text="only one article here"), dict(articles_text="short|tiny"),
            dict(min_stake_gen=0), dict(min_stake_gen=10 ** 9), dict(response_window_secs=5), dict(appeal_window_secs=10 ** 9),
            dict(upheld_refund_bps=6000), dict(upheld_refund_bps=True), dict(remand_refund_bps=True), dict(remand_refund_bps=4000), dict(remand_refund_bps=10001),
            dict(articles_text="|".join(["Article text number %02d is here" % i for i in range(13)])),
        ]
        for over in bad:
            args = dict(name="Open Garden DAO", articles_text=ARTICLES, min_stake_gen=5, response_window_secs=RESP_WINDOW,
                        appeal_window_secs=APPEAL_WINDOW)
            args.update(over)
            with self.assertRaises(gl.vm.UserError, msg=str(over)):
                self.c.register_charter(**args)
        self.assertEqual(int(self.c.charter_count), 0)

    def test_unknown_charter(self):
        expect_error(self, self.c.get_charter, "9")


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.c = make_contract()
        self.cid = register(self.c)

    def test_steward_records_decision_with_deadline(self):
        did = decide(self.c, self.cid)
        d = jl(self.c.get_decision(did))
        self.assertEqual(d["status"], "in_force")
        self.assertEqual(d["subject"], MEMBER)
        self.assertEqual(d["cited_articles"], [2])
        self.assertEqual(d["filing_deadline"], jl(self.c.get_decision(did))["filing_deadline"])
        self.assertEqual(jl(self.c.get_charter(self.cid))["decision_ids"], [did])

    def test_only_steward_can_record(self):
        set_caller(STRANGER)
        expect_error(self, self.c.record_decision, self.cid, MEMBER, "BAN", "Banned for spam in channel", "Spam repeated four times", "2")

    def test_validation(self):
        set_caller(STEWARD)
        s, r = "Banned for spam in channel", "Spam repeated four times"
        for args in [
            (self.cid, STEWARD, "BAN", s, r, "2"),
            (self.cid, "not-an-address", "BAN", s, r, "2"),
            (self.cid, MEMBER, "EXILE", s, r, "2"),
            (self.cid, MEMBER, "BAN", "short", r, "2"),
            (self.cid, MEMBER, "BAN", s, "short", "2"),
            (self.cid, MEMBER, "BAN", s, r, ""),
            (self.cid, MEMBER, "BAN", s, r, "9"),
            (self.cid, MEMBER, "BAN", s, r, "0"),
            (self.cid, MEMBER, "BAN", s, r, "a"),
            ("77", MEMBER, "BAN", s, r, "2"),
        ]:
            with self.assertRaises(gl.vm.UserError, msg=str(args)):
                self.c.record_decision(*args)
        self.assertEqual(int(self.c.decision_count), 0)

    def test_kind_is_case_insensitive_and_refs_deduplicated(self):
        did = decide(self.c, self.cid, kind="proposal_rejection", cited="4, 4;1")
        d = jl(self.c.get_decision(did))
        self.assertEqual(d["kind"], "PROPOSAL_REJECTION")
        self.assertEqual(d["cited_articles"], [4, 1])

    def test_list_decisions_filters_by_charter(self):
        other = register(self.c, steward=MEMBER2, name="Pixel Guild")
        decide(self.c, self.cid)
        decide(self.c, other, steward=MEMBER2, subject=STRANGER)
        decide(self.c, self.cid, subject=MEMBER2)
        self.assertEqual(jl(self.c.list_decisions("", 0, 10))["total"], 3)
        rows = jl(self.c.list_decisions(self.cid, 0, 10))["rows"]
        self.assertEqual([r["decision_id"] for r in rows], ["2", "0"])
        page = jl(self.c.list_decisions(self.cid, 1, 1))
        self.assertEqual([r["decision_id"] for r in page["rows"]], ["0"])


if __name__ == "__main__":
    unittest.main()
