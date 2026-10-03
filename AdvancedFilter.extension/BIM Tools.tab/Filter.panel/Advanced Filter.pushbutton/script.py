# -*- coding: utf-8 -*-
"""Advanced Filter: modeless Category/Family/Type tree -> Isolate / colour."""
__persistentengine__ = True

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Collections.Generic import List
import System
from System import TimeSpan, Uri, UriKind
from System.Windows import Visibility, WindowState
from System.Windows.Media import SolidColorBrush, Color
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
from System.Windows.Threading import DispatcherTimer
from System.Windows.Controls import CheckBox, TreeViewItem
from Autodesk.Revit import DB, UI
from pyrevit import forms, script

from advfilter import core, colour, revit_adapter, session

# One window per Revit session: the persistent engine re-runs this file on
# every button press, so the slot lives in the AppDomain, not in the module.
_SLOT_KEY = "AdvancedFilter.window"


def get_open_window():
    return System.AppDomain.CurrentDomain.GetData(_SLOT_KEY)


def set_open_window(window):
    System.AppDomain.CurrentDomain.SetData(_SLOT_KEY, window)


NO_FILTER_HINT = "Active view does not support element filtering"


def doc_key_of(document):
    """(PathName, Title) of a document, or None if it cannot be read."""
    try:
        return session.doc_key(document.PathName, document.Title)
    except Exception:
        return None


def pick_colour(initial, custom_colors):
    """Show the Windows colour dialog. Returns (rgb or None, custom_colors)."""
    clr.AddReference("System.Windows.Forms")
    clr.AddReference("System.Drawing")
    from System.Windows.Forms import ColorDialog, DialogResult
    from System.Drawing import Color as DrawingColor
    dialog = ColorDialog()
    dialog.FullOpen = True
    if custom_colors:
        dialog.CustomColors = System.Array[int](custom_colors)
    if initial is not None:
        dialog.Color = DrawingColor.FromArgb(initial[0], initial[1], initial[2])
    try:
        if dialog.ShowDialog() == DialogResult.OK:
            return colour.to_rgb(dialog.Color), list(dialog.CustomColors)
        return None, list(dialog.CustomColors)
    finally:
        dialog.Dispose()


def load_colour_state():
    """(last rgb or None, custom colours or None) from the pyRevit config."""
    try:
        cfg = script.get_config()
        return (colour.parse_rgb(getattr(cfg, "last_rgb", None)),
                colour.parse_ints(getattr(cfg, "custom_colors", None)))
    except Exception:
        return None, None


def save_colour_state(rgb, custom_colors):
    try:
        cfg = script.get_config()
        cfg.last_rgb = colour.format_rgb(rgb)
        if custom_colors:
            cfg.custom_colors = colour.format_ints(custom_colors)
        script.save_config()
    except Exception:
        pass


def load_scope():
    """Saved scope from the pyRevit config; whole project when missing or bad."""
    try:
        return core.parse_scope(getattr(script.get_config(), "scope", None))
    except Exception:
        return core.SCOPE_PROJECT


def save_scope(scope):
    try:
        cfg = script.get_config()
        cfg.scope = scope
        script.save_config()
    except Exception:
        pass


def load_window_icon():
    """BitmapImage of the bundle's icon.png, or None if it cannot be loaded."""
    try:
        image = BitmapImage()
        image.BeginInit()
        image.UriSource = Uri(script.get_bundle_file("icon.png"),
                              UriKind.Absolute)
        image.CacheOption = BitmapCacheOption.OnLoad  # release the file
        image.EndInit()
        image.Freeze()
        return image
    except Exception:
        return None


class FilterWindow(forms.WPFWindow):
    def __init__(self, xaml_file, records, elevations, document=None):
        forms.WPFWindow.__init__(self, xaml_file)
        # WPFWindow.__init__ sets the pyRevit default icon; override it after.
        icon = load_window_icon()
        if icon is not None:
            self.Icon = icon
        self._doc = document
        self._doc_key = doc_key_of(document) if document is not None else None
        self._closed = False
        self._records = records
        self._elevations = elevations
        self._view_ids = set(r.element_id for r in records if r.in_active_view)
        # Ids the tree was last scoped to: moved only by build points (open,
        # view switch, Refresh), never by Isolate/colour actions.
        self._scope_ids = set(self._view_ids)
        self._view_unsupported = False
        self._scope = load_scope()
        self._roots = []
        self._checked = set()  # remembered check paths, incl. hidden nodes
        self._busy = False
        self._boxes = []  # (node, CheckBox) for every tree node
        self._items = {}  # node -> TreeViewItem, for search show/hide
        self._visible = None  # search_visibility result; None = all visible
        self._timer = DispatcherTimer()
        self._timer.Interval = TimeSpan.FromMilliseconds(200)
        self._timer.Tick += self._on_search_tick
        self.search_box.TextChanged += self._on_search_changed
        self.colour_rgb, self._custom_colors = load_colour_state()
        self._m = 0
        self._fg_brush = SolidColorBrush(Color.FromRgb(0xE6, 0xE6, 0xE6))
        self._muted_brush = SolidColorBrush(Color.FromRgb(0x80, 0x80, 0x80))
        self._level_boxes = []
        self.scope_view.IsChecked = self._scope == core.SCOPE_VIEW
        self.scope_project.IsChecked = self._scope != core.SCOPE_VIEW
        self._build_levels(
            core.ordered_levels(self._scoped_records(), elevations), None)
        self.scope_project.Checked += self._on_scope_changed
        self.scope_view.Checked += self._on_scope_changed
        self.all_levels.Checked += self._on_all_toggle
        self.all_levels.Unchecked += self._on_all_toggle
        self._rebuild()
        # Created here: the button command gives a valid API context.
        self._queue = session.RequestQueue()
        self._event = UI.ExternalEvent.Create(RequestHandler(self))
        self._view_handler = self._on_view_activated
        __revit__.ViewActivated += self._view_handler
        self.Closed += self._on_closed

    def _build_levels(self, names, selected):
        """Fill the level list; selected=None ticks every level."""
        self._busy = True
        try:
            self.level_list.Items.Clear()
            self._level_boxes = []
            for name in names:
                box = CheckBox()
                box.Content = name
                box.IsChecked = selected is None or name in selected
                box.Checked += self._on_level_toggle
                box.Unchecked += self._on_level_toggle
                self._level_boxes.append(box)
                self.level_list.Items.Add(box)
            self.all_levels.IsChecked = (
                len(self._selected_levels()) == len(self._level_boxes))
        finally:
            self._busy = False

    def _scoped_records(self):
        """Records inside the scope; none in view scope on an unsupported view."""
        if self._scope == core.SCOPE_VIEW and self._view_unsupported:
            return []
        return core.filter_by_scope(self._records, self._scope, self._scope_ids)

    def _reapply_scope(self):
        """Rebuild level list (scoped levels only) and tree; keep checks/search."""
        old_all = [b.Content for b in self._level_boxes]
        old_selected = self._selected_levels()
        names = core.ordered_levels(self._scoped_records(), self._elevations)
        self._build_levels(
            names, session.merge_level_selection(old_selected, old_all, names))
        self._rebuild()

    def _on_scope_changed(self, sender, args):
        if self._busy:
            return
        scope = (core.SCOPE_VIEW if self.scope_view.IsChecked
                 else core.SCOPE_PROJECT)
        if scope == self._scope:
            return
        self._scope = scope
        save_scope(scope)
        self._reapply_scope()

    def _selected_levels(self):
        return [b.Content for b in self._level_boxes if b.IsChecked]

    def _rebuild(self):
        """Rebuild the tree for the selected levels, keeping check states."""
        self._checked = core.merge_checked_paths(self._checked, self._roots)
        selected = self._selected_levels()
        if selected:
            records = core.filter_by_levels(self._scoped_records(), selected)
        else:
            records = []  # no level ticked: empty tree (empty selection = all in core)
        self._roots = core.build_tree(records)
        core.apply_checked_paths(self._roots, self._checked)
        self.tree.Items.Clear()
        self._boxes = []
        self._items = {}
        for root in self._roots:
            self.tree.Items.Add(self._make_item(root))
        self._refresh_boxes()
        self._apply_search()
        self._update_status()

    def _on_search_changed(self, sender, args):
        self.search_hint.Visibility = (
            Visibility.Collapsed if self.search_box.Text else Visibility.Visible)
        # Debounce: restart the timer on every keystroke.
        self._timer.Stop()
        self._timer.Start()

    def _on_search_tick(self, sender, args):
        self._timer.Stop()
        self._apply_search()

    def _flush_search(self):
        """Apply a pending debounced search now so self._visible is current."""
        if self._timer.IsEnabled:
            self._timer.Stop()
            self._apply_search()

    def search_clear_click(self, sender, args):
        self._timer.Stop()
        self.search_box.Text = ""
        self._apply_search()

    def _apply_search(self):
        """Show/hide existing TreeViewItems; check states are untouched."""
        query = self.search_box.Text
        self._visible = core.search_visibility(self._roots, query)
        for node, item in self._items.items():
            if self._visible is None:
                item.Visibility = Visibility.Visible
            else:
                shown = node in self._visible
                item.Visibility = Visibility.Visible if shown else Visibility.Collapsed
                if shown:
                    item.IsExpanded = True

    def _on_level_toggle(self, sender, args):
        if self._busy:
            return
        self._busy = True
        try:
            self.all_levels.IsChecked = len(self._selected_levels()) == len(self._level_boxes)
        finally:
            self._busy = False
        self._rebuild()

    def _on_all_toggle(self, sender, args):
        if self._busy:
            return
        self._busy = True
        try:
            for box in self._level_boxes:
                box.IsChecked = bool(self.all_levels.IsChecked)
        finally:
            self._busy = False
        self._rebuild()

    def _make_item(self, node):
        box = CheckBox()
        box.Content = "%s (%d)" % (node.name, node.count)
        box.Tag = node
        # IsThreeState stays False: a click toggles True/False, while
        # IsChecked = None (set from node.state) still shows indeterminate.
        box.IsThreeState = False
        box.Click += self._on_click
        self._boxes.append((node, box))
        item = TreeViewItem()
        item.Header = box
        self._items[node] = item
        if node.level != core.LEVEL_TYPE:
            for child in node.children:
                item.Items.Add(self._make_item(child))
        return item

    def _on_click(self, sender, args):
        # Click fires after WPF flipped IsChecked; ignore it and decide from
        # the core state so an indeterminate box always becomes "all checked".
        self._flush_search()
        node = sender.Tag
        # While a search is active only visible leaves change (US-5); the
        # box itself keeps showing the full node.state so it never misleads.
        core.set_checked(node, core.click_target(node, self._visible),
                         self._visible)
        self._refresh_boxes()
        self._update_status()

    def select_all_click(self, sender, args):
        self._set_all(True)

    def clear_click(self, sender, args):
        self._set_all(False)

    def _set_all(self, value):
        self._flush_search()
        # Under an active search only visible leaves change (US-5).
        core.set_all(self._roots, value, self._visible)
        self._refresh_boxes()
        self._update_status()

    def expand_all_click(self, sender, args):
        for item in self._items.values():
            item.IsExpanded = True

    def collapse_all_click(self, sender, args):
        for item in self._items.values():
            item.IsExpanded = False

    def _refresh_boxes(self):
        self._busy = True
        try:
            for node, box in self._boxes:
                box.IsChecked = node.state
        finally:
            self._busy = False

    def _update_status(self):
        """Refresh the N/M label and Isolate enabled state (call after any check change)."""
        n, m = core.selection_counts(self._roots, self._view_ids)
        if self._scope == core.SCOPE_VIEW and self._view_unsupported:
            m = 0
            self.status_text.Text = NO_FILTER_HINT
            self.status_text.Foreground = self._muted_brush
        elif n == 0:
            self.status_text.Text = "Nothing selected"
            self.status_text.Foreground = self._muted_brush
        else:
            self.status_text.Text = u"%d matched · %d in active view" % (n, m)
            self.status_text.Foreground = self._fg_brush
        self.isolate_button.IsEnabled = m > 0
        self._m = m
        self._update_colour_buttons()

    def _update_colour_buttons(self):
        apply_on, reset_on = colour.action_enabled(
            self.colour_check.IsChecked, self.colour_rgb is not None, self._m)
        self.apply_colour_button.IsEnabled = apply_on
        self.reset_colours_button.IsEnabled = reset_on

    def _choose_colour(self):
        """Open the picker; returns True if a colour was chosen."""
        rgb, custom = pick_colour(self.colour_rgb, self._custom_colors)
        if custom:
            self._custom_colors = custom
        if rgb is None:
            return False
        self.colour_rgb = rgb
        save_colour_state(rgb, self._custom_colors)
        self.colour_swatch.Background = SolidColorBrush(Color.FromRgb(*rgb))
        return True

    def colour_check_changed(self, sender, args):
        if self._busy:
            return
        if self.colour_check.IsChecked:
            if not self._choose_colour() and self.colour_rgb is None:
                self._busy = True
                try:
                    self.colour_check.IsChecked = False
                finally:
                    self._busy = False
        self.colour_swatch.Visibility = (
            Visibility.Visible if self.colour_check.IsChecked
            else Visibility.Collapsed)
        self._update_colour_buttons()

    def colour_swatch_click(self, sender, args):
        if self._choose_colour():
            self._update_colour_buttons()

    def _checked_ids(self):
        """Checked ids to act on, or None after showing an alert."""
        self._flush_search()
        checked = core.checked_element_ids(self._roots)
        if not checked:
            forms.alert("Check at least one category, family or type.",
                        title="Advanced Filter")
            return None
        if not core.ids_in_view(checked, self._view_ids):
            forms.alert("None of the checked elements are in the active view.",
                        title="Advanced Filter")
            return None
        return checked

    def _post(self, action, ids=None, rgb=None):
        """Queue a request and wake the ExternalEvent handler."""
        self._queue.put(session.Request(action, ids, rgb))
        self._event.Raise()

    def apply_colour_click(self, sender, args):
        self._flush_search()
        if self.colour_rgb is None:
            forms.alert("Choose a colour first.", title="Advanced Filter")
            return
        ids = self._checked_ids()
        if ids:
            self._post(session.COLOUR, ids, self.colour_rgb)

    def reset_colours_click(self, sender, args):
        ids = self._checked_ids()
        if ids:
            self._post(session.RESET, ids)

    def isolate_click(self, sender, args):
        ids = self._checked_ids()
        if ids:
            self._post(session.ISOLATE, ids)

    def refresh_click(self, sender, args):
        self._flush_search()
        self.status_text.Text = "Refreshing..."
        self.status_text.Foreground = self._muted_brush
        self._post(session.REFRESH)

    def close_click(self, sender, args):
        self._flush_search()
        self.Close()

    # Called from RequestHandler.Execute (Revit API context, UI thread).
    def take_requests(self):
        return [] if self._closed else self._queue.drain()

    def doc_key(self):
        return self._doc_key

    def show_status(self, text):
        if self._closed:
            return
        self.status_text.Text = text
        self.status_text.Foreground = self._fg_brush

    def set_view_ids(self, view_ids):
        """Rebuild M from a fresh active-view id set (only known record ids)."""
        known = set(r.element_id for r in self._records)
        self._view_ids = set(view_ids) & known
        for r in self._records:
            r.in_active_view = r.element_id in self._view_ids
        self._update_status()

    def apply_refresh(self, document, records, elevations, unsupported=False):
        """Rebind to document/records; keep levels, search text and checks."""
        self._doc = document
        self._doc_key = doc_key_of(document)
        self._records = records
        self._elevations = elevations
        self._view_ids = set(r.element_id for r in records if r.in_active_view)
        self._scope_ids = set(self._view_ids)
        self._view_unsupported = unsupported
        self._reapply_scope()

    def _on_view_activated(self, sender, args):
        """ViewActivated runs in API context; never let an exception escape."""
        try:
            if self._closed:
                return
            document = args.Document
            if doc_key_of(document) != self._doc_key:
                return
            view = args.CurrentActiveView
            try:
                unsupported = revit_adapter.view_isolate_problem(view) is not None
            except Exception:
                unsupported = True
            try:
                ids = revit_adapter.active_view_ids(document, view)
            except Exception:
                ids = set()  # e.g. a view the collector cannot filter
                unsupported = True
            self._view_unsupported = unsupported
            self._scope_ids = set(ids)
            self.set_view_ids(ids)
            if self._scope == core.SCOPE_VIEW:
                self._reapply_scope()  # tree and levels follow the new view
        except Exception:
            pass

    def _on_closed(self, sender, args):
        self._closed = True
        self._timer.Stop()
        try:
            __revit__.ViewActivated -= self._view_handler
        except Exception:
            pass
        if get_open_window() is self:
            set_open_window(None)
        self._queue.drain()
        try:
            self._event.Dispose()
        except Exception:
            pass


class RequestHandler(UI.IExternalEventHandler):
    """Runs the window's queued requests in a valid Revit API context."""

    def __init__(self, window):
        self._window = window

    def Execute(self, uiapp):
        try:
            for request in self._window.take_requests():
                try:
                    process_request(uiapp, self._window, request)
                except Exception as ex:
                    forms.alert("Advanced Filter failed:\n%s" % ex,
                                title="Advanced Filter")
        except Exception:
            pass

    def GetName(self):
        return "Advanced Filter"


def isolate(doc, view, int_ids):
    ids = List[DB.ElementId]()
    for i in int_ids:
        ids.Add(DB.ElementId(i))
    txn = DB.Transaction(doc, "Advanced Filter: Isolate")
    try:
        txn.Start()
        view.IsolateElementsTemporary(ids)
        txn.Commit()
        return True
    except Exception as ex:
        if txn.HasStarted():
            txn.RollBack()
        forms.alert("Isolate failed:\n%s" % ex, title="Advanced Filter")
        return False


def isolate_fresh(doc, view, int_ids):
    """Isolate int_ids in a view that may already be temporarily isolated.

    One TransactionGroup (one Ctrl+Z): leave the old isolate, rebuild the view
    id set, isolate what is in view. Returns (ok, in_view, view_ids); ok with
    an empty in_view means nothing was in view (group rolled back, no alert).
    On failure it alerts, rolls back and returns (False, [], view_ids or None).
    """
    group = DB.TransactionGroup(doc, "Advanced Filter: Isolate")
    view_ids = None
    try:
        group.Start()
        if revit_adapter.in_temporary_isolate(view):
            reset = DB.Transaction(doc, "Advanced Filter: Reset isolate")
            try:
                reset.Start()
                revit_adapter.disable_temporary_isolate(view)
                reset.Commit()
            except Exception:
                if reset.HasStarted():
                    reset.RollBack()
                raise
        view_ids = revit_adapter.active_view_ids(doc, view)
        in_view = core.ids_in_view(int_ids, view_ids)
        if not in_view:
            group.RollBack()
            return True, [], view_ids
        if not isolate(doc, view, in_view):  # alerts and rolls back its own txn
            group.RollBack()
            return False, [], view_ids
        group.Assimilate()
        return True, in_view, view_ids
    except Exception as ex:
        if group.HasStarted():
            group.RollBack()
        forms.alert("Isolate failed:\n%s" % ex, title="Advanced Filter")
        return False, [], view_ids


def _id_list(int_ids):
    return [DB.ElementId(i) for i in int_ids]


def apply_colour(doc, view, int_ids, rgb):
    txn = DB.Transaction(doc, "Advanced Filter: Colour override")
    try:
        txn.Start()
        fill_id = revit_adapter.solid_fill_id(doc)
        if fill_id is None:
            txn.RollBack()
            forms.alert("No solid fill pattern found in this project.",
                        title="Advanced Filter")
            return False
        ogs = revit_adapter.build_overrides(colour.override_plan(rgb, fill_id))
        for eid in _id_list(int_ids):
            view.SetElementOverrides(eid, ogs)
        txn.Commit()
        return True
    except Exception as ex:
        if txn.HasStarted():
            txn.RollBack()
        forms.alert("Colour override failed:\n%s" % ex, title="Advanced Filter")
        return False


def reset_colours(doc, view, int_ids):
    txn = DB.Transaction(doc, "Advanced Filter: Reset colours")
    try:
        txn.Start()
        for eid in _id_list(int_ids):
            view.SetElementOverrides(eid, DB.OverrideGraphicSettings())
        txn.Commit()
        return True
    except Exception as ex:
        if txn.HasStarted():
            txn.RollBack()
        forms.alert("Reset colours failed:\n%s" % ex, title="Advanced Filter")
        return False


def notify(message):
    """Non-blocking notice: toast, else balloon, else plain alert."""
    toast = getattr(forms, "toast", None)
    if toast is not None:
        try:
            toast(message, title="Advanced Filter")
            return
        except Exception:
            pass
    balloon = getattr(forms, "show_balloon", None)
    if balloon is not None:
        try:
            balloon("Advanced Filter", message)
            return
        except Exception:
            pass
    forms.alert(message, title="Advanced Filter", warn_icon=False)


def process_request(uiapp, window, request):
    """Run one queued request against the *current* active document and view."""
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None:
        forms.alert("Open a Revit project first.", title="Advanced Filter")
        return
    doc = uidoc.Document
    view = doc.ActiveView
    if request.action == session.REFRESH:
        if view is None:
            forms.alert("There is no active view.", title="Advanced Filter")
            return
        records, elevations = revit_adapter.collect_records(doc, view)
        if not records:
            forms.alert("No model elements found in this project.",
                        title="Advanced Filter")
            return
        window.apply_refresh(
            doc, records, elevations,
            revit_adapter.view_isolate_problem(view) is not None)
        window.show_status("Refreshed: %d elements" % len(records))
        return

    message = session.document_guard(window.doc_key(), doc_key_of(doc))
    if message:
        window.show_status(message)
        forms.alert(message, title="Advanced Filter")
        return
    problem = revit_adapter.view_isolate_problem(view)
    if problem:
        forms.alert(problem, title="Advanced Filter")
        return
    if request.action == session.ISOLATE:
        ok, in_view, view_ids = isolate_fresh(doc, view, request.ids)
        if view_ids is not None:
            window.set_view_ids(view_ids)
        if ok and not in_view:
            forms.alert("None of the checked elements are in the active view.",
                        title="Advanced Filter")
            return
    else:
        view_ids = revit_adapter.active_view_ids(doc, view)
        window.set_view_ids(view_ids)
        in_view = core.ids_in_view(request.ids, view_ids)
        if not in_view:
            forms.alert("None of the checked elements are in the active view.",
                        title="Advanced Filter")
            return
    if request.action == session.COLOUR:
        ok = apply_colour(doc, view, in_view, request.rgb)
    elif request.action == session.RESET:
        ok = reset_colours(doc, view, in_view)
    elif request.action != session.ISOLATE:
        return
    if ok:
        window.show_status(session.result_text(request.action, len(in_view)))
        notice = core.hidden_notice(len(request.ids), len(in_view))
        if notice:
            notify(notice)


def main():
    existing = get_open_window()
    if existing is not None:
        try:
            if existing.WindowState == WindowState.Minimized:
                existing.WindowState = WindowState.Normal
            existing.Activate()
            return
        except Exception:
            set_open_window(None)  # stale reference: open a fresh window

    uidoc = __revit__.ActiveUIDocument
    doc = uidoc.Document if uidoc else None
    if doc is None:
        forms.alert("Open a Revit project first.", title="Advanced Filter")
        return
    view = doc.ActiveView
    problem = revit_adapter.view_isolate_problem(view)
    if problem:
        forms.alert(problem, title="Advanced Filter")
        return

    records, elevations = revit_adapter.collect_records(doc, view)
    if not records:
        forms.alert("No model elements found in this project.",
                    title="Advanced Filter")
        return

    window = FilterWindow(script.get_bundle_file("ui.xaml"), records,
                          elevations, doc)
    set_open_window(window)
    try:
        window.setup_owner()  # keep it above the Revit main window
    except Exception:
        pass
    window.Show()


main()
