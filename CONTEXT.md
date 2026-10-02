# CONTEXT — revit-advanced-filter

Standing rules for every ticket, regardless of who/what implements it.

## Platform
- Target: **Autodesk Revit 2024** (API 2024, .NET Framework 4.8).
- Delivery: **pyRevit extension** (`AdvancedFilter.extension/`), Python scripts run under pyRevit's IronPython 2.7 engine unless a ticket explicitly opts into CPython.
- No Revit-2025+ only APIs (e.g. `ElementId.Value`) — use `ElementId.IntegerValue`.

## Code rules
- Any model modification must run inside a `Transaction` (or pyRevit `revit.Transaction`) and handle exceptions; read-only filtering/selecting needs no transaction.
- Use `FilteredElementCollector` with quick filters (category, class) before slow filters/LINQ-style iteration — performance matters on large models.
- Keep pure logic (filter criteria, grouping, sorting, matching) in a host-independent module that does not import `Autodesk.*` at module load, so it can be unit-tested outside Revit.
- UI: WPF via pyRevit `forms` / XAML; dark-friendly, minimal.

## Verification
- Logic that can't run outside Revit needs a **mock-object verification write-up** (standalone Python simulation with fake elements/categories/families/types) before its ticket can close.
- Live checks may use the Revit MCP (`mcp-server-for-revit`) against the open Revit 2024 session — read-only unless the ticket says otherwise.

## Process
- Tracker: GitHub Issues on `EssamKader/revit-advanced-filter`, triage labels `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`.
- Releases: `CHANGELOG.md` + semver tag only on explicit user approval; deploy to pyRevit only from a tagged commit.
