from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _support import PLUGIN_ROOT, load_module


class ReleasePackagingTests(unittest.TestCase):
    def test_standalone_skill_is_renamed_and_self_contained(self):
        release = load_module("package_release", PLUGIN_ROOT.parent)
        with tempfile.TemporaryDirectory() as temporary:
            folder = release.build_standalone(Path(temporary))
            self.assertEqual(folder.name, "whetstone-learn")
            self.assertEqual(release.check_standalone(folder), [])
            head = (folder / "SKILL.md").read_text(encoding="utf-8")[:1200]
            self.assertIn("\nname: whetstone-learn\n", head)
            self.assertIn("description: " + release.STANDALONE_DESCRIPTION, head)
            self.assertTrue((folder / "LICENSE").is_file() and (folder / "README.md").is_file())
            self.assertIn(release.version(), (folder / "README.md").read_text(encoding="utf-8"))
            plan_template = (folder / "assets" / "learning-plan-template.md").read_text(encoding="utf-8")
            self.assertIn("/whetstone-learn 学习", plan_template)
            self.assertEqual(sorted(p.name for p in (folder / "scripts").glob("*.py")), sorted(p.name for p in (PLUGIN_ROOT / "skills" / "learn" / "scripts").glob("*.py")))

