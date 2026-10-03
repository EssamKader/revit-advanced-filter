# -*- coding: utf-8 -*-
"""Scope toggle (US-12): pure core functions and script.py wiring (no Revit)."""
import types
import unittest

import test_script_search as tss
import test_script_modeless as tm
from test_script_search import rec

from advfilter import core

L = core


class ScopePureTests(unittest.TestCase):
    def setUp(self):
        self.records = [rec(1, "Walls", "Basic Wall", "G200", "L1"),
                        rec(2, "Walls", "Basic Wall", "G300", "L1"),
                        rec(3, "Doors", "Single", "D1", "L2"),
                        rec(4, "Doors", "Single", "D2", "L3")]

    def ids(self, records):
        return [r.element_id for r in records]

    def test_constants(self):
        self.assertEqual((L.SCOPE_PROJECT, L.SCOPE_VIEW), ("project", "view"))

    def test_project_scope_keeps_all(self):
        out = L.filter_by_scope(self.records, L.SCOPE_PROJECT, [1])
        self.assertEqual(self.ids(out), [1, 2, 3, 4])
        self.assertIsNot(out, self.records)

    def test_view_scope_keeps_only_view_ids(self):
        out = L.filter_by_scope(self.records, L.SCOPE_VIEW, set([2, 3, 99]))
        self.assertEqual(self.ids(out), [2, 3])

    def test_view_scope_empty_view(self):
        self.assertEqual(L.filter_by_scope(self.records, L.SCOPE_VIEW, []), [])

    def test_composes_with_levels_scope_first(self):
        scoped = L.filter_by_scope(self.records, L.SCOPE_VIEW, [1, 3, 4])
        out = L.filter_by_levels(scoped, ["L1", "L2"])
        self.assertEqual(self.ids(out), [1, 3])
        # a level only outside the view yields nothing
        self.assertEqual(L.filter_by_levels(scoped, ["L9"]), [])

    def test_level_list_shows_only_scoped_levels(self):
        scoped = L.filter_by_scope(self.records, L.SCOPE_VIEW, [1, 3])
        elev = {"L1": 0.0, "L2": 4.0, "L3": 8.0}
        self.assertEqual(L.ordered_levels(scoped, elev), ["L1", "L2"])
        self.assertEqual(L.ordered_levels(self.records, elev), ["L1", "L2", "L3"])

    def test_level_selection_merge_on_scope_change(self):
        from advfilter import session
        # L2 unticked, then the view hides L3 and shows a new L4
        merged = session.merge_level_selection(["L1"], ["L1", "L2", "L3"],
                                               ["L1", "L2", "L4"])
        self.assertEqual(merged, ["L1", "L4"])

    def test_parse_scope(self):
        self.assertEqual(L.parse_scope("view"), L.SCOPE_VIEW)
        self.assertEqual(L.parse_scope(" View "), L.SCOPE_VIEW)
        self.assertEqual(L.parse_scope("project"), L.SCOPE_PROJECT)
        for bad in (None, "", "x", 5, object()):
            self.assertEqual(L.parse_scope(bad), L.SCOPE_PROJECT)


@unittest.skipUnless(hasattr(types, "SimpleNamespace"), "needs CPython 3")
class ScopeScriptTests(unittest.TestCase):
    box = tm.ModelessTests.box
    run_events = tm.ModelessTests.run_events
    activate = tm.ModelessTests.activate

    def setUp(self):
        tss.CONFIG.__dict__.clear()
        del tss.SAVES[:]
        tm.ModelessTests.setUp(self)
        # setUp replaced `script`; give it the config functions again.
        self.ns["script"].get_config = lambda: tss.CONFIG
        self.ns["script"].save_config = lambda: tss.SAVES.append(1)

    def tearDown(self):
        tss.CONFIG.__dict__.clear()  # CONFIG is shared with other test modules
        del tss.SAVES[:]

    def names(self):
        return sorted(n.name for n in self.w._items)

    def select_view_scope(self):
        self.w.scope_view.IsChecked = True
        self.w.scope_project.IsChecked = False
        self.w.scope_view.Checked.fire(self.w.scope_view, None)

    def select_project_scope(self):
        self.w.scope_project.IsChecked = True
        self.w.scope_view.IsChecked = False
        self.w.scope_project.Checked.fire(self.w.scope_project, None)

    def test_default_is_whole_project(self):
        self.assertTrue(self.w.scope_project.IsChecked)
        self.assertFalse(self.w.scope_view.IsChecked)
        self.assertEqual(self.w._scope, "project")
        self.assertEqual([b.Content for b in self.w._level_boxes], ["L1", "L2"])

    def test_toggle_to_view_scopes_tree_and_levels(self):
        self.select_view_scope()  # view has ids 1, 2 (both L1)
        self.assertEqual([b.Content for b in self.w._level_boxes], ["L1"])
        self.assertNotIn("D1", self.names())
        self.assertEqual(self.w.status_text.Text, "Nothing selected")

    def test_toggle_keeps_search_and_checks(self):
        self.w._on_click(self.box("G200"), None)
        self.w.search_box.Text = "wall"
        self.w._on_search_tick(None, None)
        self.select_view_scope()
        self.assertEqual(tm.core_checked(self.w), [1])
        self.assertEqual(self.w.search_box.Text, "wall")
        self.assertEqual(self.w.status_text.Text, u"1 matched · 1 in active view")
        self.select_project_scope()
        self.assertEqual(tm.core_checked(self.w), [1])
        self.assertIn("D1", self.names())
        self.assertEqual([b.Content for b in self.w._level_boxes], ["L1", "L2"])

    def test_hidden_check_survives_round_trip(self):
        self.w._on_click(self.box("D1"), None)  # D1 (id 3) is outside the view
        self.select_view_scope()
        self.assertNotIn("D1", self.names())
        self.select_project_scope()
        self.assertEqual(tm.core_checked(self.w), [3])

    def test_level_selection_kept_by_name(self):
        self.w._level_boxes[1].IsChecked = False  # untick L2
        self.w._on_level_toggle(None, None)
        self.select_view_scope()
        self.select_project_scope()  # L2 is "new" again -> selected
        self.assertEqual(self.w._selected_levels(), ["L1", "L2"])
        self.w._level_boxes[0].IsChecked = False
        self.w._on_level_toggle(None, None)
        self.select_view_scope()  # only L1 in view, previously unticked
        self.assertEqual([b.IsChecked for b in self.w._level_boxes], [False])
        self.assertEqual(self.names(), [])

    def test_same_scope_event_is_ignored(self):
        rebuilds = []
        orig = self.w._rebuild
        self.w._rebuild = lambda: (rebuilds.append(1), orig())
        self.w.scope_project.Checked.fire(self.w.scope_project, None)
        self.assertEqual(rebuilds, [])
        self.assertEqual(tss.SAVES, [])

    # -- config

    def test_toggle_saves_scope(self):
        self.select_view_scope()
        self.assertEqual(tss.CONFIG.scope, "view")
        self.select_project_scope()
        self.assertEqual(tss.CONFIG.scope, "project")
        self.assertEqual(len(tss.SAVES), 2)

    def test_saved_view_scope_restored_on_open(self):
        tss.CONFIG.scope = "view"
        w = self.ns["FilterWindow"]("x.xaml", self.records,
                                    {"L1": 0.0, "L2": 4.0}, self.doc)
        self.assertEqual(w._scope, "view")
        self.assertTrue(w.scope_view.IsChecked)
        self.assertFalse(w.scope_project.IsChecked)
        self.assertEqual([b.Content for b in w._level_boxes], ["L1"])
        self.assertNotIn("D1", [n.name for n in w._items])

    def test_bad_or_missing_config_gives_project(self):
        for value in ("garbage", None, 7):
            tss.CONFIG.scope = value
            self.assertEqual(self.ns["load_scope"](), "project")
        del tss.CONFIG.scope
        self.assertEqual(self.ns["load_scope"](), "project")

    def test_config_failure_never_raises(self):
        def boom():
            raise RuntimeError("cfg")
        self.ns["script"].get_config = boom
        self.assertEqual(self.ns["load_scope"](), "project")
        self.ns["save_scope"]("view")  # must not raise
        self.select_view_scope()  # toggle still works

    # -- ViewActivated

    def test_view_activated_view_scope_rebuilds_tree_for_new_view(self):
        self.select_view_scope()
        self.view_ids = set([3])
        self.activate(self.doc)
        self.assertEqual(self.names(), ["D1", "Doors", "Single"])
        self.assertEqual([b.Content for b in self.w._level_boxes], ["L2"])
        self.assertEqual(self.w._view_ids, set([3]))
        self.assertEqual(self.w._scope_ids, set([3]))

    def test_view_activated_view_scope_keeps_checks_by_path(self):
        self.select_view_scope()
        self.w._on_click(self.box("G200"), None)
        self.view_ids = set([2, 3])
        self.activate(self.doc)
        self.assertEqual(tm.core_checked(self.w), [])  # G200 not in the new view
        self.view_ids = set([1, 2])
        self.activate(self.doc)
        self.assertEqual(tm.core_checked(self.w), [1])  # remembered path returns

    def test_view_activated_project_scope_only_updates_m(self):
        before = list(self.w._items)
        levels = [b.Content for b in self.w._level_boxes]
        self.w._on_click(self.box("Walls"), None)
        self.view_ids = set([3])
        self.activate(self.doc)
        self.assertEqual(list(self.w._items), before)  # same tree objects
        self.assertEqual([b.Content for b in self.w._level_boxes], levels)
        self.assertEqual(self.w.status_text.Text, u"2 matched · 0 in active view")
        self.assertEqual(self.w._scope_ids, set([3]))

    def test_view_activated_other_document_ignored_in_view_scope(self):
        self.select_view_scope()
        self.view_ids = set([3])
        self.activate(tm.FakeDoc(self.view, "C:/b.rvt", "B"))
        self.assertNotIn("D1", self.names())

    # -- unsupported views

    def test_unsupported_view_shows_empty_tree_and_hint(self):
        self.select_view_scope()
        self.problem = "Temporary isolate is not available in this view type."
        self.activate(self.doc, view="Sheet")
        self.assertEqual(self.w.tree.Items, [])
        self.assertEqual(self.w._items, {})
        self.assertEqual(self.w.status_text.Text,
                         "Active view does not support element filtering")
        self.assertFalse(self.w.isolate_button.IsEnabled)

    def test_collector_failure_in_view_scope_shows_hint(self):
        self.select_view_scope()
        self.view_ids = RuntimeError("sheet")
        self.activate(self.doc)
        self.assertEqual(self.w._items, {})
        self.assertEqual(self.w.status_text.Text,
                         "Active view does not support element filtering")

    def test_unsupported_view_in_project_scope_keeps_tree_and_no_hint(self):
        self.problem = "nope"
        self.activate(self.doc)
        self.assertIn("D1", self.names())
        self.assertNotEqual(self.w.status_text.Text,
                            "Active view does not support element filtering")

    def test_leaving_unsupported_view_restores_tree(self):
        self.select_view_scope()
        self.problem = "nope"
        self.activate(self.doc)
        self.assertEqual(self.w._items, {})
        self.problem = None
        self.view_ids = set([1, 2])
        self.activate(self.doc)
        self.assertIn("G200", self.names())
        self.assertNotEqual(self.w.status_text.Text,
                            "Active view does not support element filtering")

    def test_hint_clears_on_switch_to_project_scope(self):
        self.select_view_scope()
        self.problem = "nope"
        self.activate(self.doc)
        self.select_project_scope()
        self.assertIn("D1", self.names())
        self.assertNotEqual(self.w.status_text.Text,
                            "Active view does not support element filtering")

    # -- Refresh

    def refresh_with(self, records, unsupported=False):
        self.collect_result = (records, {"L1": 0.0, "L2": 4.0})
        if unsupported:
            self.problem = "nope"
        self.w.refresh_click(None, None)
        self.run_events()

    def test_refresh_reapplies_view_scope(self):
        self.select_view_scope()
        new = [rec(1, "Walls", "Basic Wall", "G200", "L1"),
               rec(3, "Doors", "Single", "D1", "L2"),
               rec(4, "Doors", "Single", "D2", "L2")]
        for r in new:
            r.in_active_view = r.element_id in (3, 4)
        self.refresh_with(new)
        self.assertEqual(self.names(), ["D1", "D2", "Doors", "Single"])
        self.assertEqual([b.Content for b in self.w._level_boxes], ["L2"])
        self.assertEqual(self.w.status_text.Text, "Refreshed: 3 elements")

    def test_refresh_in_project_scope_shows_everything(self):
        new = [rec(1, "Walls", "Basic Wall", "G200", "L1"),
               rec(3, "Doors", "Single", "D1", "L2")]
        for r in new:
            r.in_active_view = r.element_id == 3
        self.refresh_with(new)
        self.assertIn("G200", self.names())
        self.assertEqual([b.Content for b in self.w._level_boxes], ["L1", "L2"])

    def test_refresh_on_unsupported_view_in_view_scope(self):
        self.select_view_scope()
        new = [rec(1, "Walls", "Basic Wall", "G200", "L1")]
        new[0].in_active_view = True
        self.refresh_with(new, unsupported=True)
        self.assertEqual(self.w._items, {})
        self.assertEqual(self.w.status_text.Text, "Refreshed: 1 elements")

    # -- actions do not rebuild the tree

    def test_action_updates_m_but_not_tree(self):
        self.select_view_scope()
        self.w._on_click(self.box("Walls"), None)
        items = list(self.w._items)
        self.w.isolate_click(None, None)
        self.view_ids = set([1])  # fresh pre-isolate ids differ
        self.run_events()
        self.assertEqual(list(self.w._items), items)
        self.assertEqual(self.w._view_ids, set([1]))
        self.assertEqual(self.w._scope_ids, set([1, 2]))  # tree still the built view
        self.assertIn("G300", self.names())

    def test_rebuild_after_action_uses_built_view_not_isolated_set(self):
        self.select_view_scope()
        self.w._on_click(self.box("G200"), None)
        self.w.isolate_click(None, None)
        self.view_ids = set([1])  # as if the view now reported only the isolate
        self.run_events()
        self.w._on_level_toggle(None, None)  # any rebuild
        self.assertIn("G300", self.names())


if __name__ == "__main__":
    unittest.main()
