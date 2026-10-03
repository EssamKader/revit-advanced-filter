# -*- coding: utf-8 -*-
"""Mock-object verification of advfilter.revit_adapter (no Revit needed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "AdvancedFilter.extension", "lib"))

from advfilter import revit_adapter as ra  # noqa: E402
from advfilter.core import build_tree, NO_FAMILY, NO_TYPE  # noqa: E402

MODEL = "Model"
ANNOTATION = "Annotation"


class FakeId(object):
    def __init__(self, value):
        self.IntegerValue = value


INVALID = FakeId(-1)


class FakeCategory(object):
    def __init__(self, name, ctype=MODEL, parent=None):
        self.Name = name
        self.CategoryType = ctype
        self.Parent = parent


class FakeFamily(object):
    def __init__(self, name):
        self.Name = name


class FakeSymbol(object):  # loadable family type: has .Family
    def __init__(self, tid, family, name):
        self.Id = FakeId(tid)
        self.Family = FakeFamily(family)
        self.FamilyName = family
        self.Name = name


class FakeElementType(object):  # system family type: no .Family
    def __init__(self, tid, family_name, name):
        self.Id = FakeId(tid)
        self.FamilyName = family_name
        self.Name = name


class FakeElement(object):
    def __init__(self, eid, category, etype=None, bbox=True):
        self.Id = FakeId(eid)
        self.Category = category
        self._type = etype
        self._bbox = bbox

    def GetTypeId(self):
        return self._type.Id if self._type is not None else INVALID

    def get_BoundingBox(self, view):
        return object() if self._bbox else None


class FakeViewElement(FakeElement):  # stands in for DB.View subclasses
    pass


class FakeView(object):
    def __init__(self, view_type="FloorPlan", template=False, can_temp=True):
        self.ViewType = view_type
        self.IsTemplate = template
        self._can = can_temp

    def CanUseTemporaryVisibilityModes(self):
        return self._can


WALLS = FakeCategory("Walls")
DOORS = FakeCategory("Doors")
WALL_T = FakeElementType(100, "Basic Wall", "Generic - 200mm")
DOOR_T = FakeSymbol(200, "Single-Flush", "0915 x 2134")
TYPES = dict((t.Id.IntegerValue, t) for t in (WALL_T, DOOR_T))


def get_type(type_id):
    return TYPES.get(type_id.IntegerValue)


def records(elements, view_ids=None):
    return ra.records_from_elements(elements, get_type, MODEL, view_ids,
                                    FakeViewElement)


class MappingTests(unittest.TestCase):
    def test_loadable_family_uses_family_and_symbol_names(self):
        r = records([FakeElement(1, DOORS, DOOR_T)])[0]
        self.assertEqual((r.element_id, r.category, r.family, r.type_name),
                         (1, "Doors", "Single-Flush", "0915 x 2134"))

    def test_system_family_uses_type_familyname(self):
        r = records([FakeElement(2, WALLS, WALL_T)])[0]
        self.assertEqual((r.family, r.type_name),
                         ("Basic Wall", "Generic - 200mm"))

    def test_untyped_goes_to_buckets_not_dropped(self):
        recs = records([FakeElement(3, DOORS, None)])
        self.assertEqual(len(recs), 1)
        self.assertEqual((recs[0].family, recs[0].type_name), (None, None))
        tree = build_tree(recs)
        self.assertEqual(tree[0].children[0].name, NO_FAMILY)
        self.assertEqual(tree[0].children[0].children[0].name, NO_TYPE)

    def test_missing_type_element_is_untyped(self):
        ghost = FakeElementType(999, "X", "Y")  # not in TYPES
        r = records([FakeElement(4, WALLS, ghost)])[0]
        self.assertEqual((r.family, r.type_name), (None, None))

    def test_annotation_category_excluded(self):
        tag = FakeCategory("Wall Tags", ANNOTATION)
        self.assertEqual(records([FakeElement(5, tag, WALL_T)]), [])

    def test_no_category_excluded(self):
        self.assertEqual(records([FakeElement(6, None)]), [])

    def test_subcategory_excluded(self):
        sub = FakeCategory("Primary Contours", MODEL, parent=FakeCategory("Topography"))
        self.assertEqual(records([FakeElement(7, sub)]), [])

    def test_model_category_without_geometry_excluded(self):
        mat = FakeCategory("Materials")
        self.assertEqual(records([FakeElement(8, mat, bbox=False)]), [])

    def test_view_element_excluded_despite_model_category_and_bbox(self):
        cameras = FakeCategory("Cameras")
        view3d = FakeViewElement(352540, cameras, bbox=True)
        recs = records([view3d, FakeElement(2, WALLS, WALL_T)])
        self.assertEqual([r.element_id for r in recs], [2])

    def test_view_check_skipped_when_no_view_class(self):
        self.assertTrue(ra.is_model_element(
            FakeViewElement(9, FakeCategory("Cameras")), MODEL))

    def test_element_types_not_in_instance_collection(self):
        # WhereElementIsNotElementType does that at the collector level;
        # a type object that slips through has no category -> excluded.
        wall_type_as_element = FakeElement(100, None, None)
        self.assertEqual(records([wall_type_as_element]), [])

    def test_in_active_view_flag(self):
        recs = records([FakeElement(1, DOORS, DOOR_T),
                        FakeElement(2, WALLS, WALL_T)], view_ids=set([2]))
        self.assertEqual([(r.element_id, r.in_active_view) for r in recs],
                         [(1, False), (2, True)])

    def test_type_lookup_is_cached(self):
        calls = []

        def counting(type_id):
            calls.append(type_id.IntegerValue)
            return get_type(type_id)
        els = [FakeElement(i, WALLS, WALL_T) for i in range(5)]
        ra.records_from_elements(els, counting, MODEL)
        self.assertEqual(calls, [100])

    def test_end_to_end_tree(self):
        els = [FakeElement(1, WALLS, WALL_T), FakeElement(2, WALLS, WALL_T),
               FakeElement(3, DOORS, DOOR_T)]
        tree = build_tree(records(els))
        self.assertEqual([(n.name, n.count) for n in tree],
                         [("Doors", 1), ("Walls", 2)])


class ViewGuardTests(unittest.TestCase):
    def test_ok_view(self):
        self.assertIsNone(ra.view_isolate_problem(FakeView()))

    def test_no_view(self):
        self.assertIn("no active view", ra.view_isolate_problem(None))

    def test_template(self):
        self.assertIn("template", ra.view_isolate_problem(FakeView(template=True)))

    def test_unsupported_types(self):
        for vt in ("Schedule", "DrawingSheet", "Legend", "ProjectBrowser",
                   "SystemBrowser", "Internal", "Undefined"):
            self.assertIsNotNone(ra.view_isolate_problem(FakeView(vt)), vt)

    def test_cannot_use_temp_modes(self):
        self.assertIsNotNone(ra.view_isolate_problem(FakeView(can_temp=False)))

    def test_other_view_types_ok(self):
        for vt in ("FloorPlan", "ThreeD", "Section", "Elevation", "CeilingPlan"):
            self.assertIsNone(ra.view_isolate_problem(FakeView(vt)), vt)


if __name__ == "__main__":
    unittest.main()
