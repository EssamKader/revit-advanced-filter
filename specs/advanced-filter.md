# Spec — Advanced Filter (Category → Family → Type)

**Target:** Revit 2024 · pyRevit extension · modal WPF dialog
**Status:** Draft — awaiting confirmation

## Summary
A pyRevit button opens a modal dialog listing every model element in the project as a
Category → Family → Type checkbox tree, with counts. The user checks any combination of
nodes and clicks **Isolate** to temporarily isolate the matching elements in the active view.

## Decisions (from Phase 1)
| Topic | Decision |
|---|---|
| Collection scope | Whole project (all model element instances) |
| Action | Temporary Hide/Isolate in the **active view** |
| Filter depth | Category → Family → Type only (no parameter rules) |
| UI | Modal WPF dialog (pyRevit `forms.WPFWindow` + XAML) |
| Excluded | Element types, views, annotation categories, linked models, permanent isolate |
| Geometric only (2026-10-03) | Keep an element only if its category is top-level Model, it is not a `View`, and `get_BoundingBox(None)` is not None. This drops Materials, Sun Path, Project Information, camera views and unplaced rooms. |
| Level filter (2026-10-03) | Multi-select level checklist. Each element belongs to **one** level, its base/reference level; spanning levels doesn't count. Elements with no level go to `<No Level>`. |

## User stories

### US-1 — Launch
As a BIM engineer, I want an **Advanced Filter** button on the existing **BIM Tools** ribbon tab (merged with ClashFlag's tab),
so that I can open the filter in one click.
- **Acceptance:** the extension `AdvancedFilter.extension` loads in pyRevit on Revit 2024. The button appears and opens the dialog. If no document is open, or the active view can't do temporary isolation (schedules, sheets, legends, templates), the button shows a clear message instead of the dialog.

### US-2 — Project-wide collection
As a BIM engineer, I want all model element instances in the project collected and grouped by
Category → Family → Type, so that I can see the model's whole composition.
- **Acceptance:**
  - Uses `FilteredElementCollector(doc).WhereElementIsNotElementType()`, restricted to categories where `CategoryType == Model` and the element has a valid category.
  - Loadable-family instances group by `Family.Name` → `FamilySymbol.Name`.
  - System families (walls, floors, ducts, pipes …) group by the type's `FamilyName` property → type name.
  - Elements with no type go under the `<No Family>` / `<No Type>` buckets. They are never dropped.
  - Collection of a ~100k-element model completes in a few seconds. Quick filters run first and there's no per-element parameter lookup beyond what grouping needs.

### US-3 — Tree with counts
As a BIM engineer, I want a 3-level checkbox tree with element counts at every level,
so that I know how many elements each choice affects before I isolate.
- **Acceptance:**
  - Nodes are sorted alphabetically and show `Name (count)`.
  - Parent checkboxes are tri-state. Checking a parent checks all its children; mixed children show the indeterminate state.

### US-4 — Search
As a BIM engineer, I want a search box that filters the tree by name (case-insensitive,
matches at any level), so that I can find a family or type quickly in a large model.
- **Acceptance:**
  - A match on a category keeps all of its children visible.
  - A match on a type keeps its family and category ancestors visible.
  - Clearing the search restores the full tree. Check states survive filtering.

### US-5 — Bulk selection helpers
As a BIM engineer, I want **Select all**, **Clear**, and **Expand/Collapse all** controls,
so that I can build a selection quickly.
- **Acceptance:** Select all and Clear act only on nodes visible under the current search.

### US-6 — Live result count
As a BIM engineer, I want the dialog to show **"N matched · M in active view"** as I check
nodes, so that I know before isolating whether some matches won't be visible.
- **Acceptance:**
  - N = total checked element instances.
  - M = how many of those are in the active view, using a `FilteredElementCollector(doc, view.Id)` element-id set built once when the dialog opens.
  - **Isolate** is disabled when M = 0.

### US-7 — Isolate
As a BIM engineer, I want **Isolate** to temporarily isolate the matching elements in the active
view and close the dialog, so that I can review them on screen and reset with Revit's native
"Reset Temporary Hide/Isolate".
- **Acceptance:**
  - Runs `view.IsolateElementsTemporary(ids)` inside a Transaction, using only the ids present in the active view.
  - Exceptions are caught, the transaction rolls back, and the user sees an error dialog.
  - If N > M, a non-blocking notice says how many matched elements aren't in the active view.

### US-8 — Testable core
As the maintainer, I want the grouping/tree/search/count logic in a host-independent Python module
(`lib/advfilter/core.py`) with no `Autodesk.*` imports at module load, so that it can be verified
with mock elements outside Revit (CONTEXT.md rule).
- **Acceptance:**
  - Mock-object test suite (`tests/`) covers:
    - grouping, including system families and `<No Type>`
    - tri-state propagation
    - search ancestor/descendant visibility
    - N/M counts
  - The suite runs under CPython 3 and is IronPython-2.7 compatible: no f-strings and no type hints in `lib/`.

### US-9 — Level filter
As a BIM engineer, I want to limit the tree to elements on chosen levels (one, several, or all), so that I can isolate what is on a specific floor.
- **Acceptance:**
  - Each record gets one level name, resolved in this order:
    1. `Element.LevelId`
    2. `INSTANCE_REFERENCE_LEVEL_PARAM` (beams/framing)
    3. `RBS_START_LEVEL_PARAM` (MEP curves)
    4. `FAMILY_LEVEL_PARAM` / `SCHEDULE_LEVEL_PARAM`
    5. `STAIRS_BASE_LEVEL_PARAM`
    6. otherwise `<No Level>`.
  - Live check (2026-10-03): walls, floors and columns resolve through `LevelId`, and framing through `INSTANCE_REFERENCE_LEVEL_PARAM`.
  - The dialog has a multi-select level checklist with an **All levels** toggle. Levels are sorted by elevation, with `<No Level>` last. The default is All.
  - Changing the level selection rebuilds the tree and its counts from the matching records only. Check states are preserved for nodes that still exist, by Category/Family/Type path.
  - Isolate uses only elements on the selected levels. N/M counts (US-6) and search (US-4) apply to the level-filtered tree.
  - Level resolution goes through mock tests, and the pure filtering lives in `core.py`.

### US-10 — Colour override
As a BIM engineer, I want to colour the checked elements in the active view, and to remove that colour again, so that I can highlight a category, family or type without isolating it.

Decisions (user, 2026-10-03):

| Topic | Decision |
|---|---|
| Trigger | Separate action, independent of Isolate |
| Graphics | Surface and cut foreground set to `<Solid fill>`, plus projection and cut line colour, all in the chosen colour |
| Removal | **Reset colours** button, plus Ctrl+Z (one transaction per action) |
| Picker | Windows `System.Windows.Forms.ColorDialog` with custom colours |

- **Acceptance:**
  - **Colour override checkbox:** ticking it opens the colour dialog right away.
    - Cancelling the dialog leaves the box unticked.
    - Once a colour is chosen, a clickable swatch next to the box shows it; clicking the swatch reopens the dialog.
    - Unticking the box hides the swatch, but the colour is remembered. The last colour and custom colours persist across sessions in the pyRevit script config.
  - **Apply colour button:**
    - Enabled only when the box is ticked and M > 0, i.e. checked elements exist in the active view.
    - Applies `OverrideGraphicSettings` to the checked ids in the active view, inside one Transaction "Advanced Filter: Colour override", then closes the dialog.
    - Shows the N > M notice (US-6) when some matches aren't in the view.
  - **Reset colours button:**
    - Enabled when M > 0.
    - Calls `SetElementOverrides(id, OverrideGraphicSettings())` for the checked ids in the active view, inside one Transaction "Advanced Filter: Reset colours", then closes the dialog.
    - It only clears per-element overrides. View filters and category overrides are untouched.
  - **Solid fill:** found via `FillPatternElement` where `GetFillPattern().IsSolidFill` is true and the target is Drafting. If none is found, show a clear error and roll back.
  - **Colour conversion:** the chosen colour (WinForms `Color`) is converted to `DB.Color(r, g, b)`. The conversion and the override plan (which setters get which values) live in pure, mock-tested code.
  - **Errors:** exceptions roll back the transaction and show an alert, consistent with US-7.
  - **Isolate unchanged:** Isolate behaves exactly as before. Colour and Isolate are separate actions.

### US-11 — Modeless window that stays open
As a BIM engineer, I want the Advanced Filter window to stay open after Isolate, Apply colour or Reset colours, while I can still navigate the model, so that I can try other categories, families or types without reopening it.

Decisions (user, 2026-10-03): **modeless window + ExternalEvent**; **always stays open**, with no auto-close option.

- **Acceptance:**
  - **Persistent engine:** `script.py` sets `__persistentengine__ = True`. The window opens with `.Show()`, not modal, so Revit stays usable: pan, orbit, select and switch views.
  - **Single instance:** clicking the button while the window is open brings the existing window to the front instead of opening a second one.
  - **ExternalEvent:** all model changes go through one `IExternalEventHandler` and its `ExternalEvent`:
    - Isolate, Apply colour, Reset colours (US-7, US-10)
    - each runs in its own Transaction with rollback and an alert, as today
  - **Re-read on every action:** the handler re-reads `uidoc.ActiveView` and runs the view guard (US-1); an unsupported view shows an alert and changes nothing. It also rebuilds the active-view id set, so M always matches the view actually acted on.
  - **Live M:** the dialog subscribes to `UIApplication.ViewActivated` while open and unsubscribes on close. It recomputes the view id set and the N/M status (US-6) when the user switches views.
  - **Refresh button:** re-collects the project records for the current active document, for after model edits. It keeps the selected levels, the search text and the checked leaf paths (US-3/4/9).
  - **Document guard:** if the active document is no longer the one the window was built from, actions show "The active document changed — click Refresh" and do nothing. Refresh rebinds to the active document.
  - **After each action:** the window stays open. The status line shows a short result ("Isolated 12 elements" / "Coloured 12 elements" / "Reset 12 elements"), and the N > M notice still appears.
  - **Buttons:** Cancel becomes **Close**, the only way to close besides the window ✕. Closing unsubscribes events and releases the single-instance slot.
  - **Implementation details (#20):**
    - The single-instance slot is kept in `AppDomain` data (key `AdvancedFilter.window`), because the persistent engine re-runs `script.py` on every press.
    - Before Isolate rebuilds the view id set, the handler leaves temporary hide/isolate in that view (`DisableTemporaryViewMode`), since a view already in temporary isolate would report only the isolated elements. Colour and Reset do not do this.
    - Refresh does not run the isolate view guard (it only reads), and it also reports `Refreshed: N elements` in the status line. A document with no model elements keeps the current window state and alerts.
    - If `ViewActivated` fires for a view the collector cannot filter, M becomes 0 (Isolate and colour buttons disable) until the next view switch.
    - Pure helpers live in `lib/advfilter/session.py`: `result_text`, `document_guard`, `merge_level_selection`, `Request`/`RequestQueue` (Execute drains the queue, because `ExternalEvent.Raise` coalesces).
  - **Testing:** the pure parts (action dispatch, result text, document-guard decision) are mock-tested. The ExternalEvent and modeless behaviour are live-only and verified in #7.

## Out of scope
- Parameter-value filters
- Linked models
- Element types
- Annotation categories
- Permanent hide/isolate
- Select/export actions (colour override added as US-10)
- Dockable pane
- Saved filter presets

## Proposed layout
```
AdvancedFilter.extension/
  BIM Tools.tab/        # same name as ClashFlag's tab so pyRevit merges them
    Filter.panel/
      Advanced Filter.pushbutton/
        script.py        # Revit glue: collect → dialog → isolate
        ui.xaml          # WPF dialog
        bundle.yaml
        icon.png
  lib/advfilter/
    __init__.py
    core.py              # pure logic (US-8)
    revit_adapter.py     # Element → plain record (cat, family, type, id)
tests/
  test_core.py           # mock-object verification
```
