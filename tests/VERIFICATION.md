# Verification notes

## #2 Tracer bullet (adapter, guards, selection)

Mock-object verification, run with `python -m unittest discover -s tests -v`.

What the mocks (`tests/test_revit_adapter.py`) prove, using fake
Element / Category / FamilySymbol / ElementType / View / ElementId classes:
- Loadable family: family = `symbol.Family.Name`, type = `symbol.Name`.
- System family: family = type's `FamilyName`, type = `type.Name` (no `.Family`).
- Untyped / missing type element: `(None, None)` -> `<No Family>` / `<No Type>` buckets, never dropped.
- Excluded: Annotation categories, no category, subcategories, Model-category elements
  without a bounding box, and anything without a category (element types).
- `in_active_view` is derived from a once-built int id set; type lookups are cached per type id.
- `view_isolate_problem`: no view, template, unsupported ViewTypes, and
  `CanUseTemporaryVisibilityModes() == False` all return a message; normal views return None.
- `core.checked_element_ids` (checked node = everything under it, de-duplicated) and
  `core.ids_in_view` are pure and unit-tested in `tests/test_core.py`.

Read-only probe of the live Revit 2024 session (MCP) confirmed: `ElementId.IntegerValue` and
`GetTypeId()` -> `-1` for typeless elements, `CanUseTemporaryVisibilityModes()` exists, subcategory
elements exist (`Category.Parent != null`), and Model-category non-geometric elements
(Materials, Project Information, Sun Path, Pipe Segments, Material Assets, Legend Components,
HVAC Zones) have no bounding box -> hence the bounding-box rule in `is_model_element`.
The open project had no walls/floors/doors to probe.

Second live probe (project with elements): 11 elements kept by the rule. Type-name logic confirmed:
Floors `FloorType` FamilyName "Floor" / "Generic 150mm"; Structural Columns `FamilySymbol`
Family.Name "UC-Universal Columns-Column" / "UC305x305x97"; Structural Framing `FamilySymbol`
"Concrete-Rectangular Beam", "Precast-Inverted Tee", "UB-Universal Beams"; Walls `WallType`
FamilyName "Basic Wall" / "Generic - 200mm". Defect found: a 3D view (category Cameras,
`ViewFamilyType`, id 352540) passed the rule (Model category, top-level, has bbox). Initial fix (INCOMPLETE, see #9):
`is_model_element(..., view_class)` rejects any `DB.View` instance; `collect_records` passes
`DB.View`. Mock tests: a view element with Model category + bbox is excluded, normal elements kept.

Remaining for live verification (#7, needs real pyRevit):
- `script.py` / `ui.xaml` load and render, checkbox events fire, Isolate closes the dialog.
- `IsolateElementsTemporary` in a Transaction, and "Reset Temporary Hide/Isolate" restores the view.
- `Element.Name` behaviour on ElementType/FamilySymbol under IronPython (adapter falls back to
  `Element.Name.GetValue`), `Family.Name` and `FamilyName` on real system/loadable types.
- Performance on a ~100k element model (bounding-box check cost per element).

## #9 Level filter

Mock-object verification, run with `python -m unittest discover -s tests -v` (64 tests, all pass).

Pure logic (`tests/test_core.py`): `ElementRecord.level` (None/blank -> `<No Level>`),
`filter_by_levels` (None/empty = all, single, multiple, unknown level -> empty),
`ordered_levels` (by elevation, `<No Level>` last, only levels present on records, missing
elevation after known ones by name), `checked_paths` / `apply_checked_paths` (round trip across
rebuilds, nodes that disappear are dropped, restored when the level returns), and
"only-existing nodes": after every level selection tried, no node has count 0 or no children;
a family only on L1 vanishes when only L2 is selected.

Adapter (`tests/test_revit_adapter.py`, fake Level/Parameter/Element, injected `get_element` and
parameter keys): `LevelResolver` order LevelId -> INSTANCE_REFERENCE -> RBS_START -> FAMILY_LEVEL
-> SCHEDULE_LEVEL -> STAIRS_BASE -> None (`<No Level>`); each step individually; invalid id, id
not resolving to a Level, wrong storage type, null parameter all fall through; level lookups
cached per level id (one `get_element` per level); elevations exposed for ordering.

UI (`script.py`, `ui.xaml`): not runnable outside Revit. Logic path is
level toggle -> `checked_paths` -> `filter_by_levels` (explicit empty roots when nothing ticked,
because core treats an empty selection as "all") -> `build_tree` -> `apply_checked_paths` -> repopulate.
Isolate reads the current `_roots`, so the "Check at least one..." alert covers the empty tree.

Live read-only probe (Revit 2024 MCP): Level 1 @0, Level 2 @13.12 ft (4000 mm). Walls (352524),
Structural Columns (352571), Floors (352597): resolved via `LevelId` -> Level 1. Structural Framing
(7 elements): `LevelId` unusable, resolved via `INSTANCE_REFERENCE_LEVEL_PARAM` -> Level 1.
Element 352540 (category Cameras) is a plain `Autodesk.Revit.DB.Element`, not a `View`, so the
view-class exclusion does not drop it; it resolves to no level and shows as `<No Level>` (pre-existing from #2).

Remaining for live verification (needs real pyRevit): dialog renders the level column, All-levels
toggle / per-level checkboxes rebuild the tree, IronPython `str(param.StorageType) == "ElementId"`,
`BuiltInParameter` names all present in 2024 (guarded by `hasattr`), RBS_START / FAMILY / SCHEDULE /
STAIRS_BASE steps (no such elements in the test model).

### Correction to #2 (camera leak, fixed in #9 branch)
The `DB.View` check did not remove element 352540: a live probe showed it is a plain
`Autodesk.Revit.DB.Element` (category `OST_Cameras`, not ViewSpecific, has geometry). Real fix:
`is_model_element(..., excluded_category_ids)` rejects categories listed in
`_NON_PHYSICAL_CATEGORIES = ("OST_Cameras",)` (resolved with getattr in `non_physical_category_ids()`,
passed by `collect_records`). Mock test: a non-View Cameras element with Model category and bbox is
excluded, a wall is kept. The View check remains.

## Issue #3 - Tri-state checkbox propagation

Core (`tests/test_core.py::TriStateTests` plus updated `CheckStatePreservationTests`): leaves (type
nodes) are the only stored check state; `Node.state` derives True / False / None (mixed) for family
and category nodes. `set_checked` propagates down; `Node.checked` is now "fully checked" and its
setter calls `set_checked`. `click_target(node)` is True unless the node is fully checked, so an
indeterminate click checks everything. `checked_element_ids` = ids of checked leaves, de-duplicated,
stable order. Persistence stores leaf paths only; a category checked while only L1 was shown gets
its L2-only types unchecked when L2 appears and shows as indeterminate (tested). Parent paths in
remembered memory are ignored on apply.

UI (`script.py`): not runnable outside Revit. Each CheckBox has `IsThreeState=False`, handles
`Click` only (never Checked/Unchecked, so no re-entrancy), calls
`core.set_checked(node, core.click_target(node))`, then `_refresh_boxes` sets every box's
`IsChecked = node.state` via the node -> CheckBox list built in `_make_item` (reset on rebuild).
Live-only: WPF renders IsChecked=None as indeterminate with IsThreeState=False, and a click on
that box fires Click once and ends up fully checked; boxes stay in sync after level rebuilds.

## Issue #4 - Search box filtering the tree

Core (`tests/test_core.py::SearchTests`): `search_visibility(roots, query)` returns a set of visible
nodes or `None` (blank/whitespace/None query = everything visible). Case-insensitive substring on
`node.name` at any level, query trimmed. Category match -> whole subtree; family match -> its types
and its category; type match -> its family and category. No match -> empty set (not None). Search
never touches check flags (tested incl. hidden checked leaf surviving and clear restoring).

Click rule under search (US-5): `set_checked(node, value, visible=None)` changes only leaves in
`visible`; `click_target(node, visible=None)` is evaluated over visible leaves (all visible leaves
checked -> uncheck, otherwise check; no visible leaves -> True, a harmless no-op). Hidden leaves keep
their state. Parent boxes keep showing the full `node.state` (e.g. indeterminate after a click that
checked only the visible leaves) so the display never hides checked descendants.

UI (`script.py`, `ui.xaml`): search TextBox with a TextBlock hint overlay (IsHitTestVisible=False,
collapsed when text is non-empty) and a "✕" clear button. `TextChanged` restarts a 200 ms
`DispatcherTimer` (WindowsBase); the tick calls `_apply_search`, which sets `Visibility` on the
existing TreeViewItems through the `_items` node -> item map (no rebuild) and expands visible items
while a query is active. `_rebuild` ends with `_apply_search`, so level changes keep the search.
Mock test `tests/test_script_search.py` execs script.py against fake WPF/pyRevit modules (CPython
only) and checks: debounce restart, hint toggle, hide/expand, clear restores, state preservation,
click-under-search, level rebuild re-applying the search.

Live-only: dark TextBox/hint rendering, DispatcherTimer actually ticking under IronPython,
`Collapsed` TreeViewItems not leaving gaps, `IsExpanded` behaviour with large trees, Cyrillic-free
"…" and "✕" glyphs displaying in Segoe UI.

## Issue #6 - live count, Isolate enable, N>M notice

Core (`core.py`): `selection_counts(roots, view_id_set)` returns `(N, M)` where N is the number of
distinct ids from `checked_element_ids` (checked leaves of the current, level-filtered tree, search
ignored) and M is `len(ids_in_view(...))`. `hidden_notice(n, m)` returns None when `n <= m`, else
"{n-m} matched element(s) are not visible in the active view and were not isolated."
`tests/test_counts.py` covers: nothing checked, single type, category, all, none in view, duplicate
ids, level filter, search not changing counts, empty view set, and the notice text/None cases.

UI (`script.py`, `ui.xaml`): bottom bar is a two-column Grid; `status_text` is left, Isolate/Cancel
right. `FilterWindow._update_status()` sets "N matched · M in active view" (or a muted "Nothing
selected" when N == 0) and `isolate_button.IsEnabled = M > 0`. It is called at the end of `_rebuild`
(startup, level changes, All-levels toggle) and after every `_on_click`; #5's Select all / Clear
should call it too. `isolate_click` keeps its alerts as a safety net and stores `self.counts = (N, M)`
before closing; `main()` then runs `isolate`, and `core.hidden_notice(*window.counts)` feeds
`notify()`, which tries `forms.toast`, then `forms.show_balloon("Advanced Filter", msg)`, then
`forms.alert(..., warn_icon=False)`. The installed pyRevit (`pyrevit/forms/_ipy.py`) provides `toast`.
`tests/test_script_status.py` (fake-module harness shared with `test_script_search.py`) checks status
text and button state at startup, after clicks, uncheck, none-in-view, level change, search
invariance, counts stored on isolate, and the notify fallback order.

Live-only: toast actually appearing (pyRevit toaster executable under Windows notifications), muted
foreground rendering, the disabled-button look on the dark style, status text ellipsis at narrow width.

## Issue #5 - Bulk helpers (Select all / Clear / Expand all / Collapse all)

Core: `set_all(roots, value, visible=None)` calls `set_checked` on every root; with `visible` (search
active) hidden leaves keep their state. `tests/test_core.py::SetAllTests` covers no-search, search-
restricted select, clear under search keeping hidden checked, and empty roots.

UI: `ui.xaml` has a compact button row (Row 1 of the right-hand grid, between search and tree; tree
moved to Row 2) with Click handlers `select_all_click`, `clear_click`, `expand_all_click`,
`collapse_all_click`. Select/Clear call `core.set_all(self._roots, v, self._visible)` then
`_refresh_boxes()` and `_update_status()`; expand/collapse set `IsExpanded` on every item in
`self._items` (hidden ones included). `tests/test_script_status.py` checks select/clear status text and
Isolate state, select/clear under an active search touching only visible nodes (N/M updates), and
expand/collapse flipping every item.

Live-only: button row look/padding on the dark style, handlers wiring from XAML `Click=` names, real
TreeView expansion rendering.

## Issue #18 - Colour override (US-10)

Pure logic in `lib/advfilter/colour.py`: `to_rgb` (clamps to 0..255 ints), `override_plan(rgb, fill_id)`
(ordered setter-name/value pairs: surface and cut foreground pattern id, colour and visible, then
projection and cut line colour), `action_enabled(ticked, chosen, m)` -> (apply, reset) and
`find_solid_fill_id` (first pattern with `IsSolidFill` and `str(Target) == "Drafting"`).
`revit_adapter.solid_fill_id(doc)` and `build_overrides(plan)` (getattr setters, tuples -> `DB.Color`)
are tested against fake `Autodesk.Revit.DB` modules in `tests/test_colour.py`.

script.py: `pick_colour()` wraps `System.Windows.Forms.ColorDialog` (FullOpen, session-wide
`FilterWindow._custom_colors`); tests replace it. The tick/cancel/untick/swatch rules, button enable
states, guards, and the `self.action` field ("isolate" / "colour" / "reset", plus `action_ids`,
`counts`, `colour_rgb`) are exercised through the fake-module harness. `apply_colour` and
`reset_colours` run against a fake Transaction/view: commit per id, rollback with alert when no solid
fill, rollback on exception. `main()` dispatch is checked per action; Isolate tests were adapted to the
`action` field and behave as before.

Live probe (read-only, Revit 2024): one solid FillPatternElement, `<Solid fill>`, Target Drafting,
Id 3; `OverrideGraphicSettings` has `SetSurfaceForegroundPatternVisible` and
`SetCutForegroundPatternVisible`.

Live-only: the real ColorDialog (FullOpen, custom colours persisting, modal over the WPF window),
swatch rendering and hand cursor, new row layout in the dark style, the actual override look in plan
and section (cut pattern colour), Ctrl+Z undoing one action, and that `Color(int,int,int)` accepts
IronPython ints.

Persistence: pyRevit re-executes script.py on every press, so class attributes cannot hold the
colour. The last colour (`last_rgb` as "r,g,b") and the ColorDialog custom colours (`custom_colors`
as comma-separated ints) are stored with `script.get_config()` / `script.save_config()` after each
successful pick and read once at window init. This widens US-10 from "session" to "across sessions"
(accepted by the user). Config read/write is wrapped in try/except so it never blocks the dialog.
Parse/format helpers live in colour.py (`format_rgb`, `parse_rgb`, `format_ints`, `parse_ints`).
Live-only: the real config file round trip and `System.Array[int]` for `CustomColors`.
