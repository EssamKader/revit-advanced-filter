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
