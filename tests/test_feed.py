"""Run with:  python -m unittest discover tests"""
import os
import tempfile
import unittest

# keep tests away from the user's real ~/MorningMarketBrief folder
os.environ["MMB_HOME"] = tempfile.mkdtemp(prefix="itd-test-")
from datetime import date
from pathlib import Path

from mmb_feed import engine, feed

FIX = Path(__file__).parent / "fixtures"


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = engine.build("2026-10-01", "2027-03-31")
        cls.by = {}
        for e in cls.ev:
            cls.by.setdefault(e.cat, []).append(e)

    def test_h2_gsec_total_matches_rbi_calendar(self):
        auctions = [e for e in self.by["gsec"] if e.title.startswith("G-Sec auction")]
        self.assertEqual(len(auctions), 23)
        seed, _, _ = engine.load_inputs()
        self.assertEqual(sum(sum(w["alloc"].values()) for w in seed["gsec_weeks"]), 786000)

    def test_gandhi_jayanti_week_flagged(self):
        w1 = [e for e in self.by["gsec"] if e.date == "2026-10-02"]
        self.assertTrue(w1 and w1[0].flags)

    def test_tbill_quarter_total(self):
        tb = [e for e in self.by["tbill"] if e.amount_cr]
        self.assertEqual(sum(e.amount_cr for e in tb), 299000)

    def test_christmas_auction_flagged(self):
        xmas = [e for e in self.by["gsec"] if e.date == "2026-12-25"]
        self.assertTrue(xmas and xmas[0].flags)

    def test_weekend_roll(self):
        cal = engine.Cal({"2026-12-25": "Christmas"})
        self.assertEqual(cal.next_working(date(2026, 12, 12)), date(2026, 12, 14))
        self.assertEqual(cal.prev_working(date(2026, 11, 15)), date(2026, 11, 13))
        self.assertEqual(cal.after(date(2026, 12, 24)), date(2026, 12, 28))

    def test_switch_third_monday(self):
        sw = [e.date for e in self.by["mpc"] if "Switch" in e.title]
        self.assertIn("2026-11-16", sw)
        self.assertIn("2027-03-15", sw)

    def test_indian_number_format(self):
        self.assertEqual(engine.fmt_cr(786000), "₹7,86,000 cr")
        self.assertEqual(engine.fmt_cr(23000), "₹23,000 cr")


class FeedTests(unittest.TestCase):
    def test_confirmation_from_fixture(self):
        ev = engine.build("2026-10-28", "2026-11-10")
        log = feed.confirm(ev, feed.parse((FIX / "title_only_sample.xml").read_bytes()))
        g = next(e for e in ev if e.date == "2026-11-06" and e.title.startswith("G-Sec auction"))
        t = next(e for e in ev if e.date == "2026-11-04" and e.cat == "tbill")
        s = next(e for e in ev if e.date == "2026-11-03" and e.cat == "sdl")
        self.assertEqual(g.state, "notified")
        self.assertEqual(t.state, "done")
        self.assertEqual(s.state, "notified")
        self.assertTrue(all("Money Market" not in line for line in log))


class RbiParseTests(unittest.TestCase):
    """Synthetic feed: invented numbers in RBI's table layout (no RBI content in the repo)."""

    @classmethod
    def setUpClass(cls):
        from mmb_feed import rbi_parse
        items = feed.parse((FIX / "synthetic_feed.xml").read_bytes())
        cls.recs = {r["data"]["kind"]: r for r in map(rbi_parse.parse_item, items) if r["data"]}

    def test_gsec_result(self):
        x = self.recs["gsec_result"]["data"]["items"]
        self.assertEqual([i["cutoff_yield"] for i in x], [7.10, 7.65])
        self.assertEqual([i["way"] for i in x], [7.095, 7.64])
        self.assertEqual([i["bid_cover"] for i in x], [2.5, 2.5])
        self.assertEqual(x[1]["devolvement"], "NIL")

    def test_sdl_notice(self):
        d = self.recs["sdl_notice"]["data"]
        self.assertEqual(d["total_cr"], 6000)
        self.assertEqual(d["states"], {"State A": 3000, "State B": 2500, "State C": 500})
        self.assertEqual(d["n_securities"], 4)
        self.assertEqual(d["auction"], "2026-11-10")

    def test_tbill_notice(self):
        d = self.recs["tbill_notice"]["data"]
        self.assertEqual((d["total_cr"], d["auction"], d["settle"]), (23000, "2026-11-11", "2026-11-12"))
        self.assertEqual(d["split"], {"91D": 8000, "182D": 8000, "364D": 7000})

    def test_mmo(self):
        d = self.recs["mmo"]["data"]
        self.assertEqual(d["net_liquidity_cr"], -95000)
        self.assertEqual(d["sdf_cr"], 102000)
        self.assertEqual(d["msf_cr"], 10500)
        self.assertEqual(d["call_war"], 5.50)
        self.assertEqual(d["durable_liquidity_cr"], 500000)

    def test_wss(self):
        d = self.recs["wss"]["data"]
        self.assertEqual((d["fx_total_usd_mn"], d["fx_week_chg_usd_mn"], d["fx_as_on"]), (700000, 1000, "2026-10-30"))

    def test_sgb(self):
        self.assertEqual(self.recs["sgb"]["data"]["price"], 12345)

    def test_unknown_release_gives_no_numbers(self):
        from mmb_feed import rbi_parse
        r = rbi_parse.parse_item({"title": "Lending and Deposit Rates", "html": "<table><tr><td>9.99</td></tr></table>"})
        self.assertIsNone(r["data"])

    def test_notice_amount_lands_on_calendar(self):
        from mmb_feed import rbi_parse
        ev = engine.build("2026-11-05", "2026-11-15")
        recs = [rbi_parse.parse_item(i) for i in feed.parse((FIX / "synthetic_feed.xml").read_bytes())]
        feed.apply_notices(ev, recs)
        sdl = next(e for e in ev if e.cat == "sdl" and e.date == "2026-11-10")
        self.assertEqual((sdl.amount_cr, sdl.status), (6000, "V"))


class PackagingTests(unittest.TestCase):
    def test_user_copy_overrides_default(self):
        from mmb_feed import paths
        self.assertEqual(paths.data_file("holidays_mumbai.json").parent, paths.PKG_DATA)
        paths.init_user_data()
        self.assertEqual(paths.data_file("holidays_mumbai.json").parent, paths.home() / "data")

    def test_windows_task_xml(self):
        import xml.dom.minidom
        from mmb_feed import schedule
        x = schedule.windows_xml("09:15")
        xml.dom.minidom.parseString(x.replace('encoding="UTF-16"', 'encoding="UTF-8"').encode())
        self.assertIn("T09:15:00", x)
        self.assertIn("<StartWhenAvailable>true</StartWhenAvailable>", x)
        self.assertIn("-m mmb_feed digest --open", x)

    def test_cron_line(self):
        from mmb_feed import schedule
        self.assertTrue(schedule.cron_line("09:15").startswith("15 9 * * 1-5 "))

    def test_digest_end_to_end(self):
        from mmb_feed.__main__ import run_digest
        from datetime import date
        p = run_digest(date(2026, 11, 9), feed_file=FIX / "synthetic_feed.xml", quiet=True)
        html = p.read_text(encoding="utf-8")
        self.assertIn("7.1000%", html)
        self.assertIn("not affiliated", html)


if __name__ == "__main__":
    unittest.main()
