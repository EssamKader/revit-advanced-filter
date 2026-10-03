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
        self._checked = False  # meaningful on type nodes (leaves) only

    @property
    def state(self):
        """True (all leaves checked), False (none) or None (mixed).

        Type nodes are the source of truth; category/family states are
        always derived from their children, never stored.
        """
        if self.level == LEVEL_TYPE:
            return self._checked
        states = set(child.state for child in self.children)
        if states == set([True]):
            return True
        if not states or states == set([False]):
            return False
        return None

    @property
    def checked(self):
        """True only when fully checked (indeterminate counts as False)."""
        return self.state is True

    @checked.setter
    def checked(self, value):
        set_checked(self, value)

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


def _leaves(node, visible=None):
    """Type nodes under node; restricted to the visible set when given."""
    if node.level == LEVEL_TYPE:
        if visible is None or node in visible:
            yield node
    else:
        for child in node.children:
            for leaf in _leaves(child, visible):
                yield leaf


def set_checked(node, value, visible=None):
    """Check/uncheck a node's leaves.

    Ancestor states need no update: they are derived from the leaves.
    An indeterminate node clicked by the user should be passed True
    (see click_target).

    visible: optional set of nodes from search_visibility. While a search
    is active only leaves in it are changed (US-5: bulk actions act on
    visible nodes only); hidden leaves keep their state.
    """
    for leaf in _leaves(node, visible):
        leaf._checked = bool(value)


def click_target(node, visible=None):
    """Value a user click should apply: not-all-checked -> True, else False.

    With visible given, the state is evaluated over visible leaves only, so
    a parent whose visible leaves are all checked unchecks them even if
    hidden leaves under it are unchecked (the displayed box state is still
    node.state, over all leaves).
    """
    if visible is None:
        return node.state is not True
    leaves = list(_leaves(node, visible))
    return not (leaves and all(leaf._checked for leaf in leaves))


def search_visibility(roots, query):
    """Set of nodes visible for query, or None (all visible) if it is blank.

    Case-insensitive substring match on node.name at any level, query
    trimmed. Category match -> all descendants visible; family match -> its
    types and its category; type match -> its family and category.
    Never touches check state.
    """
    text = (query or "").strip().lower()
    if not text:
        return None
    visible = set()

    def show_subtree(node):
        visible.add(node)
        for child in node.children:
            show_subtree(child)

    def show_ancestors(node):
        node = node.parent
        while node is not None:
            visible.add(node)
            node = node.parent

    def visit(node):
        if text in node.name.lower():
            show_subtree(node)
            show_ancestors(node)
        for child in node.children:
            visit(child)

    for root in roots:
        visit(root)
    return visible


def checked_element_ids(nodes):
    """Element ids of every fully-checked leaf, de-duplicated, stable order."""
    seen = set()
    result = []

    def visit(node):
        if node.level == LEVEL_TYPE:
            if node._checked:
                for element_id in node.element_ids:
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


def selection_counts(roots, view_id_set):
    """(N, M): distinct checked ids in the tree, and how many are in view."""
    checked = checked_element_ids(roots)
    return len(checked), len(ids_in_view(checked, view_id_set))


def hidden_notice(n, m):
    """Post-isolate notice text, or None when everything matched was isolated."""
    if n <= m:
        return None
    return ("%d matched element(s) are not visible in the active view "
            "and were not isolated." % (n - m))


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
    """Set of name-path tuples of every checked leaf (type node).

    Only leaf paths are remembered; category/family states are derived.
    Consequence: a category checked while only L1 was shown has its L2-only
    types come in unchecked when L2 appears, and shows as indeterminate.
    """
    result = set()

    def visit(node):
        if node.level == LEVEL_TYPE:
            if node._checked:
                result.add(_node_path(node))
        else:
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
    """Check leaves whose path is in paths; others are left untouched.

    Non-leaf paths in paths are ignored (leaf-only rule).
    """
    def visit(node):
        if node.level == LEVEL_TYPE:
            if _node_path(node) in paths:
                node._checked = True
        else:
            for child in node.children:
                visit(child)

    for root in roots:
        visit(root)
