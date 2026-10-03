# -*- coding: utf-8 -*-
"""Mock verification: the window icon comes from the bundle icon.png."""
import types
import unittest

from test_script_search import load_script, rec


def build(ns):
    return ns["FilterWindow"]("x.xaml", [rec(1, "Walls", "Basic Wall", "G200")],
                              {"L1": 0.0}, None)


@unittest.skipUnless(hasattr(types, "SimpleNamespace"), "needs CPython 3")
class WindowIconTests(unittest.TestCase):
    def test_icon_set_from_bundle_icon_png(self):
        ns = load_script()
        asked = []
        ns["script"] = types.SimpleNamespace(
            get_bundle_file=lambda n: asked.append(n) or "C:/b/" + n)
        w = build(ns)
        self.assertEqual(asked, ["icon.png"])
        icon = w.Icon
        self.assertNotEqual(icon, "pyrevit-default")  # replaced after init
        self.assertEqual(icon.UriSource, ("uri", "C:/b/icon.png", "Absolute"))
        self.assertEqual(icon.CacheOption, "OnLoad")
        self.assertEqual(icon.calls, ["begin", "end", "freeze"])

    def test_loader_failure_keeps_window_working(self):
        ns = load_script()

        def boom(name):
            raise IOError("no icon")

        ns["script"] = types.SimpleNamespace(get_bundle_file=boom)
        w = build(ns)
        self.assertEqual(w.Icon, "pyrevit-default")
        self.assertEqual(len(w._records), 1)

    def test_bitmap_failure_keeps_window_working(self):
        ns = load_script()
        ns["script"] = types.SimpleNamespace(get_bundle_file=lambda n: n)

        class Bad(object):
            def BeginInit(self):
                raise ValueError("bad png")

        ns["BitmapImage"] = Bad
        w = build(ns)
        self.assertEqual(w.Icon, "pyrevit-default")


if __name__ == "__main__":
    unittest.main()
