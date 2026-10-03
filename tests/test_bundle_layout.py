import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "AdvancedFilter.extension")
BUTTON = os.path.join(EXT, "BIM Tools.tab", "Filter.panel", "Advanced Filter.pushbutton")


class BundleLayoutTests(unittest.TestCase):
    def test_button_bundle_files(self):
        self.assertTrue(os.path.isdir(BUTTON))
        for name in ("script.py", "ui.xaml", "bundle.yaml", "icon.png"):
            self.assertTrue(os.path.isfile(os.path.join(BUTTON, name)), name)

    def test_only_bim_tools_tab(self):
        tabs = [os.path.basename(p) for p in glob.glob(os.path.join(EXT, "*.tab"))]
        self.assertEqual(tabs, ["BIM Tools.tab"])


if __name__ == "__main__":
    unittest.main()
