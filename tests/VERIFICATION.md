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
`ViewFamilyType`, id 352540) passed the rule (Model category, top-level, has bbox). Fix:
`is_model_element(..., view_class)` rejects any `DB.View` instance; `collect_records` passes
`DB.View`. Mock tests: a view element with Model category + bbox is excluded, normal elements kept.

Remaining for live verification (#7, needs real pyRevit):
- `script.py` / `ui.xaml` load and render, checkbox events fire, Isolate closes the dialog.
- `IsolateElementsTemporary` in a Transaction, and "Reset Temporary Hide/Isolate" restores the view.
- `Element.Name` behaviour on ElementType/FamilySymbol under IronPython (adapter falls back to
  `Element.Name.GetValue`), `Family.Name` and `FamilyName` on real system/loadable types.
- Performance on a ~100k element model (bounding-box check cost per element).
