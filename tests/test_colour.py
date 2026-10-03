# -*- coding: utf-8 -*-
"""Pure colour logic (colour.py) plus mock verification of the colour flow."""
import sys
import types
import unittest

from test_script_search import load_script, rec

from advfilter import colour


def C(r, g, b):
    return types.SimpleNamespace(R=r, G=g, B=b)


class PureTests(unittest.TestCase):
    def test_to_rgb_clamps(self):
        self.assertEqual(colour.to_rgb(C(10, 20, 30)), (10, 20, 30))
        self.assertEqual(colour.to_rgb(C(-5, 300, 255.9)), (0, 255, 255))

    def test_plan_order_and_content(self):
        plan = colour.override_plan((1, 2, 3), "FILL")
        self.assertEqual(plan, [
            ("SetSurfaceForegroundPatternId", "FILL"),
            ("SetSurfaceForegroundPatternColor", (1, 2, 3)),
            ("SetSurfaceForegroundPatternVisible", True),
            ("SetCutForegroundPatternId", "FILL"),
            ("SetCutForegroundPatternColor", (1, 2, 3)),
            ("SetCutForegroundPatternVisible", True),
            ("SetProjectionLineColor", (1, 2, 3)),
            ("SetCutLineColor", (1, 2, 3)),
        ])

    def test_enable_matrix(self):
        ae = colour.action_enabled
        self.assertEqual(ae(True, True, 3), (True, True))
        self.assertEqual(ae(False, True, 3), (False, True))
        self.assertEqual(ae(True, False, 3), (False, True))
        self.assertEqual(ae(True, True, 0), (False, False))
        self.assertEqual(ae(False, False, 0), (False, False))

    def test_find_solid_fill(self):
        def fpe(solid, target, i):
            pat = types.SimpleNamespace(IsSolidFill=solid, Target=target)
            return types.SimpleNamespace(GetFillPattern=lambda: pat, Id=i)
        self.assertIsNone(colour.find_solid_fill_id([]))
        self.assertIsNone(colour.find_solid_fill_id(
            [fpe(False, "Drafting", 1), fpe(True, "Model", 2)]))
        self.assertEqual(colour.find_solid_fill_id(
            [fpe(True, "Model", 2), fpe(False, "Drafting", 1),
             fpe(True, "Drafting", 3)]), 3)


class ParseTests(unittest.TestCase):
    def test_rgb_round_trip_and_bad_input(self):
        self.assertEqual(colour.format_rgb((1, 2, 3)), "1,2,3")
        self.assertEqual(colour.parse_rgb("1,2,3"), (1, 2, 3))
        self.assertEqual(colour.parse_rgb(" 1, 2 ,300"), (1, 2, 255))
        for bad in (None, "", "1,2", "a,b,c", "1,2,3,4", 5):
            self.assertIsNone(colour.parse_rgb(bad))

    def test_ints_round_trip_and_bad_input(self):
        self.assertEqual(colour.format_ints([5, 6, 7]), "5,6,7")
        self.assertEqual(colour.parse_ints("5,6,7"), [5, 6, 7])
        for bad in (None, "", "x,1", 3.5):
            self.assertIsNone(colour.parse_ints(bad))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        class OGS(object):
            def __init__(self):
                self.calls = []
        for name in ("SetSurfaceForegroundPatternId", "SetSurfaceForegroundPatternColor",
                     "SetSurfaceForegroundPatternVisible", "SetCutForegroundPatternId",
                     "SetCutForegroundPatternColor", "SetCutForegroundPatternVisible",
                     "SetProjectionLineColor", "SetCutLineColor"):
            setattr(OGS, name, (lambda n: lambda self, v: self.calls.append((n, v)))(name))

        class Collector(object):
            def __init__(self, doc):
                self.doc = doc

            def OfClass(self, cls):
                return self.doc

        db = types.ModuleType("Autodesk.Revit.DB")
        db.OverrideGraphicSettings = OGS
        db.Color = lambda r, g, b: ("Color", r, g, b)
        db.FilteredElementCollector = Collector
        db.FillPatternElement = object
        self.saved = dict((k, sys.modules.get(k)) for k in
                          ("Autodesk", "Autodesk.Revit", "Autodesk.Revit.DB"))
        sys.modules["Autodesk"] = types.ModuleType("Autodesk")
        sys.modules["Autodesk.Revit"] = types.ModuleType("Autodesk.Revit")
        sys.modules["Autodesk.Revit.DB"] = db

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_build_overrides_converts_colours_in_order(self):
        from advfilter import revit_adapter
        plan = colour.override_plan((1, 2, 3), "FILL")
        ogs = revit_adapter.build_overrides(plan)
        expected = [(n, ("Color", 1, 2, 3) if isinstance(v, tuple) else v)
                    for n, v in plan]
        self.assertEqual(ogs.calls, expected)

    def test_solid_fill_id_uses_collector(self):
        from advfilter import revit_adapter
        pat = types.SimpleNamespace(IsSolidFill=True, Target="Drafting")
        fpe = types.SimpleNamespace(GetFillPattern=lambda: pat, Id=7)
        self.assertEqual(revit_adapter.solid_fill_id([fpe]), 7)
        self.assertIsNone(revit_adapter.solid_fill_id([]))


@unittest.skipUnless(hasattr(types, "SimpleNamespace"), "needs CPython 3")
class ScriptColourTests(unittest.TestCase):
    def setUp(self):
        import test_script_search as tss
        self.tss = tss
        tss.CONFIG.__dict__.clear()
        del tss.SAVES[:]
        self.ns = load_script()
        self.records = [rec(1, "Walls", "Basic Wall", "G200"),
                        rec(2, "Walls", "Basic Wall", "G300"),
                        rec(3, "Doors", "Single", "D1")]
        self.records[0].in_active_view = True
        self.records[1].in_active_view = True
        self.records[2].in_active_view = False
        self.w = self.ns["FilterWindow"]("x.xaml", self.records, {"L1": 0.0})
        self.w.Close = lambda: None
        self.picks = []
        self.alerts = []
        self.ns["forms"].alert = lambda *a, **k: self.alerts.append(a[0])

    def script_pick(self, *results):
        results = list(results)

        def fake(initial, custom):
            self.picks.append((initial, custom))
            return results.pop(0), "CUSTOM"
        self.ns["pick_colour"] = fake

    def box(self, name):
        return [b for n, b in self.w._boxes if n.name == name][0]

    def tick(self, value=True):
        self.w.colour_check.IsChecked = value
        self.w.colour_check_changed(None, None)

    def test_tick_opens_picker_and_shows_swatch(self):
        self.script_pick((10, 20, 30))
        self.tick()
        self.assertEqual(len(self.picks), 1)
        self.assertTrue(self.w.colour_check.IsChecked)
        self.assertEqual(self.w.colour_swatch.Visibility, "Visible")
        self.assertEqual(self.w.colour_rgb, (10, 20, 30))
        self.assertEqual(self.w._custom_colors, "CUSTOM")

    def test_pick_saved_and_restored_by_new_window(self):
        self.script_pick((10, 20, 30))
        self.ns["pick_colour"] = lambda i, c: ((10, 20, 30), [5, 6])
        self.tick()
        self.assertEqual(self.tss.CONFIG.last_rgb, "10,20,30")
        self.assertEqual(self.tss.CONFIG.custom_colors, "5,6")
        self.assertEqual(len(self.tss.SAVES), 1)
        ns2 = load_script()
        w2 = ns2["FilterWindow"]("x.xaml", self.records, {"L1": 0.0})
        self.assertEqual(w2.colour_rgb, (10, 20, 30))
        self.assertEqual(w2._custom_colors, [5, 6])

    def test_cancel_does_not_save(self):
        self.script_pick(None)
        self.tick()
        self.assertEqual(self.tss.SAVES, [])

    def test_config_failure_never_blocks(self):
        def boom():
            raise RuntimeError("cfg")
        self.ns["script"].get_config = boom
        self.ns["pick_colour"] = lambda i, c: ((1, 2, 3), [])
        self.tick()
        self.assertEqual(self.w.colour_rgb, (1, 2, 3))
        w2 = self.ns["FilterWindow"]("x.xaml", self.records, {"L1": 0.0})
        self.assertIsNone(w2.colour_rgb)

    def test_cancel_first_time_unticks(self):
        self.script_pick(None)
        self.tick()
        self.assertFalse(self.w.colour_check.IsChecked)
        self.assertEqual(self.w.colour_swatch.Visibility, "Collapsed")
        self.assertIsNone(self.w.colour_rgb)

    def test_untick_remembers_and_retick_reopens(self):
        self.script_pick((1, 2, 3), None)
        self.tick()
        self.tick(False)
        self.assertEqual(self.w.colour_swatch.Visibility, "Collapsed")
        self.assertEqual(self.w.colour_rgb, (1, 2, 3))
        self.tick()  # picker cancelled, earlier colour kept, stays ticked
        self.assertTrue(self.w.colour_check.IsChecked)
        self.assertEqual(self.w.colour_rgb, (1, 2, 3))
        self.assertEqual(self.picks[1], ((1, 2, 3), "CUSTOM"))

    def test_swatch_reopens_picker(self):
        self.script_pick((1, 2, 3), (4, 5, 6))
        self.tick()
        self.w.colour_swatch_click(None, None)
        self.assertEqual(self.w.colour_rgb, (4, 5, 6))
        self.assertEqual(len(self.picks), 2)

    def test_button_states(self):
        w = self.w
        self.assertFalse(w.apply_colour_button.IsEnabled)
        self.assertFalse(w.reset_colours_button.IsEnabled)
        w._on_click(self.box("G200"), None)  # M = 1
        self.assertFalse(w.apply_colour_button.IsEnabled)  # box not ticked
        self.assertTrue(w.reset_colours_button.IsEnabled)
        self.script_pick((1, 2, 3))
        self.tick()
        self.assertTrue(w.apply_colour_button.IsEnabled)
        w._on_click(self.box("G200"), None)  # back to nothing
        self.assertFalse(w.apply_colour_button.IsEnabled)
        self.assertFalse(w.reset_colours_button.IsEnabled)
        w._on_click(self.box("D1"), None)  # N=1, M=0
        self.assertFalse(w.apply_colour_button.IsEnabled)
        self.assertFalse(w.reset_colours_button.IsEnabled)

    def test_apply_click_stores_action(self):
        w = self.w
        self.script_pick((1, 2, 3))
        self.tick()
        w._on_click(self.box("Walls"), None)
        w.apply_colour_click(None, None)
        self.assertEqual(w.action, "colour")
        self.assertEqual(sorted(w.action_ids), [1, 2])
        self.assertEqual(w.counts, (2, 2))
        self.assertEqual(w.colour_rgb, (1, 2, 3))

    def test_reset_click_stores_action(self):
        w = self.w
        w._on_click(self.box("Doors"), None)
        w._on_click(self.box("G200"), None)
        w.reset_colours_click(None, None)
        self.assertEqual(w.action, "reset")
        self.assertEqual(w.action_ids, [1])
        self.assertEqual(w.counts, (2, 1))

    def test_guards_alert_without_closing(self):
        w = self.w
        self.script_pick((1, 2, 3))
        self.tick()
        w.apply_colour_click(None, None)  # nothing checked
        w.reset_colours_click(None, None)  # nothing checked
        w._on_click(self.box("D1"), None)
        w.reset_colours_click(None, None)  # none in view
        self.assertEqual(len(self.alerts), 3)
        self.assertIsNone(w.action)

    def test_isolate_unaffected(self):
        w = self.w
        w._on_click(self.box("Walls"), None)
        w.isolate_click(None, None)
        self.assertEqual(w.action, "isolate")
        self.assertEqual(sorted(w.ids_to_isolate), [1, 2])
        self.assertEqual(w.counts, (2, 2))

    def _env(self, fill_id="FILL", fail_on=None):
        ns = self.ns
        log = []

        class Txn(object):
            started = False

            def __init__(self, doc, name):
                log.append(("txn", name))

            def Start(self):
                Txn.started = True
                log.append("start")

            def Commit(self):
                log.append("commit")

            def HasStarted(self):
                return Txn.started

            def RollBack(self):
                Txn.started = False
                log.append("rollback")

        class View(object):
            def SetElementOverrides(self, eid, ogs):
                if fail_on == eid:
                    raise RuntimeError("boom")
                log.append(("set", eid, ogs))

        ns["doc"] = object()
        ns["DB"] = types.SimpleNamespace(
            ElementId=lambda i: i, Transaction=Txn,
            OverrideGraphicSettings=lambda: "EMPTY")
        ns["revit_adapter"] = types.SimpleNamespace(
            solid_fill_id=lambda d: fill_id,
            build_overrides=lambda plan: ("OGS", plan))
        ns["forms"].alert = lambda *a, **k: log.append(("alert", a[0]))
        return View(), log

    @staticmethod
    def sets(log):
        return [e for e in log if isinstance(e, tuple) and e[0] == "set"]

    def test_apply_commits_each_id(self):
        view, log = self._env()
        self.assertTrue(self.ns["apply_colour"](view, [1, 2], (1, 2, 3)))
        self.assertEqual(log[:2], [("txn", "Advanced Filter: Colour override"), "start"])
        sets = self.sets(log)
        self.assertEqual([e[1] for e in sets], [1, 2])
        self.assertEqual(sets[0][2][1], colour.override_plan((1, 2, 3), "FILL"))
        self.assertEqual(log[-1], "commit")

    def test_apply_no_solid_fill_rolls_back(self):
        view, log = self._env(fill_id=None)
        self.assertFalse(self.ns["apply_colour"](view, [1], (1, 2, 3)))
        self.assertIn("rollback", log)
        self.assertNotIn("commit", log)
        self.assertIn(("alert", "No solid fill pattern found in this project."), log)
        self.assertFalse(self.sets(log))

    def test_apply_exception_rolls_back(self):
        view, log = self._env(fail_on=2)
        self.assertFalse(self.ns["apply_colour"](view, [1, 2], (1, 2, 3)))
        self.assertIn("rollback", log)
        self.assertNotIn("commit", log)
        self.assertEqual(log[-1][0], "alert")

    def test_reset_flow(self):
        view, log = self._env()
        self.assertTrue(self.ns["reset_colours"](view, [1, 2]))
        self.assertEqual(log[0], ("txn", "Advanced Filter: Reset colours"))
        self.assertEqual(self.sets(log), [("set", 1, "EMPTY"), ("set", 2, "EMPTY")])
        self.assertEqual(log[-1], "commit")

    def test_reset_exception_rolls_back(self):
        view, log = self._env(fail_on=1)
        self.assertFalse(self.ns["reset_colours"](view, [1]))
        self.assertIn("rollback", log)
        self.assertNotIn("commit", log)

    def test_main_dispatch(self):
        for action, counts, expect in (
                ("colour", (3, 1), ["apply", "notify"]),
                ("reset", (2, 2), ["reset"]),
                ("isolate", (3, 1), ["isolate", "notify"]),
                (None, (3, 1), [])):
            ns = self.ns
            calls = []

            class FakeWindow(object):
                def __init__(self, *a):
                    self.action = action
                    self.action_ids = [1]
                    self.counts = counts
                    self.colour_rgb = (1, 2, 3)

                def ShowDialog(self):
                    pass
            ns["doc"] = types.SimpleNamespace(ActiveView=object())
            ns["revit_adapter"] = types.SimpleNamespace(
                view_isolate_problem=lambda v: None,
                collect_records=lambda d, v: ([1], {}))
            ns["script"] = types.SimpleNamespace(get_bundle_file=lambda n: n)
            ns["FilterWindow"] = FakeWindow
            ns["apply_colour"] = lambda v, i, c: calls.append("apply") or True
            ns["reset_colours"] = lambda v, i: calls.append("reset") or True
            ns["isolate"] = lambda v, i: calls.append("isolate") or True
            ns["notify"] = lambda m: calls.append("notify")
            ns["main"]()
            self.assertEqual(calls, expect, action)


if __name__ == "__main__":
    unittest.main()
