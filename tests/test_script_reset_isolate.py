# -*- coding: utf-8 -*-
"""Reset isolate (US-13): script.py wiring against mock objects (no Revit)."""
import types
import unittest

import test_script_search as tss
import test_script_modeless as tm
from test_script_modeless import FakeDoc, make_uiapp


@unittest.skipUnless(hasattr(types, "SimpleNamespace"), "needs CPython 3")
class ResetIsolateTests(unittest.TestCase):
    box = tm.ModelessTests.box
    run_events = tm.ModelessTests.run_events
    txns = tm.ModelessTests.txns
    activate = tm.ModelessTests.activate

    def setUp(self):
        tss.CONFIG.__dict__.clear()
        del tss.SAVES[:]
        tm.ModelessTests.setUp(self)
        self.ns["script"].get_config = lambda: tss.CONFIG
        self.ns["script"].save_config = lambda: tss.SAVES.append(1)

    def tearDown(self):
        tss.CONFIG.__dict__.clear()
        del tss.SAVES[:]

    def click(self):
        self.w.reset_isolate_click(None, None)
        self.run_events()

    def names(self):
        return [n.name for n in self.w._items]

    def test_button_queues_request_and_raises(self):
        self.w.reset_isolate_click(None, None)
        self.assertEqual(self.event.raised, 1)
        self.assertEqual(self.w.closed_calls, 0)
        self.assertEqual(self.w.take_requests()[0].action, "reset_isolate")

    def test_button_flushes_pending_search(self):
        self.w.search_box.Text = "g200"
        self.w._on_search_changed(None, None)
        self.assertTrue(self.w._timer.running)
        self.w.reset_isolate_click(None, None)
        self.assertFalse(self.w._timer.running)
        self.assertIsNotNone(self.w._visible)

    def test_reset_when_isolated(self):
        self.isolated = True
        self.click()
        self.assertEqual(self.txns(), ["Advanced Filter: Reset isolate"])
        self.assertLess(self.log.index("disabled"), self.log.index("commit"))
        self.assertNotIn("gstart", self.log)
        self.assertNotIn("rollback", self.log)
        # view ids are re-read after the disable
        self.assertEqual(self.adapter_calls, ["disable", "ids"])
        self.assertEqual(self.w.status_text.Text, "Isolation reset")
        self.assertEqual(self.alerts, [])
        self.assertEqual(self.w.closed_calls, 0)

    def test_view_ids_rebuilt_after_reset(self):
        self.isolated = True
        self.view_ids = set([1, 2, 3])  # full view after the reset
        self.click()
        self.assertEqual(self.w._view_ids, set([1, 2, 3]))
        self.assertEqual(self.w._scope_ids, set([1, 2, 3]))
        self.assertTrue(self.records[2].in_active_view)

    def test_noop_when_not_isolated(self):
        self.isolated = False
        self.click()
        self.assertEqual(self.log, [])
        self.assertEqual(self.adapter_calls, [])
        self.assertEqual(self.w.status_text.Text, "View is not temporarily isolated")
        self.assertEqual(self.alerts, [])

    def test_unusable_view_counts_as_not_isolated(self):
        self.isolated = True
        self.problem = "Temporary isolate is not available in this view type."
        self.click()
        self.assertEqual(self.log, [])
        self.assertEqual(self.alerts, [])
        self.assertEqual(self.w.status_text.Text, "View is not temporarily isolated")

    def test_isolate_check_error_counts_as_not_isolated(self):
        def boom(v):
            raise RuntimeError("x")
        self.ns["revit_adapter"].in_temporary_isolate = boom
        self.click()
        self.assertEqual(self.log, [])
        self.assertEqual(self.w.status_text.Text, "View is not temporarily isolated")

    def test_failure_rolls_back_and_alerts(self):
        self.isolated = True

        def boom(v):
            raise RuntimeError("no")
        self.ns["revit_adapter"].disable_temporary_isolate = boom
        self.click()
        self.assertEqual(self.txns(), ["Advanced Filter: Reset isolate"])
        self.assertIn("rollback", self.log)
        self.assertNotIn("commit", self.log)
        self.assertEqual(len(self.alerts), 1)
        self.assertTrue(self.alerts[0].startswith("Reset isolate failed"))
        self.assertNotEqual(self.w.status_text.Text, "Isolation reset")
        self.assertEqual(self.adapter_calls, [])  # no rebuild after a failure

    def test_document_guard(self):
        self.isolated = True
        other = FakeDoc(self.view, "C:/b.rvt", "B")
        self.w.reset_isolate_click(None, None)
        self.event.handler.Execute(make_uiapp(other))
        self.assertEqual(self.log, [])
        self.assertEqual(self.adapter_calls, [])
        self.assertEqual(self.w.status_text.Text, tm.MSG)
        self.assertEqual(self.alerts, [tm.MSG])

    def test_no_document_alerts(self):
        self.isolated = True
        self.w.reset_isolate_click(None, None)
        self.event.handler.Execute(make_uiapp(None))
        self.assertEqual(self.alerts, ["Open a Revit project first."])
        self.assertEqual(self.log, [])

    def test_works_with_nothing_checked(self):
        self.isolated = True
        self.assertEqual(tm.core_checked(self.w), [])
        self.click()
        self.assertEqual(self.w.status_text.Text, "Isolation reset")
        self.assertEqual(self.alerts, [])

    def test_checks_kept(self):
        self.isolated = True
        self.w._on_click(self.box("G200"), None)
        self.click()
        self.assertEqual(tm.core_checked(self.w), [1])

    def test_view_scope_rebuilds_tree_after_reset(self):
        self.w.scope_view.IsChecked = True
        self.w.scope_project.IsChecked = False
        self.w.scope_view.Checked.fire(self.w.scope_view, None)
        self.view_ids = set([1])  # the isolated view reports only G200
        self.activate(self.doc)
        self.assertNotIn("G300", self.names())
        self.isolated = True
        self.view_ids = set([1, 2, 3])  # full view after the reset
        self.click()
        self.assertIn("G300", self.names())
        self.assertIn("D1", self.names())
        self.assertEqual([b.Content for b in self.w._level_boxes], ["L1", "L2"])
        self.assertEqual(self.w._scope_ids, set([1, 2, 3]))
        self.assertEqual(self.w.status_text.Text, "Isolation reset")

    def test_project_scope_keeps_tree_objects(self):
        self.isolated = True
        before = list(self.w._items)
        self.click()
        self.assertEqual(list(self.w._items), before)

    def test_button_is_in_xaml(self):
        with open(tss.SCRIPT.replace("script.py", "ui.xaml"),
                  encoding="utf-8") as f:
            xaml = f.read()
        self.assertIn('x:Name="reset_isolate_button"', xaml)
        self.assertIn('Click="reset_isolate_click"', xaml)
        self.assertIn('Content="Reset isolate"', xaml)
        self.assertLess(xaml.index('x:Name="isolate_button"'),
                        xaml.index('x:Name="reset_isolate_button"'))
        self.assertLess(xaml.index('x:Name="reset_isolate_button"'),
                        xaml.index('x:Name="close_button"'))


if __name__ == "__main__":
    unittest.main()
