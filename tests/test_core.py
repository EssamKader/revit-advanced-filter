# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "AdvancedFilter.extension", "lib"))

from advfilter.core import (  # noqa: E402
    ElementRecord, build_tree, iter_element_ids, NO_FAMILY, NO_TYPE)


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


if __name__ == "__main__":
    unittest.main()
