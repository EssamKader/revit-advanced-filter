# revit-advanced-filter

pyRevit extension for **Revit 2024**: find model elements by **Category → Family → Type**, then isolate or colour them. The window stays open while you work in the model.

## Features
- **Project-wide tree** of physical building elements, grouped Category → Family → Type, with counts at every level. It never shows empty nodes or unplaced types.
- **Geometric elements only**. These are left out:
  - views and cameras
  - CAD imports and links, Revit links, point clouds
  - view-specific elements (detail lines)
  - model lines
  - Rooms, Areas, MEP Spaces, HVAC Zones
  - anything without real geometry
- **Scope**: *Whole project* or *Active view only*. View scope follows you when you switch views.
- **Levels**: a multi-select checklist sorted by elevation. Each element belongs to one level, found in this order:
  1. its own level
  2. its reference level (beams)
  3. its MEP start level
  4. its family or schedule level
  5. its stairs base level
  6. its host's level (railings)
  7. otherwise `<No Level>`
- **Tri-state checkboxes**, a **search** box (case-insensitive, any level), and **Select all / Clear / Expand all / Collapse all**. While searching, bulk actions apply only to visible rows.
- **Live count**: *N matched · M in active view*. Isolate is disabled when nothing is in the view.
- **Isolate** and **Reset isolate** use Temporary Hide/Isolate, one Ctrl+Z each.
- **Colour override**: pick a colour (Windows colour dialog, remembered across sessions). **Apply colour** sets a solid fill on surface and cut plus projection and cut line colour. **Reset colours** clears the per-element overrides.
- **Modeless window**: it stays open after every action, and Revit stays usable. **Refresh** re-reads the model after edits. A second click on the button focuses the open window.

## Install
Requires **Revit 2024** and **pyRevit** (4.8+).

1. Download the source of the latest [release](https://github.com/EssamKader/revit-advanced-filter/releases), or clone a release tag:
   ```bash
   git clone --branch v0.1.0 https://github.com/EssamKader/revit-advanced-filter.git
   ```
2. Register the folder that **contains** `AdvancedFilter.extension`:
   ```bash
   pyrevit extensions paths add "C:\path\to\revit-advanced-filter"
   ```
   Or use pyRevit → Settings → Custom Extension Directories → Add → Save & Reload.
3. Restart Revit, or use pyRevit → Reload. The button appears at **BIM Tools → Filter → Advanced Filter**. The tab merges with any other extension that already provides a *BIM Tools* tab.

## Usage
1. Open a plan, section, elevation or 3D view.
2. Click **Advanced Filter**.
3. Choose a scope and levels, then search for or tick categories, families or types.
4. **Isolate** or **Apply colour**. Then use **Reset isolate** or **Reset colours**, or Ctrl+Z.
5. Keep the window open, change the selection, and act again. After editing the model, click **Refresh**.

## Limitations
- Revit 2024 only (uses the `ElementId.IntegerValue` API).
- Linked models and element types are not listed.
- Parameter-value filters and saved presets are not included.
- Colour override is persistent in the view. It isn't temporary like isolate.
- In a temporarily isolated view, colour actions affect only the visible elements.

## Development
- The pure logic lives in `AdvancedFilter.extension/lib/advfilter/` (`core.py`, `session.py`, `colour.py`) and is IronPython 2.7 compatible.
- Revit glue lives in `revit_adapter.py` and the pushbutton's `script.py`.
- Tests are mock-object tests runnable under CPython 3:
  ```bash
  python -m unittest discover -s tests -v
  ```
- What the mocks prove, and what was verified live, is in [tests/VERIFICATION.md](tests/VERIFICATION.md). Standing rules are in [CONTEXT.md](CONTEXT.md), the spec in [specs/advanced-filter.md](specs/advanced-filter.md), and history in [CHANGELOG.md](CHANGELOG.md).

## License
[MIT](LICENSE) © Essam Kader
