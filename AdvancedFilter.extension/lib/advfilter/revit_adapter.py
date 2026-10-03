# -*- coding: utf-8 -*-
"""Revit 2024 adapter: Revit elements -> core.ElementRecord.

Autodesk.* is imported lazily (only by the thin collector functions) so the
mapping logic below stays importable and testable under CPython with fakes.
"""
from advfilter.core import ElementRecord

# ViewType names (compared as strings) that can never take temporary isolate.
_UNSUPPORTED_VIEW_TYPES = (
    "Schedule", "DrawingSheet", "Legend", "ProjectBrowser", "SystemBrowser",
    "Internal", "Undefined", "Report", "PanelSchedule", "CostReport",
    "LoadsReport", "ColumnSchedule",
)


# Model-category elements that carry geometry but are not physical objects.
_NON_PHYSICAL_CATEGORIES = ("OST_Cameras",)


def non_physical_category_ids():
    """Int ids of _NON_PHYSICAL_CATEGORIES (names missing in this Revit are skipped)."""
    from Autodesk.Revit.DB import BuiltInCategory
    return set(int(getattr(BuiltInCategory, n)) for n in _NON_PHYSICAL_CATEGORIES
               if hasattr(BuiltInCategory, n))


def _id_int(element_id):
    return element_id.IntegerValue


def element_name(element):
    """Name of an Element; avoids the IronPython ElementType.Name pitfall."""
    try:
        return element.Name
    except Exception:
        from Autodesk.Revit.DB import Element
        return Element.Name.GetValue(element)


def view_isolate_problem(view):
    """None if temporary isolate works in view, else a user-facing message."""
    if view is None:
        return "There is no active view."
    if view.IsTemplate:
        return "The active view is a view template. Open a regular view."
    view_type = str(view.ViewType)
    if view_type in _UNSUPPORTED_VIEW_TYPES:
        return ("Temporary isolate is not available in this view type (%s). "
                "Open a plan, section, elevation, 3D or similar view." % view_type)
    if not view.CanUseTemporaryVisibilityModes():
        return ("Temporary hide/isolate is not available in the active view. "
                "Open a plan, section, elevation, 3D or similar view.")
    return None


def is_model_element(element, model_category_type, view_class=None,
                     excluded_category_ids=None):
    """True for top-level Model-category elements that have model geometry.

    Live check showed Model-category non-geometric database elements
    (Materials, Project Information, Sun Path, Legend Components, ...) with
    no bounding box; they cannot be isolated, so they are skipped. View
    elements (e.g. 3D views, category Cameras) report a Model category and a
    bounding box but are not geometry, so view_class (DB.View) excludes them.
    """
    if view_class is not None and isinstance(element, view_class):
        return False
    cat = element.Category
    if cat is None or cat.CategoryType != model_category_type:
        return False
    if cat.Parent is not None:  # subcategory
        return False
    if excluded_category_ids and _id_int(cat.Id) in excluded_category_ids:
        return False
    return element.get_BoundingBox(None) is not None


def type_names(element, get_type, cache=None):
    """(family, type) names for an instance; (None, None) when untyped."""
    type_id = element.GetTypeId()
    if type_id is None or _id_int(type_id) == -1:
        return None, None
    key = _id_int(type_id)
    if cache is not None and key in cache:
        return cache[key]
    result = _names_of_type(get_type(type_id))
    if cache is not None:
        cache[key] = result
    return result


def _names_of_type(etype):
    if etype is None:
        return None, None
    symbol_family = getattr(etype, "Family", None)  # FamilySymbol only
    if symbol_family is not None:
        family = element_name(symbol_family)
    else:
        family = getattr(etype, "FamilyName", None)
    return family, element_name(etype)


class LevelResolver(object):
    """Resolves the level name of an element, caching level id -> (name, elevation).

    Order: Element.LevelId, then each parameter key in param_keys. A
    parameter counts only if it has ElementId storage, holds a valid id and
    that id resolves to a Level. get_element and param_keys are injected so
    the logic runs against fakes.
    """

    def __init__(self, get_element, param_keys, level_class=None):
        self._get_element = get_element
        self._param_keys = list(param_keys)
        self._level_class = level_class
        self._cache = {}  # level id int -> (name, elevation) or None
        self.elevations = {}  # level name -> elevation

    def _is_level(self, obj):
        if obj is None:
            return False
        if self._level_class is not None:
            return isinstance(obj, self._level_class)
        return hasattr(obj, "Elevation")

    def _lookup(self, element_id):
        if element_id is None or _id_int(element_id) == -1:
            return None
        key = _id_int(element_id)
        if key not in self._cache:
            level = self._get_element(element_id)
            if self._is_level(level):
                name = element_name(level)
                self._cache[key] = name
                self.elevations[name] = level.Elevation
            else:
                self._cache[key] = None
        return self._cache[key]

    def level_name(self, element):
        """Level name for element, or None (-> <No Level>)."""
        name = self._lookup(getattr(element, "LevelId", None))
        if name:
            return name
        for key in self._param_keys:
            param = element.get_Parameter(key)
            if param is None or str(param.StorageType) != "ElementId":
                continue
            name = self._lookup(param.AsElementId())
            if name:
                return name
        return None


def level_param_keys():
    """BuiltInParameters tried after LevelId, in spec order (missing skipped)."""
    from Autodesk.Revit.DB import BuiltInParameter
    names = ("INSTANCE_REFERENCE_LEVEL_PARAM", "RBS_START_LEVEL_PARAM",
             "FAMILY_LEVEL_PARAM", "SCHEDULE_LEVEL_PARAM",
             "STAIRS_BASE_LEVEL_PARAM")
    return [getattr(BuiltInParameter, n) for n in names
            if hasattr(BuiltInParameter, n)]


def make_record(element, get_type, view_ids=None, cache=None,
                level_resolver=None):
    """Map one element to an ElementRecord (category already validated)."""
    family, type_name = type_names(element, get_type, cache)
    element_id = _id_int(element.Id)
    level = level_resolver.level_name(element) if level_resolver else None
    return ElementRecord(
        element_id, element.Category.Name, family, type_name,
        in_active_view=(view_ids is not None and element_id in view_ids),
        level=level)


def records_from_elements(elements, get_type, model_category_type,
                          view_ids=None, view_class=None, level_resolver=None,
                          excluded_category_ids=None):
    records = []
    cache = {}
    for element in elements:
        if is_model_element(element, model_category_type, view_class,
                            excluded_category_ids):
            records.append(make_record(element, get_type, view_ids, cache,
                                       level_resolver))
    return records


def in_temporary_isolate(view):
    """True when the view is in temporary hide/isolate mode."""
    from Autodesk.Revit.DB import TemporaryViewMode
    return bool(view.IsInTemporaryViewMode(TemporaryViewMode.TemporaryHideIsolate))


def disable_temporary_isolate(view):
    """Leave temporary hide/isolate. Modifies the view: needs a Transaction."""
    from Autodesk.Revit.DB import TemporaryViewMode
    view.DisableTemporaryViewMode(TemporaryViewMode.TemporaryHideIsolate)


def active_view_ids(doc, view):
    """Set of int element ids visible in view (built once)."""
    from Autodesk.Revit.DB import FilteredElementCollector
    collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    return set(_id_int(i) for i in collector.ToElementIds())


def collect_records(doc, view):
    """All model element instances as (ElementRecords, level elevations dict)."""
    from Autodesk.Revit.DB import CategoryType, FilteredElementCollector, Level, View
    view_ids = active_view_ids(doc, view)
    collector = FilteredElementCollector(doc).WhereElementIsNotElementType()
    type_cache = {}

    def get_type(type_id):
        key = _id_int(type_id)
        if key not in type_cache:
            type_cache[key] = doc.GetElement(type_id)
        return type_cache[key]

    resolver = LevelResolver(doc.GetElement, level_param_keys(), Level)
    records = records_from_elements(collector, get_type, CategoryType.Model,
                                    view_ids, View, resolver,
                                    non_physical_category_ids())
    return records, resolver.elevations


def solid_fill_id(doc):
    """ElementId of the Drafting <Solid fill> pattern, or None."""
    from Autodesk.Revit.DB import FilteredElementCollector, FillPatternElement
    from advfilter.colour import find_solid_fill_id
    return find_solid_fill_id(
        FilteredElementCollector(doc).OfClass(FillPatternElement))


def build_overrides(plan):
    """DB.OverrideGraphicSettings from colour.override_plan output."""
    from Autodesk.Revit.DB import OverrideGraphicSettings, Color
    ogs = OverrideGraphicSettings()
    for name, value in plan:
        if isinstance(value, tuple):
            value = Color(value[0], value[1], value[2])
        getattr(ogs, name)(value)
    return ogs
