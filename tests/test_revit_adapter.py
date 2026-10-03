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
    def __init__(self, name, ctype=MODEL, parent=None, cid=None):
        self.Name = name
        if cid is not None:
            self.Id = FakeId(cid)
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


class FakeXYZ(object):
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z


class FakeBBox(object):
    def __init__(self, mn=(0, 0, 0), mx=(1, 1, 1)):
        self.Min = FakeXYZ(*mn)
        self.Max = FakeXYZ(*mx)


class FakeElement(object):
    def __init__(self, eid, category, etype=None, bbox=True):
        self.bbox_calls = 0
        self.Id = FakeId(eid)
        self.Category = category
        self._type = etype
        self._bbox = bbox

    def GetTypeId(self):
        return self._type.Id if self._type is not None else INVALID

    def get_BoundingBox(self, view):
        self.bbox_calls += 1
        if self._bbox is True:
            return FakeBBox()
        return self._bbox or None


class FakeViewElement(FakeElement):  # stands in for DB.View subclasses
    pass


class FakeImportInstance(FakeElement):
    pass


class FakeLinkInstance(FakeElement):
    pass


class FakePointCloud(FakeElement):
    pass


class FakeDetailLine(FakeElement):
    ViewSpecific = True


class FakeOwned(FakeElement):  # OwnerViewId only, ViewSpecific absent
    OwnerViewId = FakeId(555)


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

    def test_non_physical_category_excluded_by_id(self):
        cam_cat = FakeCategory("Cameras")
        cam_cat.Id = FakeId(-2000500)
        WALLS.Id = FakeId(-2000011)
        cam = FakeElement(352540, cam_cat, bbox=True)  # plain Element, not a View
        recs = ra.records_from_elements(
            [cam, FakeElement(2, WALLS, WALL_T)], get_type, MODEL,
            excluded_classes=(FakeViewElement,), excluded_category_ids=set([-2000500]))
        self.assertEqual([r.element_id for r in recs], [2])
        # without the exclusion the camera leaks (the bug being fixed)
        self.assertEqual(len(ra.records_from_elements(
            [cam], get_type, MODEL, excluded_classes=(FakeViewElement,))), 1)

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


EXCLUDED = (FakeViewElement, FakeImportInstance, FakeLinkInstance, FakePointCloud)
NON_PHYS_IDS = set([-2000051, -2000160, -2003200, -2003600, -2008107, -2000500])


def cat(name, cid):
    return FakeCategory(name, cid=cid)


def kept_ids(elements):
    return [r.element_id for r in ra.records_from_elements(
        elements, get_type, MODEL, excluded_classes=EXCLUDED,
        excluded_category_ids=NON_PHYS_IDS)]


class ExclusionTests(unittest.TestCase):
    def test_excluded_cases_dropped(self):
        wall = FakeElement(1, cat("Walls", -2000011), WALL_T)
        bad = [
            FakeImportInstance(10, cat("01- Basment Floor.dwg", 900001)),
            FakeLinkInstance(11, cat("RVT Links", -2001352)),
            FakePointCloud(12, cat("Point Clouds", -2001360)),
            FakeDetailLine(13, cat("Lines", -2000051)),
            FakeOwned(14, cat("Generic Annotations2", 77)),
            FakeElement(15, cat("Lines", -2000051)),       # model line
            FakeElement(16, cat("Rooms", -2000160)),
            FakeElement(17, cat("Areas", -2003200)),
            FakeElement(18, cat("MEP Spaces", -2003600)),
            FakeElement(19, cat("HVAC Zones", -2008107)),
        ]
        self.assertEqual(kept_ids([wall] + bad), [1])

    def test_real_building_elements_kept(self):
        els = [
            FakeElement(1, cat("Floors", -2000032), WALL_T),
            FakeElement(2, cat("Walls", -2000011), WALL_T),
            FakeElement(3, cat("Structural Columns", -2001330), DOOR_T),
            FakeElement(4, cat("Stairs", -2000120), WALL_T),
            FakeElement(5, cat("Railings", -2000126), WALL_T),
            FakeElement(6, cat("Ramps", -2000180), WALL_T),   # plain Element
            FakeElement(7, cat("Structural Foundations", -2001300), WALL_T),
        ]
        self.assertEqual(kept_ids(els), [1, 2, 3, 4, 5, 6, 7])

    def test_view_specific_false_or_invalid_owner_kept(self):
        el = FakeElement(1, cat("Walls", -2000011), WALL_T)
        el.ViewSpecific = False
        el.OwnerViewId = INVALID
        self.assertEqual(kept_ids([el]), [1])

    def test_cheap_checks_before_bounding_box(self):
        cheap = [
            FakeImportInstance(1, cat("a.dwg", 9)),
            FakeLinkInstance(2, cat("RVT Links", 8)),
            FakeElement(3, None),
            FakeElement(4, FakeCategory("Tag", ANNOTATION, cid=5)),
            FakeElement(5, FakeCategory("Sub", MODEL, parent=object(), cid=6)),
            FakeElement(6, cat("Lines", -2000051)),
            FakeDetailLine(7, cat("Walls", -2000011)),
            FakeOwned(8, cat("Walls", -2000011)),
        ]
        self.assertEqual(kept_ids(cheap), [])
        self.assertEqual([e.bbox_calls for e in cheap], [0] * len(cheap))
        keep = FakeElement(9, cat("Walls", -2000011), WALL_T)
        kept_ids([keep])
        self.assertEqual(keep.bbox_calls, 1)


class DegenerateBBoxTests(unittest.TestCase):
    MM = 1.0 / 304.8

    def kept(self, bb):
        return kept_ids([FakeElement(1, cat("Railings", -2000126), WALL_T,
                                     bbox=bb)]) == [1]

    def test_helper(self):
        self.assertTrue(ra.is_degenerate_bbox(FakeBBox((0, -1, 0), (0, -1, 0))))
        self.assertFalse(ra.is_degenerate_bbox(FakeBBox((0, 0, 0), (5, 0, 0))))
        self.assertTrue(ra.is_degenerate_bbox(
            FakeBBox((0, 0, 0), (1, 1, 1)), tol=2.0))

    def test_point_bbox_excluded(self):
        self.assertFalse(self.kept(FakeBBox((0, -0.164, 0), (0, -0.164, 0))))

    def test_thin_real_bbox_kept(self):
        t = 5 * self.MM  # 5 mm in one axis only
        self.assertTrue(self.kept(FakeBBox((0, 0, 0), (0, 0, t))))
        self.assertTrue(self.kept(FakeBBox((0, 0, 0), (10, 10, t))))

    def test_normal_bbox_kept(self):
        self.assertTrue(self.kept(FakeBBox()))

    def test_none_bbox_excluded(self):
        self.assertFalse(self.kept(None))


class FakeLevel(object):
    def __init__(self, lid, name, elevation):
        self.Id = FakeId(lid)
        self.Name = name
        self.Elevation = elevation


class FakeParam(object):
    def __init__(self, storage, value):
        self.StorageType = storage
        self._value = value

    def AsElementId(self):
        return self._value


class FakeLeveled(FakeElement):
    def __init__(self, eid, category, level_id=None, params=None, etype=None):
        FakeElement.__init__(self, eid, category, etype)
        self.LevelId = level_id if level_id is not None else INVALID
        self._params = params or {}

    def get_Parameter(self, key):
        return self._params.get(key)


KEYS = ["INST_REF", "RBS_START", "FAMILY_LVL", "SCHED_LVL", "STAIRS_BASE"]


def eid_param(value):
    return FakeParam("ElementId", FakeId(value))


L1 = FakeLevel(10, "Level 1", 0.0)
L2 = FakeLevel(11, "Level 2", 13.12)
ELEMENTS = {10: L1, 11: L2, 500: WALL_T}
ELEMENTS.update({
    700: FakeLeveled(700, WALLS, FakeId(11)),                    # floor
    701: FakeLeveled(701, WALLS, None, {KEYS[4]: eid_param(10)}),  # stair
    702: FakeLeveled(702, WALLS),                                # no level
    703: FakeLeveled(703, WALLS),                                # has a host
})
ELEMENTS[703].HostId = FakeId(700)


def make_resolver(calls=None):
    def get_element(eid):
        if calls is not None:
            calls.append(eid.IntegerValue)
        return ELEMENTS.get(eid.IntegerValue)
    return ra.LevelResolver(get_element, KEYS)


class LevelResolutionTests(unittest.TestCase):
    def name(self, element):
        return make_resolver().level_name(element)

    def test_level_id_first(self):
        el = FakeLeveled(1, WALLS, FakeId(10), {KEYS[0]: eid_param(11)})
        self.assertEqual(self.name(el), "Level 1")

    def test_each_parameter_step(self):
        for key in KEYS:
            el = FakeLeveled(1, WALLS, None, {key: eid_param(11)})
            self.assertEqual(self.name(el), "Level 2", key)

    def test_parameter_order(self):
        el = FakeLeveled(1, WALLS, None, {KEYS[3]: eid_param(11),
                                          KEYS[1]: eid_param(10)})
        self.assertEqual(self.name(el), "Level 1")  # RBS_START before SCHEDULE

    def test_invalid_level_id_falls_through(self):
        el = FakeLeveled(1, WALLS, FakeId(-1), {KEYS[0]: eid_param(10)})
        self.assertEqual(self.name(el), "Level 1")

    def test_level_id_not_a_level_falls_through(self):
        el = FakeLeveled(1, WALLS, FakeId(500), {KEYS[0]: eid_param(11)})
        self.assertEqual(self.name(el), "Level 2")

    def test_missing_element_falls_through(self):
        el = FakeLeveled(1, WALLS, FakeId(999), {KEYS[1]: eid_param(10)})
        self.assertEqual(self.name(el), "Level 1")

    def railing(self, host):
        el = FakeLeveled(1, WALLS)
        el.HostId = FakeId(host) if host is not None else INVALID
        return el

    def test_host_level_fallback(self):
        self.assertEqual(self.name(self.railing(700)), "Level 2")  # floor
        self.assertEqual(self.name(self.railing(701)), "Level 1")  # stair param

    def test_host_without_level_or_invalid_host_is_none(self):
        self.assertIsNone(self.name(self.railing(702)))
        self.assertIsNone(self.name(self.railing(999)))  # unresolvable
        self.assertIsNone(self.name(self.railing(None)))
        self.assertIsNone(self.name(FakeLeveled(1, WALLS)))  # no HostId attr

    def test_own_level_beats_host(self):
        el = self.railing(700)
        el.LevelId = FakeId(10)
        self.assertEqual(self.name(el), "Level 1")

    def test_host_depth_one_no_chaining(self):
        self.assertIsNone(self.name(self.railing(703)))  # 703 -> 700 not followed
        loop = FakeLeveled(704, WALLS)
        loop.HostId = FakeId(704)
        ELEMENTS[704] = loop
        try:
            self.assertIsNone(self.name(self.railing(704)))
        finally:
            del ELEMENTS[704]

    def test_host_cached(self):
        calls = []
        r = make_resolver(calls)
        for _ in range(3):
            self.assertEqual(r.level_name(self.railing(700)), "Level 2")
        self.assertEqual(calls, [700, 11])

    def test_param_rules(self):
        cases = [
            FakeParam("Integer", FakeId(10)),   # wrong storage
            FakeParam("ElementId", INVALID),    # invalid id
            FakeParam("ElementId", FakeId(500)),  # not a level
            FakeParam("ElementId", FakeId(999)),  # unresolvable
            FakeParam("ElementId", None),
        ]
        for p in cases:
            el = FakeLeveled(1, WALLS, None, {KEYS[0]: p, KEYS[2]: eid_param(11)})
            self.assertEqual(self.name(el), "Level 2")
            el = FakeLeveled(1, WALLS, None, {KEYS[0]: p})
            self.assertIsNone(self.name(el))

    def test_no_level_info_is_none_and_becomes_no_level(self):
        el = FakeLeveled(1, WALLS)
        self.assertIsNone(self.name(el))
        recs = ra.records_from_elements([el], get_type, MODEL,
                                        level_resolver=make_resolver())
        self.assertEqual(recs[0].level, "<No Level>")

    def test_cache_and_elevations(self):
        calls = []
        r = make_resolver(calls)
        for i in range(4):
            r.level_name(FakeLeveled(i, WALLS, FakeId(10)))
        r.level_name(FakeLeveled(9, WALLS, None, {KEYS[0]: eid_param(11)}))
        self.assertEqual(calls, [10, 11])
        self.assertEqual(r.elevations, {"Level 1": 0.0, "Level 2": 13.12})

    def test_records_get_levels_order_and_filter(self):
        from advfilter.core import filter_by_levels, ordered_levels
        r = make_resolver()
        els = [FakeLeveled(1, WALLS, FakeId(11), etype=WALL_T),
               FakeLeveled(2, WALLS, FakeId(10), etype=WALL_T),
               FakeLeveled(3, DOORS, None, {KEYS[0]: eid_param(10)}, DOOR_T),
               FakeLeveled(4, DOORS, None, etype=DOOR_T)]
        recs = ra.records_from_elements(els, get_type, MODEL, level_resolver=r)
        self.assertEqual([x.level for x in recs],
                         ["Level 2", "Level 1", "Level 1", "<No Level>"])
        self.assertEqual(ordered_levels(recs, r.elevations),
                         ["Level 1", "Level 2", "<No Level>"])
        tree = build_tree(filter_by_levels(recs, ["Level 2"]))
        self.assertEqual([(n.name, n.count) for n in tree], [("Walls", 1)])


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
