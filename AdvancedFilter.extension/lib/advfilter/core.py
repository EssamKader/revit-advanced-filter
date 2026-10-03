# -*- coding: utf-8 -*-
"""Host-independent grouping model: Category -> Family -> Type.

Pure Python (IronPython 2.7 / CPython 3 compatible). Must never import
Autodesk.*, clr, pyrevit or System.
"""

NO_FAMILY = "<No Family>"
NO_TYPE = "<No Type>"
NO_LEVEL = "<No Level>"

LEVEL_CATEGORY = "category"
LEVEL_FAMILY = "family"
LEVEL_TYPE = "type"


class ElementRecord(object):
    """Plain description of one model element instance."""

    def __init__(self, element_id, category, family=None, type_name=None,
                 in_active_view=False, level=None):
        self.element_id = element_id
        self.category = category
        self.family = family
        self.type_name = type_name
        self.in_active_view = in_active_view
        self.level = _clean(level, NO_LEVEL)


class Node(object):
    """One node of the Category/Family/Type tree."""

    def __init__(self, name, level, parent=None):
        self.name = name
        self.level = level
        self.parent = parent
        self.children = []
        self.element_ids = []  # populated on type nodes only
        self.checked = False

    @property
    def count(self):
        """Total number of element ids under this node."""
        if self.level == LEVEL_TYPE:
            return len(self.element_ids)
        return sum(child.count for child in self.children)

    def __repr__(self):
        return "Node(%r, %s, count=%d)" % (self.name, self.level, self.count)


def _clean(value, fallback):
    if value is None:
        return fallback
    text = value.strip() if hasattr(value, "strip") else str(value).strip()
    return text if text else fallback


def _sort_key(node):
    # Case-insensitive name first, raw name as stable tie-breaker.
    return (node.name.lower(), node.name)


def build_tree(records):
    """Group records into a sorted list of category Nodes.

    Records with an empty/None category are skipped (the spec only collects
    elements with a valid category); missing family/type go to the
    NO_FAMILY / NO_TYPE buckets and are never dropped.
    """
    categories = {}
    index = {}  # (path tuple) -> Node, for O(1) lookup at every level
    for rec in records:
        cat_name = _clean(rec.category, "")
        if not cat_name:
            continue
        family_name = _clean(rec.family, NO_FAMILY)
        type_name = _clean(rec.type_name, NO_TYPE)

        cat = categories.get(cat_name)
        if cat is None:
            cat = categories[cat_name] = Node(cat_name, LEVEL_CATEGORY)
        fam_key = (cat_name, family_name)
        fam = index.get(fam_key)
        if fam is None:
            fam = index[fam_key] = Node(family_name, LEVEL_FAMILY, cat)
            cat.children.append(fam)
        typ_key = (cat_name, family_name, type_name)
        typ = index.get(typ_key)
        if typ is None:
            typ = index[typ_key] = Node(type_name, LEVEL_TYPE, fam)
            fam.children.append(typ)
        typ.element_ids.append(rec.element_id)

    result = sorted(categories.values(), key=_sort_key)
    for cat in result:
        cat.children.sort(key=_sort_key)
        for fam in cat.children:
            fam.children.sort(key=_sort_key)
    return result


def iter_element_ids(node):
    """Yield every element id under (and including) the given node."""
    if node.level == LEVEL_TYPE:
        for element_id in node.element_ids:
            yield element_id
    else:
        for child in node.children:
            for element_id in iter_element_ids(child):
                yield element_id


def checked_element_ids(nodes):
    """Union of element ids under every checked node, de-duplicated.

    A checked node means "everything under it", so a checked parent covers
    all its descendants regardless of their own flag. Order is stable.
    """
    seen = set()
    result = []

    def visit(node):
        if node.checked:
            for element_id in iter_element_ids(node):
                if element_id not in seen:
                    seen.add(element_id)
                    result.append(element_id)
        else:
            for child in node.children:
                visit(child)

    for node in nodes:
        visit(node)
    return result


def ids_in_view(element_ids, view_id_set):
    """Keep only the ids present in view_id_set (order preserved)."""
    return [i for i in element_ids if i in view_id_set]


def filter_by_levels(records, level_names):
    """Records whose level is in level_names; None/empty means all levels.

    Rebuild the tree from the result with build_tree so counts and nodes
    reflect only the selected levels (no empty nodes can appear).
    """
    if not level_names:
        return list(records)
    wanted = set(level_names)
    return [r for r in records if r.level in wanted]


def ordered_levels(records, elevations):
    """Level names present on records, by elevation, NO_LEVEL last.

    elevations: dict name -> float. Names without an elevation follow the
    known ones, sorted by name.
    """
    present = set(r.level for r in records)
    named = [n for n in present if n != NO_LEVEL]
    known = sorted((n for n in named if n in elevations),
                   key=lambda n: (elevations[n], n.lower(), n))
    unknown = sorted((n for n in named if n not in elevations),
                     key=lambda n: (n.lower(), n))
    result = known + unknown
    if NO_LEVEL in present:
        result.append(NO_LEVEL)
    return result


def _node_path(node):
    names = []
    while node is not None:
        names.append(node.name)
        node = node.parent
    return tuple(reversed(names))


def checked_paths(roots):
    """Set of name-path tuples of every checked node."""
    result = set()

    def visit(node):
        if node.checked:
            result.add(_node_path(node))
        for child in node.children:
            visit(child)

    for root in roots:
        visit(root)
    return result


def all_paths(roots):
    """Set of name-path tuples of every node in the tree."""
    result = set()

    def visit(node):
        result.add(_node_path(node))
        for child in node.children:
            visit(child)

    for root in roots:
        visit(root)
    return result


def merge_checked_paths(previous, roots):
    """Remembered checks: hidden paths keep state, visible ones take live state."""
    return (set(previous) - all_paths(roots)) | checked_paths(roots)


def apply_checked_paths(roots, paths):
    """Check nodes whose path is in paths; others are left untouched."""
    def visit(node):
        if _node_path(node) in paths:
            node.checked = True
        for child in node.children:
            visit(child)

    for root in roots:
        visit(root)
