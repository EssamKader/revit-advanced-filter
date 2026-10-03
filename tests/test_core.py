# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "AdvancedFilter.extension", "lib"))

from advfilter.core import (  # noqa: E402
    ElementRecord, build_tree, iter_element_ids, NO_FAMILY, NO_TYPE, NO_LEVEL,
    filter_by_levels, ordered_levels, checked_paths, apply_checked_paths,
    checked_element_ids, merge_checked_paths, set_checked, click_target,
    search_visibility)


def rec(eid, cat, fam, typ, in_view=True):
    return ElementRecord(eid, cat, fam, typ, in_view)


def names(nodes):
    return [n.name for n in nodes]


class BuildTreeTests(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(build_tree([]), [])
        self.assertEqual(build_tree(iter([])), [])

    def test_loadable_family(self):
        tree = build_tree([
            rec(1, "Doors", "Single-Flush", "0915 x 2134mm"),
            rec(2, "Doors", "Single-Flush", "0915 x 2134mm"),
            rec(3, "Doors", "Single-Flush", "1000 x 2100mm"),
        ])
        self.assertEqual(names(tree), ["Doors"])
        fam = tree[0].children[0]
        self.assertEqual(fam.name, "Single-Flush")
        self.assertEqual(names(fam.children), ["0915 x 2134mm", "1000 x 2100mm"])
        self.assertEqual(fam.children[0].element_ids, [1, 2])
        self.assertEqual(fam.children[1].element_ids, [3])

    def test_system_family(self):
        tree = build_tree([rec(10, "Walls", "Basic Wall", "Generic - 200mm")])
        cat = tree[0]
        self.assertEqual((cat.name, cat.level), ("Walls", "category"))
        fam = cat.children[0]
        self.assertEqual((fam.name, fam.level), ("Basic Wall", "family"))
        typ = fam.children[0]
        self.assertEqual((typ.name, typ.level), ("Generic - 200mm", "type"))
        self.assertIs(typ.parent, fam)
        self.assertIs(fam.parent, cat)
        self.assertIsNone(cat.parent)

    def test_untyped_elements_not_dropped(self):
        tree = build_tree([
            rec(1, "Generic Models", None, None),
            rec(2, "Generic Models", "", "  "),
            rec(3, "Generic Models", "   ", "T1"),
            rec(4, "Generic Models", "F1", None),
        ])
        cat = tree[0]
        self.assertEqual(cat.count, 4)
        self.assertEqual(names(cat.children), [NO_FAMILY, "F1"])
        nofam = cat.children[0]
        self.assertEqual(names(nofam.children), [NO_TYPE, "T1"])
        self.assertEqual(sorted(nofam.children[0].element_ids), [1, 2])
        self.assertEqual(cat.children[1].children[0].name, NO_TYPE)

    def test_same_type_name_different_families_separate(self):
        tree = build_tree([
            rec(1, "Doors", "FamA", "Standard"),
            rec(2, "Doors", "FamB", "Standard"),
        ])
        fams = tree[0].children
        self.assertEqual(names(fams), ["FamA", "FamB"])
        self.assertEqual(fams[0].children[0].element_ids, [1])
        self.assertEqual(fams[1].children[0].element_ids, [2])

    def test_same_family_name_different_categories_separate(self):
        tree = build_tree([
            rec(1, "Doors", "Generic", "T"),
            rec(2, "Windows", "Generic", "T"),
        ])
        self.assertEqual(names(tree), ["Doors", "Windows"])
        self.assertEqual(tree[0].children[0].children[0].element_ids, [1])
        self.assertEqual(tree[1].children[0].children[0].element_ids, [2])

    def test_counts_all_levels(self):
        tree = build_tree([
            rec(1, "Doors", "F1", "A"),
            rec(2, "Doors", "F1", "A"),
            rec(3, "Doors", "F1", "B"),
            rec(4, "Doors", "F2", "A"),
            rec(5, "Walls", "Basic Wall", "W1"),
        ])
        doors, walls = tree
        self.assertEqual(doors.count, 4)
        self.assertEqual(walls.count, 1)
        f1, f2 = doors.children
        self.assertEqual((f1.count, f2.count), (3, 1))
        self.assertEqual([t.count for t in f1.children], [2, 1])
        self.assertEqual(f2.children[0].count, 1)

    def test_case_insensitive_sorting(self):
        tree = build_tree([
            rec(1, "walls", "beta", "b"),
            rec(2, "Windows", "Alpha", "C"),
            rec(3, "Doors", "alpha", "a"),
            rec(4, "walls", "Alpha", "B"),
            rec(5, "walls", "Alpha", "a"),
        ])
        self.assertEqual(names(tree), ["Doors", "walls", "Windows"])
        walls = tree[1]
        self.assertEqual(names(walls.children), ["Alpha", "beta"])
        self.assertEqual(names(walls.children[0].children), ["a", "B"])

    def test_checked_defaults_false(self):
        tree = build_tree([rec(1, "Doors", "F", "T")])
        self.assertFalse(tree[0].checked)
        self.assertFalse(tree[0].children[0].children[0].checked)

    def test_accepts_generator(self):
        tree = build_tree(rec(i, "Doors", "F", "T") for i in range(3))
        self.assertEqual(tree[0].count, 3)


class IterElementIdsTests(unittest.TestCase):
    def setUp(self):
        self.tree = build_tree([
            rec(1, "Doors", "F1", "A"),
            rec(2, "Doors", "F1", "B"),
            rec(3, "Doors", "F2", "A"),
            rec(4, "Walls", "Basic Wall", "W1"),
        ])

    def test_category(self):
        self.assertEqual(sorted(iter_element_ids(self.tree[0])), [1, 2, 3])

    def test_family(self):
        self.assertEqual(sorted(iter_element_ids(self.tree[0].children[0])), [1, 2])

    def test_type(self):
        self.assertEqual(list(iter_element_ids(self.tree[1].children[0].children[0])), [4])

    def test_total_matches_count(self):
        for node in self.tree:
            self.assertEqual(len(list(iter_element_ids(node))), node.count)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        from advfilter.core import checked_element_ids, ids_in_view
        self.checked_ids = checked_element_ids
        self.in_view = ids_in_view
        self.tree = build_tree([
            rec(1, "Walls", "Basic Wall", "Generic - 200"),
            rec(2, "Walls", "Basic Wall", "Generic - 300"),
            rec(3, "Doors", "Single", "0915"),
            rec(4, "Doors", "Single", "0915"),
        ])

    def test_nothing_checked(self):
        self.assertEqual(self.checked_ids(self.tree), [])

    def test_checked_category_covers_all_descendants(self):
        walls = [n for n in self.tree if n.name == "Walls"][0]
        walls.checked = True
        self.assertEqual(sorted(self.checked_ids(self.tree)), [1, 2])

    def test_checked_type_only(self):
        doors = [n for n in self.tree if n.name == "Doors"][0]
        doors.children[0].children[0].checked = True
        self.assertEqual(sorted(self.checked_ids(self.tree)), [3, 4])

    def test_parent_and_child_checked_deduplicated(self):
        walls = [n for n in self.tree if n.name == "Walls"][0]
        walls.checked = True
        walls.children[0].children[0].checked = True
        ids = self.checked_ids(self.tree)
        self.assertEqual(sorted(ids), [1, 2])
        self.assertEqual(len(ids), 2)

    def test_ids_in_view_intersection(self):
        self.assertEqual(self.in_view([1, 2, 3], set([2, 3, 9])), [2, 3])
        self.assertEqual(self.in_view([1], set()), [])


def lrec(eid, cat, fam, typ, level):
    return ElementRecord(eid, cat, fam, typ, True, level)


def all_nodes(roots):
    for n in roots:
        yield n
        for sub in all_nodes(n.children):
            yield sub


LEVEL_RECS = [
    lrec(1, "Walls", "Basic Wall", "W200", "L1"),
    lrec(2, "Walls", "Basic Wall", "W200", "L2"),
    lrec(3, "Walls", "Curtain", "CW", "L1"),
    lrec(4, "Doors", "Single", "D1", "L1"),
    lrec(5, "Doors", "Single", "D1", None),
    lrec(6, "Floors", "Floor", "F150", "L2"),
]


class LevelTests(unittest.TestCase):
    def test_blank_level_is_no_level(self):
        for v in (None, "", "   "):
            self.assertEqual(lrec(1, "A", "B", "C", v).level, NO_LEVEL)
        self.assertEqual(ElementRecord(1, "A").level, NO_LEVEL)
        self.assertEqual(lrec(1, "A", "B", "C", " L1 ").level, "L1")

    def test_filter_none_or_empty_is_all(self):
        self.assertEqual(len(filter_by_levels(LEVEL_RECS, None)), 6)
        self.assertEqual(len(filter_by_levels(LEVEL_RECS, [])), 6)

    def test_filter_single_and_multiple(self):
        self.assertEqual([r.element_id for r in filter_by_levels(LEVEL_RECS, ["L2"])], [2, 6])
        got = filter_by_levels(LEVEL_RECS, ["L2", NO_LEVEL])
        self.assertEqual([r.element_id for r in got], [2, 5, 6])

    def test_filter_unknown_level_is_empty(self):
        self.assertEqual(filter_by_levels(LEVEL_RECS, ["Nope"]), [])

    def test_counts_reflect_selected_levels(self):
        tree = build_tree(filter_by_levels(LEVEL_RECS, ["L1"]))
        self.assertEqual([(n.name, n.count) for n in tree],
                         [("Doors", 1), ("Walls", 2)])

    def test_no_zero_count_or_empty_nodes_after_filtering(self):
        for sel in (["L1"], ["L2"], [NO_LEVEL], ["L1", "L2"], ["Nope"], None):
            tree = build_tree(filter_by_levels(LEVEL_RECS, sel))
            for node in all_nodes(tree):
                self.assertGreater(node.count, 0, (sel, node))
                if node.level != "type":
                    self.assertTrue(node.children, (sel, node))

    def test_family_only_on_l1_vanishes_on_l2(self):
        tree = build_tree(filter_by_levels(LEVEL_RECS, ["L2"]))
        walls = [n for n in tree if n.name == "Walls"][0]
        self.assertEqual([f.name for f in walls.children], ["Basic Wall"])
        self.assertEqual([n.name for n in tree], ["Floors", "Walls"])

    def test_ordered_levels_by_elevation_no_level_last(self):
        recs = [lrec(1, "A", "B", "C", n) for n in ("L3", None, "L1", "L2", "L1")]
        el = {"L1": 0.0, "L2": 13.1, "L3": -5.0, "Unused": 99.0}
        self.assertEqual(ordered_levels(recs, el), ["L3", "L1", "L2", NO_LEVEL])

    def test_ordered_levels_only_existing(self):
        recs = [lrec(1, "A", "B", "C", "L1")]
        self.assertEqual(ordered_levels(recs, {"L1": 0, "L2": 5}), ["L1"])

    def test_ordered_levels_missing_elevation_after_known_by_name(self):
        recs = [lrec(i, "A", "B", "C", n) for i, n in enumerate(("zz", "Aa", "L1", None))]
        self.assertEqual(ordered_levels(recs, {"L1": 0}), ["L1", "Aa", "zz", NO_LEVEL])


class CheckStatePreservationTests(unittest.TestCase):
    def test_paths_roundtrip_across_level_rebuild(self):
        tree = build_tree(LEVEL_RECS)
        walls = [n for n in tree if n.name == "Walls"][0]
        walls.children[0].checked = True               # family Basic Wall -> W200
        floors = [n for n in tree if n.name == "Floors"][0]
        floors.checked = True
        saved = checked_paths(tree)
        self.assertEqual(saved, set([
            ("Walls", "Basic Wall", "W200"), ("Floors", "Floor", "F150")]))

        new_tree = build_tree(filter_by_levels(LEVEL_RECS, ["L1"]))
        apply_checked_paths(new_tree, saved)
        # Floors has nothing on L1 -> gone; Walls/Basic Wall/W200 survive.
        self.assertEqual(names(new_tree), ["Doors", "Walls"])
        self.assertEqual(sorted(checked_element_ids(new_tree)), [1])
        self.assertEqual(checked_paths(new_tree), set([
            ("Walls", "Basic Wall", "W200")]))

    def test_state_restored_when_level_comes_back(self):
        tree = build_tree(filter_by_levels(LEVEL_RECS, ["L1"]))
        apply_checked_paths(tree, set([("Walls", "Curtain", "CW")]))
        saved = checked_paths(tree)
        again = build_tree(LEVEL_RECS)
        apply_checked_paths(again, saved)
        self.assertEqual(checked_element_ids(again), [3])

    def test_hide_and_restore_keeps_check(self):
        memory = set()
        tree = build_tree(LEVEL_RECS)
        apply_checked_paths(tree, memory)
        [n for n in tree if n.name == "Walls"][0].children[1].checked = True  # Curtain (L1 only)
        memory = merge_checked_paths(memory, tree)
        hidden = build_tree(filter_by_levels(LEVEL_RECS, ["L2"]))
        apply_checked_paths(hidden, memory)
        memory = merge_checked_paths(memory, hidden)  # Curtain not visible: kept
        self.assertIn(("Walls", "Curtain", "CW"), memory)
        back = build_tree(LEVEL_RECS)
        apply_checked_paths(back, memory)
        self.assertEqual(checked_element_ids(back), [3])

    def test_unchecking_visible_node_forgets_it(self):
        tree = build_tree(LEVEL_RECS)
        apply_checked_paths(tree, set([("Walls", "Curtain", "CW")]))
        memory = merge_checked_paths(set([("Walls", "Curtain", "CW")]), tree)
        self.assertEqual(memory, set([("Walls", "Curtain", "CW")]))
        [n for n in tree if n.name == "Walls"][0].children[1].checked = False
        memory = merge_checked_paths(memory, tree)
        self.assertEqual(memory, set())

    def test_empty_selection_tree_has_nothing_to_isolate(self):
        tree = build_tree([])
        apply_checked_paths(tree, set([("Walls", "Curtain", "CW")]))
        self.assertEqual(checked_element_ids(tree), [])


class TriStateTests(unittest.TestCase):
    def setUp(self):
        self.tree = build_tree([
            rec(1, "Walls", "Basic Wall", "W200"),
            rec(2, "Walls", "Basic Wall", "W300"),
            rec(3, "Walls", "Curtain", "CW"),
            rec(4, "Doors", "Single", "D1"),
        ])
        self.walls = [n for n in self.tree if n.name == "Walls"][0]
        self.basic = self.walls.children[0]
        self.w200, self.w300 = self.basic.children
        self.curtain = self.walls.children[1]

    def test_all_unchecked_by_default(self):
        self.assertIs(self.walls.state, False)
        self.assertIs(self.w200.state, False)

    def test_down_propagation_from_category(self):
        set_checked(self.walls, True)
        for n in all_nodes([self.walls]):
            self.assertIs(n.state, True)
        set_checked(self.walls, False)
        for n in all_nodes([self.walls]):
            self.assertIs(n.state, False)

    def test_down_propagation_from_family(self):
        set_checked(self.basic, True)
        self.assertIs(self.w200.state, True)
        self.assertIs(self.w300.state, True)
        self.assertIs(self.curtain.state, False)

    def test_up_derivation_mixed_is_none(self):
        set_checked(self.w200, True)
        self.assertIs(self.basic.state, None)
        self.assertIs(self.walls.state, None)
        self.assertIs(self.curtain.state, False)

    def test_up_derivation_all_children_checked(self):
        set_checked(self.w200, True)
        set_checked(self.w300, True)
        self.assertIs(self.basic.state, True)
        self.assertIs(self.walls.state, None)  # Curtain still unchecked
        set_checked(self.curtain, True)
        self.assertIs(self.walls.state, True)

    def test_up_derivation_back_to_none(self):
        set_checked(self.walls, True)
        set_checked(self.w300, False)
        self.assertIs(self.basic.state, None)
        set_checked(self.w200, False)
        self.assertIs(self.basic.state, False)
        self.assertIs(self.walls.state, None)  # Curtain still checked

    def test_click_on_indeterminate_checks_everything(self):
        set_checked(self.w200, True)
        self.assertIs(self.walls.state, None)
        set_checked(self.walls, click_target(self.walls))
        for n in all_nodes([self.walls]):
            self.assertIs(n.state, True)

    def test_click_on_checked_unchecks_and_unchecked_checks(self):
        self.assertTrue(click_target(self.walls))
        set_checked(self.walls, True)
        self.assertFalse(click_target(self.walls))

    def test_checked_property_is_fully_checked_only(self):
        set_checked(self.w200, True)
        self.assertFalse(self.basic.checked)
        self.basic.checked = True
        self.assertTrue(self.w300.checked)

    def test_element_ids_mixed_states(self):
        set_checked(self.w200, True)
        set_checked(self.curtain, True)
        self.assertEqual(checked_element_ids(self.tree), [1, 3])

    def test_element_ids_deduplicated_and_stable(self):
        tree = build_tree([rec(5, "A", "F", "T"), rec(5, "A", "F", "T"),
                           rec(1, "A", "F", "U")])
        set_checked(tree[0], True)
        self.assertEqual(checked_element_ids(tree), [5, 1])

    def test_leaf_rule_new_leaves_come_in_unchecked(self):
        l1 = build_tree(filter_by_levels(LEVEL_RECS, ["L1"]))
        walls = [n for n in l1 if n.name == "Walls"][0]
        set_checked(walls, True)  # Basic Wall/W200 (1), Curtain/CW (3)
        memory = merge_checked_paths(set(), l1)
        both = build_tree(LEVEL_RECS)
        apply_checked_paths(both, memory)
        walls2 = [n for n in both if n.name == "Walls"][0]
        self.assertIs(walls2.state, True)  # all Walls leaves exist on L1
        # Add a type that only exists on L2 and rebuild.
        recs = LEVEL_RECS + [lrec(7, "Walls", "Basic Wall", "W400", "L2")]
        grown = build_tree(recs)
        apply_checked_paths(grown, memory)
        walls3 = [n for n in grown if n.name == "Walls"][0]
        self.assertIs(walls3.state, None)
        self.assertEqual(sorted(checked_element_ids(grown)), [1, 2, 3])  # W400 (7) unchecked

    def test_parent_paths_in_memory_are_ignored(self):
        tree = build_tree(LEVEL_RECS)
        apply_checked_paths(tree, set([("Walls",), ("Walls", "Curtain")]))
        self.assertEqual(checked_element_ids(tree), [])


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tree = build_tree([
            rec(1, "Walls", "Basic Wall", "Generic 200"),
            rec(2, "Walls", "Basic Wall", "Generic 300"),
            rec(3, "Walls", "Curtain Wall", "Storefront"),
            rec(4, "Doors", "Single Flush", "0915 x 2134"),
            rec(5, "Doors", "Double", "1830 x 2134"),
        ])
        self.doors, self.walls = self.tree
        self.basic, self.curtain = self.walls.children
        self.g200, self.g300 = self.basic.children
        self.store = self.curtain.children[0]
        self.single, self.double = [
            f for f in self.doors.children if f.name in ("Single Flush", "Double")]

    def vis(self, query):
        return search_visibility(self.tree, query)

    def test_empty_and_blank_mean_all_visible(self):
        self.assertIsNone(self.vis(""))
        self.assertIsNone(self.vis("   "))
        self.assertIsNone(self.vis(None))

    def test_category_match_shows_all_descendants(self):
        v = self.vis("walls")
        self.assertEqual(v, set(all_nodes([self.walls])))
        self.assertNotIn(self.doors, v)

    def test_family_match_shows_types_and_category(self):
        v = self.vis("basic")
        self.assertEqual(v, set([self.walls, self.basic, self.g200, self.g300]))

    def test_type_match_shows_ancestors_only(self):
        v = self.vis("storefront")
        self.assertEqual(v, set([self.walls, self.curtain, self.store]))

    def test_case_insensitive(self):
        self.assertEqual(self.vis("STOREFRONT"), self.vis("storefront"))
        self.assertEqual(self.vis("dOORS"), set(all_nodes([self.doors])))

    def test_query_is_trimmed(self):
        self.assertEqual(self.vis("  storefront 	"), self.vis("storefront"))

    def test_substring_match_in_middle(self):
        self.assertEqual(self.vis("eneri"),
                         set([self.walls, self.basic, self.g200, self.g300]))

    def test_multiple_matches_union(self):
        v = self.vis("2134")
        self.assertIn(self.single, v)
        self.assertIn(self.double, v)
        self.assertNotIn(self.walls, v)

    def test_no_match_gives_empty_set_not_none(self):
        self.assertEqual(self.vis("zzz"), set())

    def test_search_does_not_change_check_state(self):
        set_checked(self.g200, True)
        before = checked_paths(self.tree)
        self.vis("doors")
        self.vis("zzz")
        self.assertEqual(checked_paths(self.tree), before)
        self.assertIs(self.basic.state, None)

    def test_hidden_checked_leaf_survives_and_clear_restores(self):
        set_checked(self.g200, True)
        v = self.vis("storefront")
        self.assertNotIn(self.g200, v)
        self.assertEqual(checked_element_ids(self.tree), [1])
        self.assertIsNone(self.vis(""))

    def test_set_checked_under_search_only_touches_visible_leaves(self):
        v = self.vis("generic 200")
        set_checked(self.walls, True, v)
        self.assertIs(self.g200.state, True)
        self.assertIs(self.g300.state, False)
        self.assertIs(self.store.state, False)
        self.assertIs(self.walls.state, None)  # parent shows full state

    def test_set_checked_uncheck_under_search_keeps_hidden_checks(self):
        set_checked(self.walls, True)
        v = self.vis("generic 200")
        set_checked(self.walls, False, v)
        self.assertIs(self.g200.state, False)
        self.assertIs(self.g300.state, True)
        self.assertIs(self.store.state, True)

    def test_click_target_evaluated_over_visible_leaves(self):
        v = self.vis("generic 200")
        self.assertIs(click_target(self.walls, v), True)
        set_checked(self.walls, True, v)
        # Visible leaves all checked -> next click unchecks, though the
        # category itself is only partially checked overall.
        self.assertIs(self.walls.state, None)
        self.assertIs(click_target(self.walls, v), False)
        self.assertIs(click_target(self.walls), True)  # no search: full state

    def test_click_target_no_visible_leaves_is_true(self):
        self.assertIs(click_target(self.doors, set()), True)

    def test_visible_none_behaves_as_before(self):
        set_checked(self.walls, True, None)
        self.assertIs(self.walls.state, True)
        self.assertIs(click_target(self.walls, None), False)


if __name__ == "__main__":
    unittest.main()
