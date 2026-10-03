# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-10-03

First release: pyRevit extension for Revit 2024, verified live on a 9,500-element structural model.

### Added
- Category → Family → Type tree of physical model elements, with counts and project-wide collection. (#1, #2)
- Tri-state checkboxes. (#3)
- Search box. (#4)
- Select all / Clear / Expand all / Collapse all. (#5)
- Live "N matched · M in active view" count, and a notice when some matches aren't in the view. (#6)
- Multi-select level filter, using each element's base or reference level. (#9)
- Button placed on the shared **BIM Tools** ribbon tab. (#11)
- Colour override with Apply colour / Reset colours. The colour is remembered across sessions. (#18)
- Modeless window that stays open (ExternalEvent), with Refresh and single-instance focus. (#20)
- Scope toggle: Whole project / Active view only. (#23)
- Window icon matches the button icon. (#26)
- Reset isolate button. (#28)

### Fixed
- Non-building elements are excluded: CAD imports, links, point clouds, view-specific elements, model lines, cameras and spatial elements. (#22)
- Elements without real geometry (e.g. a railing that failed to generate) are excluded. Railings take their level from their host. (#30)
