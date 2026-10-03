# -*- coding: utf-8 -*-
"""Mock verification of the modeless flow in script.py (US-11, no Revit)."""
import types
import unittest

import test_script_search as tss
from test_script_search import load_script, rec, DOMAIN, FakeExternalEvent

from advfilter import colour, session

MSG = session.DOC_CHANGED_MESSAGE


class FakeList(list):
    def Add(self, x):
        self.append(x)

    def __class_getitem__(cls, item):
        return cls


class FakeView(object):
    def __init__(self, log, fail_isolate=False):
        self.log = log
        self.fail_isolate = fail_isolate

    def IsolateElementsTemporary(self, ids):
        if self.fail_isolate:
            raise RuntimeError("boom")
        self.log.append(("isolate", list(ids)))

    def SetElementOverrides(self, eid, ogs):
        self.log.append(("set", eid, ogs))


class FakeDoc(object):
    def __init__(self, view, path="C:/a.rvt", title="A"):
        self.ActiveView = view
        self.PathName = path
        self.Title = title


def make_uiapp(doc):
    return types.SimpleNamespace(
        ActiveUIDocument=types.SimpleNamespace(Document=doc) if doc else None)


@unittest.skipUnless(hasattr(types, "SimpleNamespace"), "needs CPython 3")
class ModelessTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_script()
        self.log = []
        log = self.log

        class Txn(object):
            started = False

            def __init__(self, document, name):
                log.append(("txn", document, name))

            def Start(self):
                Txn.started = True

            def Commit(self):
                log.append("commit")

            def HasStarted(self):
                return Txn.started

            def RollBack(self):
                Txn.started = False
                log.append("rollback")

        class Group(object):
            started = False

            def __init__(self, document, name):
                log.append(("group", document, name))

            def Start(self):
                Group.started = True
                log.append("gstart")

            def Assimilate(self):
                Group.started = False
                log.append("assimilate")

            def RollBack(self):
                Group.started = False
                log.append("grollback")

            def HasStarted(self):
                return Group.started

        ns = self.ns
        ns["DB"] = types.SimpleNamespace(
            ElementId=lambda i: i, Transaction=Txn, TransactionGroup=Group,
            OverrideGraphicSettings=lambda: "EMPTY")
        ns["List"] = FakeList
        self.view_ids = set([1, 2])
        self.problem = None
        self.adapter_calls = []
        self.isolated = False  # view already in temporary isolate
        self.collect_result = None

        def active_view_ids(d, v):
            self.adapter_calls.append("ids")
            if isinstance(self.view_ids, Exception):
                raise self.view_ids
            return set(self.view_ids)

        ns["revit_adapter"] = types.SimpleNamespace(
            view_isolate_problem=lambda v: self.problem,
            active_view_ids=active_view_ids,
            in_temporary_isolate=lambda v: self.isolated,
            disable_temporary_isolate=lambda v: (
                self.adapter_calls.append("disable"), log.append("disabled")),
            collect_records=lambda d, v: self.collect_result,
            solid_fill_id=lambda d: "FILL",
            build_overrides=lambda plan: ("OGS", plan))
        self.alerts = []
        self.notices = []
        ns["forms"].alert = lambda *a, **k: self.alerts.append(a[0])
        ns["notify"] = lambda m: self.notices.append(m)
        ns["script"] = types.SimpleNamespace(get_bundle_file=lambda n: n)

        self.view = FakeView(log)
        self.doc = FakeDoc(self.view)
        self.records = [rec(1, "Walls", "Basic Wall", "G200", "L1"),
                        rec(2, "Walls", "Basic Wall", "G300", "L1"),
                        rec(3, "Doors", "Single", "D1", "L2")]
        for r in self.records:
            r.in_active_view = r.element_id in self.view_ids
        self.w = ns["FilterWindow"]("x.xaml", self.records,
                                    {"L1": 0.0, "L2": 4.0}, self.doc)
        self.event = FakeExternalEvent.created[-1]
        self.uiapp = make_uiapp(self.doc)

    def box(self, name):
        return [b for n, b in self.w._boxes if n.name == name][0]

    def run_events(self, uiapp=None):
        """What Revit does after Raise: call Execute once."""
        self.event.handler.Execute(uiapp or self.uiapp)

    def txns(self):
        return [e[2] for e in self.log if isinstance(e, tuple) and e[0] == "txn"]

    # -- window stays open, ExternalEvent wiring

    def test_event_created_in_constructor_with_handler(self):
        self.assertEqual(len(FakeExternalEvent.created), 1)
        self.assertEqual(self.event.handler.GetName(), "Advanced Filter")
        self.assertEqual(self.event.raised, 0)

    def test_isolate_keeps_window_open_and_reports(self):
        self.w._on_click(self.box("Walls"), None)
        self.w.isolate_click(None, None)
        self.assertEqual(self.event.raised, 1)
        self.assertEqual(self.w.closed_calls, 0)
        self.run_events()
        self.assertEqual(self.w.closed_calls, 0)
        self.assertEqual(self.w.status_text.Text, "Isolated 2 elements")
        self.assertIn(("isolate", [1, 2]), self.log)
        self.assertEqual(self.txns(), ["Advanced Filter: Isolate"])
        self.assertEqual(self.log[0][1], self.doc)  # Transaction on the passed doc
        self.assertEqual(self.log[-2:], ["commit", "assimilate"])
        self.assertEqual(self.notices, [])
        self.assertEqual(self.adapter_calls, ["ids"])
        self.assertEqual(self.log[0][2:], ("Advanced Filter: Isolate",))
        self.assertEqual(self.log[:2][0][0], "group")
        self.assertEqual(self.log[-1], "assimilate")

    def test_repeated_actions_work(self):
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.run_events()
        self.assertEqual(self.w.status_text.Text, "Isolated 1 element")
        self.w._on_click(self.box("G300"), None)
        self.w.isolate_click(None, None)
        self.run_events()
        self.assertEqual(self.w.status_text.Text, "Isolated 2 elements")
        self.assertEqual(self.txns(), ["Advanced Filter: Isolate"] * 2)
        self.assertEqual(self.log.count("assimilate"), 2)

    def test_reisolate_in_isolated_view_resets_first_in_one_group(self):
        self.isolated = True
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.run_events()
        i = self.log.index
        self.assertEqual(self.txns(), ["Advanced Filter: Reset isolate",
                                       "Advanced Filter: Isolate"])
        self.assertTrue(i("gstart") < i("disabled") < self.log.index(("isolate", [1])))
        self.assertEqual(self.log.count("gstart"), 1)
        self.assertEqual(self.log[-1], "assimilate")
        self.assertNotIn("grollback", self.log)
        self.assertEqual(self.w.status_text.Text, "Isolated 1 element")

    def test_reset_isolate_failure_rolls_back_group_and_alerts(self):
        self.isolated = True

        def boom(v):
            raise RuntimeError("no")
        self.ns["revit_adapter"].disable_temporary_isolate = boom
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.run_events()
        self.assertIn("rollback", self.log)
        self.assertIn("grollback", self.log)
        self.assertNotIn("assimilate", self.log)
        self.assertTrue(self.alerts[0].startswith("Isolate failed"))

    def test_group_rolls_back_when_nothing_in_view(self):
        self.isolated = True
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.view_ids = set([3])
        self.run_events()
        self.assertIn("grollback", self.log)
        self.assertNotIn("assimilate", self.log)
        self.assertNotIn(("isolate", [1]), self.log)
        self.assertEqual(self.alerts,
                         ["None of the checked elements are in the active view."])
        self.assertEqual(self.w._view_ids, set([3]))

    def test_notice_when_n_exceeds_m(self):
        self.w._on_click(self.box("Walls"), None)
        self.w._on_click(self.box("D1"), None)  # D1 not in view
        self.w.isolate_click(None, None)
        self.run_events()
        self.assertEqual(self.w.status_text.Text, "Isolated 2 elements")
        self.assertEqual(len(self.notices), 1)
        self.assertIn("1 matched element(s)", self.notices[0])

    def test_colour_and_reset_run_same_functions(self):
        self.w.colour_rgb = (1, 2, 3)
        self.w.colour_check.IsChecked = True
        self.w._on_click(self.box("Walls"), None)
        self.w.apply_colour_click(None, None)
        self.run_events()
        self.assertEqual(self.w.status_text.Text, "Coloured 2 elements")
        sets = [e for e in self.log if isinstance(e, tuple) and e[0] == "set"]
        self.assertEqual([e[1] for e in sets], [1, 2])
        self.assertEqual(sets[0][2][1], colour.override_plan((1, 2, 3), "FILL"))
        self.assertNotIn("disable", self.adapter_calls)  # only Isolate resets
        self.assertNotIn("gstart", self.log)
        del self.log[:]
        self.w.reset_colours_click(None, None)
        self.run_events()
        self.assertEqual(self.w.status_text.Text, "Reset 2 elements")
        self.assertEqual(self.txns(), ["Advanced Filter: Reset colours"])
        self.assertEqual([e for e in self.log if e[0] == "set"],
                         [("set", 1, "EMPTY"), ("set", 2, "EMPTY")])

    def test_coalesced_raises_drain_every_request(self):
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.w.reset_colours_click(None, None)
        self.assertEqual(self.event.raised, 2)
        self.run_events()  # Revit coalesces: one Execute
        self.assertEqual(self.txns(), ["Advanced Filter: Isolate",
                                       "Advanced Filter: Reset colours"])

    def test_isolate_failure_rolls_back_and_alerts(self):
        self.view.fail_isolate = True
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.run_events()
        self.assertIn("rollback", self.log)
        self.assertNotIn("commit", self.log)
        self.assertIn("grollback", self.log)
        self.assertNotIn("assimilate", self.log)
        self.assertTrue(self.alerts[0].startswith("Isolate failed"))
        self.assertNotEqual(self.w.status_text.Text, "Isolated 1 element")

    def test_exception_in_execute_never_escapes(self):
        self.view_ids = RuntimeError("collector died")
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.run_events()  # must not raise
        self.assertTrue(self.alerts[0].startswith("Isolate failed"))
        self.assertIn("grollback", self.log)
        self.assertEqual(self.txns(), [])

    # -- guards

    def test_document_guard_blocks_and_tells_user(self):
        other = FakeDoc(self.view, path="C:/b.rvt", title="B")
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.run_events(make_uiapp(other))
        self.assertEqual(self.w.status_text.Text, MSG)
        self.assertEqual(self.alerts, [MSG])
        self.assertEqual(self.txns(), [])
        self.assertEqual(self.adapter_calls, [])

    def test_unsaved_docs_compared_by_title(self):
        a = FakeDoc(self.view, path="", title="Project1")
        w = self.ns["FilterWindow"]("x.xaml", self.records, {"L1": 0.0, "L2": 4.0}, a)
        self.assertEqual(w.doc_key(), ("", "Project1"))
        self.assertIsNotNone(session.document_guard(
            w.doc_key(), self.ns["doc_key_of"](FakeDoc(self.view, "", "Project2"))))

    def test_no_active_document_alerts(self):
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.run_events(make_uiapp(None))
        self.assertEqual(self.alerts, ["Open a Revit project first."])

    def test_view_guard_failure_changes_nothing(self):
        self.problem = "Temporary isolate is not available in this view type (Schedule)."
        self.w._on_click(self.box("G200"), None)
        before = self.w.status_text.Text
        self.w.isolate_click(None, None)
        self.run_events()
        self.assertEqual(self.alerts, [self.problem])
        self.assertEqual(self.txns(), [])
        self.assertEqual(self.adapter_calls, [])
        self.assertEqual(self.w.status_text.Text, before)

    def test_view_ids_rebuilt_before_acting(self):
        self.w._on_click(self.box("Walls"), None)
        self.w.isolate_click(None, None)
        self.view_ids = set([2])  # user switched view between click and Execute
        self.run_events()
        self.assertIn(("isolate", [2]), self.log)
        self.assertEqual(self.w.status_text.Text, "Isolated 1 element")
        self.assertEqual(len(self.notices), 1)  # N=2 > M=1
        self.assertEqual(self.w._view_ids, set([2]))

    def test_none_in_rebuilt_view_alerts(self):
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.view_ids = set([3])
        self.run_events()
        self.assertEqual(self.alerts, ["None of the checked elements are in the active view."])
        self.assertEqual(self.txns(), [])

    # -- ViewActivated

    def activate(self, document, view="V2"):
        revit = self.ns["__revit__"]
        revit.ViewActivated.fire(
            None, types.SimpleNamespace(Document=document, CurrentActiveView=view))

    def test_view_activated_updates_m_and_status(self):
        self.w._on_click(self.box("Walls"), None)
        self.assertEqual(self.w.status_text.Text, u"2 matched · 2 in active view")
        self.view_ids = set([2, 3, 99])  # 99 is not a record id
        self.activate(self.doc)
        self.assertEqual(self.w.status_text.Text, u"2 matched · 1 in active view")
        self.assertEqual(self.w._view_ids, set([2, 3]))
        self.assertEqual([r.in_active_view for r in self.records], [False, True, True])
        self.assertTrue(self.w.isolate_button.IsEnabled)

    def test_view_activated_other_document_ignored(self):
        self.w._on_click(self.box("Walls"), None)
        self.view_ids = set()
        self.activate(FakeDoc(self.view, "C:/b.rvt", "B"))
        self.assertEqual(self.w.status_text.Text, u"2 matched · 2 in active view")

    def test_view_activated_failure_gives_empty_m(self):
        self.w._on_click(self.box("Walls"), None)
        self.view_ids = RuntimeError("sheet")
        self.activate(self.doc)  # must not raise
        self.assertEqual(self.w.status_text.Text, u"2 matched · 0 in active view")
        self.assertFalse(self.w.isolate_button.IsEnabled)

    # -- Refresh

    def test_refresh_routes_through_event(self):
        self.w.refresh_click(None, None)
        self.assertEqual(self.event.raised, 1)
        self.assertEqual(self.adapter_calls, [])  # no API call from the click
        self.assertEqual([r.action for r in self.w._queue.drain()], ["refresh"])

    def test_refresh_preserves_levels_search_and_checks(self):
        w = self.w
        w._on_click(self.box("G200"), None)
        w.search_box.Text = "wall"
        w._on_search_tick(None, None)
        w._level_boxes[1].IsChecked = False  # untick L2
        w._on_level_toggle(None, None)
        self.assertEqual(w._selected_levels(), ["L1"])

        new_doc = FakeDoc(self.view, "C:/b.rvt", "B")
        new_records = [rec(10, "Walls", "Basic Wall", "G200", "L1"),
                       rec(11, "Walls", "Basic Wall", "G300", "L1"),
                       rec(12, "Doors", "Single", "D1", "L2"),
                       rec(13, "Doors", "Single", "D9", "L3")]
        for r in new_records:
            r.in_active_view = r.element_id in (10, 12)
        self.collect_result = (new_records, {"L1": 0.0, "L2": 4.0, "L3": 8.0})
        w.refresh_click(None, None)
        self.run_events(make_uiapp(new_doc))

        self.assertEqual([b.Content for b in w._level_boxes], ["L1", "L2", "L3"])
        self.assertEqual([b.IsChecked for b in w._level_boxes], [True, False, True])
        self.assertFalse(w.all_levels.IsChecked)
        self.assertEqual(w.search_box.Text, "wall")
        self.assertEqual(core_checked(w), [10])  # G200 stayed checked, new ids
        self.assertEqual(w._doc, new_doc)
        self.assertEqual(w.doc_key(), ("C:/b.rvt", "B"))
        self.assertEqual(w._view_ids, set([10, 12]))
        self.assertEqual(w.status_text.Text, "Refreshed: 4 elements")
        # Actions on the new document now pass the guard.
        self.view_ids = set([10, 12])
        w.isolate_click(None, None)
        self.run_events(make_uiapp(new_doc))
        self.assertEqual(w.status_text.Text, "Isolated 1 element")

    def test_refresh_after_document_change_unblocks_actions(self):
        other = FakeDoc(self.view, "C:/b.rvt", "B")
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.run_events(make_uiapp(other))
        self.assertEqual(self.w.status_text.Text, MSG)
        self.collect_result = ([rec(1, "Walls", "Basic Wall", "G200")], {"L1": 0.0})
        self.w.refresh_click(None, None)
        self.run_events(make_uiapp(other))
        self.assertEqual(self.w.doc_key(), ("C:/b.rvt", "B"))

    def test_refresh_with_no_elements_keeps_state(self):
        self.collect_result = ([], {})
        self.w.refresh_click(None, None)
        self.run_events()
        self.assertEqual(self.alerts, ["No model elements found in this project."])
        self.assertEqual(len(self.w._records), 3)

    # -- close

    def test_close_unsubscribes_and_releases(self):
        revit = self.ns["__revit__"]
        self.assertEqual(len(revit.ViewActivated.handlers), 1)
        self.ns["set_open_window"](self.w)
        self.w.close_click(None, None)
        self.assertEqual(self.w.closed_calls, 1)
        self.assertEqual(revit.ViewActivated.handlers, [])
        self.assertIsNone(self.ns["get_open_window"]())
        self.assertTrue(self.event.disposed)
        self.assertEqual(self.w.take_requests(), [])
        # A late ViewActivated or Execute does nothing.
        self.activate(self.doc)
        self.run_events()

    def test_closed_via_window_x_does_same_cleanup(self):
        self.w.Closed.fire(self.w, None)
        self.assertEqual(self.ns["__revit__"].ViewActivated.handlers, [])
        self.assertTrue(self.event.disposed)


def core_checked(window):
    from advfilter import core
    return core.checked_element_ids(window._roots)


@unittest.skipUnless(hasattr(types, "SimpleNamespace"), "needs CPython 3")
class SingleInstanceTests(unittest.TestCase):
    def _script(self, fresh):
        ns = load_script(fresh=fresh)
        view = object()
        doc = FakeDoc(view)
        ns["__revit__"].ActiveUIDocument = types.SimpleNamespace(Document=doc)
        ns["revit_adapter"] = types.SimpleNamespace(
            view_isolate_problem=lambda v: None,
            collect_records=lambda d, v: (
                [rec(1, "Walls", "Basic Wall", "G200")], {"L1": 0.0}))
        ns["script"] = types.SimpleNamespace(get_bundle_file=lambda n: n)
        return ns

    def test_first_press_shows_second_press_activates(self):
        ns = self._script(True)
        ns["main"]()
        w = ns["get_open_window"]()
        self.assertIsNotNone(w)
        self.assertEqual((w.shown, w.activated), (1, 0))
        # Persistent engine: script.py runs again, module state is new.
        ns2 = self._script(False)  # exec runs main(): that press activates
        self.assertIs(ns2["get_open_window"](), w)
        self.assertEqual((w.shown, w.activated), (1, 1))
        ns2["main"]()
        self.assertEqual((w.shown, w.activated), (1, 2))
        self.assertEqual(len(FakeExternalEvent.created), 1)

    def test_minimised_window_is_restored(self):
        ns = self._script(True)
        ns["main"]()
        w = ns["get_open_window"]()
        w.WindowState = "Minimized"
        self._script(False)["main"]()
        self.assertEqual(w.WindowState, "Normal")

    def test_after_close_next_press_opens_new_window(self):
        ns = self._script(True)
        ns["main"]()
        w = ns["get_open_window"]()
        w.Close()
        self.assertIsNone(ns["get_open_window"]())
        ns2 = self._script(False)
        ns2["main"]()
        w2 = ns2["get_open_window"]()
        self.assertIsNot(w2, w)
        self.assertEqual(w2.shown, 1)

    def test_stale_window_replaced(self):
        ns = self._script(True)
        ns["main"]()
        w = ns["get_open_window"]()

        def boom():
            raise RuntimeError("disposed")
        w.Activate = boom
        ns2 = self._script(False)
        ns2["main"]()
        self.assertIsNot(ns2["get_open_window"](), w)

    def test_persistent_engine_flag(self):
        self.assertIs(self._script(True)["__persistentengine__"], True)


if __name__ == "__main__":
    unittest.main()
