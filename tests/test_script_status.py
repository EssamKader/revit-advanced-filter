# -*- coding: utf-8 -*-
"""Mock verification of the status label / Isolate enablement in script.py."""
import types
import unittest

from test_script_search import load_script, rec


@unittest.skipUnless(hasattr(types, "SimpleNamespace"), "needs CPython 3")
class ScriptStatusTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_script()
        records = [rec(1, "Walls", "Basic Wall", "Generic 200"),
                   rec(2, "Walls", "Basic Wall", "Generic 300"),
                   rec(3, "Doors", "Single", "D1"),
                   rec(4, "Doors", "Single", "D2", level="L2")]
        records[0].in_active_view = True
        records[1].in_active_view = False
        records[2].in_active_view = False
        records[3].in_active_view = False
        self.w = self.ns["FilterWindow"]("x.xaml", records, {"L1": 0.0, "L2": 4.0})

    def box(self, name):
        return [b for n, b in self.w._boxes if n.name == name][0]

    def text(self):
        return self.w.status_text.Text

    def test_startup_nothing_selected(self):
        self.assertEqual(self.text(), "Nothing selected")
        self.assertEqual(self.w.status_text.Foreground, self.w._muted_brush)
        self.assertFalse(self.w.isolate_button.IsEnabled)

    def test_click_updates(self):
        self.w._on_click(self.box("Generic 200"), None)
        self.assertEqual(self.text(), u"1 matched · 1 in active view")
        self.assertEqual(self.w.status_text.Foreground, self.w._fg_brush)
        self.assertTrue(self.w.isolate_button.IsEnabled)
        self.w._on_click(self.box("Walls"), None)
        self.assertEqual(self.text(), u"2 matched · 1 in active view")

    def test_disabled_when_none_in_view(self):
        self.w._on_click(self.box("Generic 300"), None)
        self.assertEqual(self.text(), u"1 matched · 0 in active view")
        self.assertFalse(self.w.isolate_button.IsEnabled)

    def test_uncheck_returns_to_nothing(self):
        self.w._on_click(self.box("Generic 200"), None)
        self.w._on_click(self.box("Generic 200"), None)
        self.assertEqual(self.text(), "Nothing selected")
        self.assertFalse(self.w.isolate_button.IsEnabled)

    def test_level_change_updates(self):
        self.w._on_click(self.box("Doors"), None)
        self.assertEqual(self.text(), u"2 matched · 0 in active view")
        self.w._level_boxes[1].IsChecked = False  # untick L2
        self.w._on_level_toggle(None, None)
        self.assertEqual(self.text(), u"1 matched · 0 in active view")

    def test_search_does_not_change_status(self):
        self.w._on_click(self.box("Walls"), None)
        before = self.text()
        self.w.search_box.Text = "door"
        self.w._on_search_tick(None, None)
        self.assertEqual(self.text(), before)

    def test_isolate_stores_counts(self):
        self.w._on_click(self.box("Walls"), None)
        self.w.Close = lambda: None
        self.w.isolate_click(None, None)
        self.assertEqual(self.w.counts, (2, 1))
        self.assertEqual(self.w.ids_to_isolate, [1])
        self.assertIsNotNone(self.ns["core"].hidden_notice(*self.w.counts))

    def _run_main(self, fail, counts):
        ns = self.ns
        calls = []

        class FakeView(object):
            def IsolateElementsTemporary(self, ids):
                if fail:
                    raise RuntimeError("boom")

        class FakeTxn(object):
            started = False

            def __init__(self, doc, name):
                pass

            def Start(self):
                FakeTxn.started = True

            def Commit(self):
                pass

            def HasStarted(self):
                return FakeTxn.started

            def RollBack(self):
                calls.append("rollback")

        class FakeWindow(object):
            ids_to_isolate = [1]

            def __init__(self, *a):
                self.counts = counts

            def ShowDialog(self):
                pass

        class FakeList(list):
            def Add(self, x):
                self.append(x)

        view = FakeView()
        ns["doc"] = types.SimpleNamespace(ActiveView=view)
        ns["DB"] = types.SimpleNamespace(ElementId=lambda i: i,
                                         Transaction=FakeTxn)
        ns["List"] = types.SimpleNamespace(__getitem__=None)
        ns["List"] = type("L", (), {"__getitem__": lambda self, k: FakeList})()
        ns["revit_adapter"] = types.SimpleNamespace(
            view_isolate_problem=lambda v: None,
            collect_records=lambda d, v: ([1], {}))
        ns["script"] = types.SimpleNamespace(get_bundle_file=lambda n: n)
        ns["FilterWindow"] = FakeWindow
        ns["forms"].alert = lambda *a, **k: calls.append("alert")
        ns["notify"] = lambda m: calls.append("notify")
        ns["main"]()
        return calls

    def test_notice_after_successful_isolate(self):
        self.assertEqual(self._run_main(False, (3, 1)), ["notify"])

    def test_no_notice_when_all_isolated(self):
        self.assertEqual(self._run_main(False, (2, 2)), [])

    def test_no_notice_after_failed_isolate(self):
        calls = self._run_main(True, (3, 1))
        self.assertNotIn("notify", calls)
        self.assertIn("rollback", calls)
        self.assertIn("alert", calls)

    def test_notify_fallback_chain(self):
        forms = self.ns["forms"]
        calls = []
        forms.alert = lambda *a, **k: calls.append(("alert", k))
        forms.toast = lambda *a, **k: calls.append("toast")
        self.ns["notify"]("m")
        self.assertEqual(calls, ["toast"])
        del calls[:]
        def boom(*a, **k):
            raise RuntimeError("x")
        forms.toast = boom
        forms.show_balloon = lambda h, t: calls.append("balloon")
        self.ns["notify"]("m")
        self.assertEqual(calls, ["balloon"])
        del calls[:]
        forms.show_balloon = boom
        self.ns["notify"]("m")
        self.assertEqual(calls[0][0], "alert")
        self.assertIs(calls[0][1].get("warn_icon"), False)


if __name__ == "__main__":
    unittest.main()
