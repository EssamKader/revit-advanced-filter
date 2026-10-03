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


def is_model_element(element, model_category_type, view_class=None):
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


def make_record(element, get_type, view_ids=None, cache=None):
    """Map one element to an ElementRecord (category already validated)."""
    family, type_name = type_names(element, get_type, cache)
    element_id = _id_int(element.Id)
    return ElementRecord(
        element_id, element.Category.Name, family, type_name,
        in_active_view=(view_ids is not None and element_id in view_ids))


def records_from_elements(elements, get_type, model_category_type,
                          view_ids=None, view_class=None):
    records = []
    cache = {}
    for element in elements:
        if is_model_element(element, model_category_type, view_class):
            records.append(make_record(element, get_type, view_ids, cache))
    return records


def active_view_ids(doc, view):
    """Set of int element ids visible in view (built once)."""
    from Autodesk.Revit.DB import FilteredElementCollector
    collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
    return set(_id_int(i) for i in collector.ToElementIds())


def collect_records(doc, view):
    """All model element instances of the project as ElementRecords."""
    from Autodesk.Revit.DB import CategoryType, FilteredElementCollector, View
    view_ids = active_view_ids(doc, view)
    collector = FilteredElementCollector(doc).WhereElementIsNotElementType()
    type_cache = {}

    def get_type(type_id):
        key = _id_int(type_id)
        if key not in type_cache:
            type_cache[key] = doc.GetElement(type_id)
        return type_cache[key]

    return records_from_elements(collector, get_type, CategoryType.Model,
                                 view_ids, View)
