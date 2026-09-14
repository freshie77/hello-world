import json, pathlib, unittest, reddit_risk
HERE=pathlib.Path(__file__).parent

class Tests(unittest.TestCase):
    def test_sample_is_high_risk(self):
        f=json.loads((HERE/"sample_activity.json").read_text())
        r=reddit_risk.score_account(f["account"],f["activity"],f["now_utc"])
        self.assertGreaterEqual(r["risk_score"],75)
        codes={x["code"] for x in r["findings"]}
        self.assertIn("geographic_inconsistency",codes)
        self.assertIn("repeated_crosspost",codes)
        self.assertIn("promo_destination",codes)

    def test_normal_account_scores_zero(self):
        account={"name":"normal","created_utc":1600000000,"link_karma":500,"comment_karma":2500}
        activity=[{"subreddit":"gardening","body":"My tomatoes finally ripened.","created_utc":1789000000}]
        self.assertEqual(reddit_risk.score_account(account,activity,1789340400)["risk_score"],0)

if __name__=="__main__":
    unittest.main()
