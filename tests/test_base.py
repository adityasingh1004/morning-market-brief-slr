"""Checks on the base report, the base builder and the validator.  python -m unittest discover tests"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["MMB_HOME"] = tempfile.mkdtemp(prefix="mmb-test-")


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mmb = load("mmb")
make_base = load("make_base")
BASE = (ROOT / "report" / "base_report.html").read_text(encoding="utf-8")


class BaseReportTests(unittest.TestCase):
    def test_base_validates(self):
        self.assertEqual(mmb.validate(BASE), [])

    def test_attribution_present(self):
        self.assertIn('id="mmb-attribution"', BASE)
        self.assertIn("Morning Market Brief – SLR · by Aditya Kumar Singh", BASE)
        self.assertNotIn("Prepared for", BASE)

    def test_builder_is_repeatable(self):
        self.assertEqual(make_base.make_base(BASE), BASE)

    def test_media_series_empty_official_kept(self):
        a = BASE.find("const MKT=[")
        block = BASE[a:BASE.find("\n];", a)]
        for line in block.splitlines():
            if 'st:"s"' in line:
                self.assertIn("pts:[]", line)
            if 'src:"mUst"' in line:
                self.assertNotIn("pts:[]", line)


class ValidatorTests(unittest.TestCase):
    def test_removing_attribution_fails(self):
        import re
        broken = re.sub(r'<footer id="mmb-attribution".*?</footer>', "", BASE, flags=re.S)
        self.assertTrue(any("Attribution" in e for e in mmb.validate(broken)))

    def test_unknown_tag_fails(self):
        broken = BASE.replace('st:"u"', 'st:"maybe"', 1)
        self.assertTrue(any("status tags" in e for e in mmb.validate(broken)))

    def test_undefined_source_fails(self):
        broken = BASE.replace('src:"mUst"', 'src:"nosuchsource"', 1)
        self.assertTrue(any("not defined" in e for e in mmb.validate(broken)))

    def test_future_date_fails(self):
        broken = BASE.replace('const DATA_AS_OF="', 'const DATA_AS_OF="2099-01-01";const X="', 1)
        self.assertTrue(any("future" in e for e in mmb.validate(broken)))

    def test_init_backup_restore(self):
        mmb.cmd_init()
        self.assertTrue(mmb.report_path().exists())
        mmb.cmd_backup()
        mmb.report_path().write_text("broken", encoding="utf-8")
        mmb.cmd_restore()
        self.assertEqual(mmb.validate(mmb.report_path().read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
