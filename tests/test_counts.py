# -*- coding: utf-8 -*-
"""selection_counts / hidden_notice (pure core)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "AdvancedFilter.extension", "lib"))

from advfilter import core  # noqa: E402


def rec(eid, cat, fam, typ, level="L1"):
    return core.ElementRecord(eid, cat, fam, typ, True, level)


RECORDS = [rec(1, "Walls", "Basic", "G200"), rec(2, "Walls", "Basic", "G200"),
           rec(3, "Walls", "Basic", "G300"), rec(4, "Doors", "S", "D1"),
           rec(5, "Doors", "S", "D2", level="L2")]


def node(roots, name):
    stack = list(roots)
    while stack:
        n = stack.pop()
        if n.name == name:
            return n
        stack.extend(n.children)


class SelectionCountsTests(unittest.TestCase):
    def setUp(self):
        self.roots = core.build_tree(RECORDS)
        self.view = set([1, 3, 4])

    def test_nothing_checked(self):
        self.assertEqual(core.selection_counts(self.roots, self.view), (0, 0))

    def test_single_type(self):
        core.set_checked(node(self.roots, "G200"), True)
        self.assertEqual(core.selection_counts(self.roots, self.view), (2, 1))

    def test_category_and_all(self):
        core.set_checked(node(self.roots, "Walls"), True)
        self.assertEqual(core.selection_counts(self.roots, self.view), (3, 2))
        for r in self.roots:
            core.set_checked(r, True)
        self.assertEqual(core.selection_counts(self.roots, self.view), (5, 3))

    def test_none_in_view(self):
        core.set_checked(node(self.roots, "D2"), True)
        self.assertEqual(core.selection_counts(self.roots, self.view), (1, 0))

    def test_distinct_ids(self):
        core.set_checked(node(self.roots, "G200"), True)
        node(self.roots, "G300").element_ids.append(1)  # duplicate id
        core.set_checked(node(self.roots, "G300"), True)
        self.assertEqual(core.selection_counts(self.roots, self.view), (3, 2))

    def test_level_filter(self):
        roots = core.build_tree(core.filter_by_levels(RECORDS, ["L1"]))
        for r in roots:
            core.set_checked(r, True)
        self.assertEqual(core.selection_counts(roots, self.view), (4, 3))

    def test_search_does_not_change_counts(self):
        core.set_checked(node(self.roots, "Walls"), True)
        before = core.selection_counts(self.roots, self.view)
        visible = core.search_visibility(self.roots, "door")
        self.assertIsNotNone(visible)
        self.assertEqual(core.selection_counts(self.roots, self.view), before)

    def test_empty_view_set(self):
        core.set_checked(node(self.roots, "Walls"), True)
        self.assertEqual(core.selection_counts(self.roots, set()), (3, 0))


class HiddenNoticeTests(unittest.TestCase):
    def test_none_when_all_visible(self):
        self.assertIsNone(core.hidden_notice(3, 3))
        self.assertIsNone(core.hidden_notice(0, 0))

    def test_text(self):
        self.assertEqual(
            core.hidden_notice(5, 3),
            "2 matched element(s) are not visible in the active view "
            "and were not isolated.")


if __name__ == "__main__":
    unittest.main()
