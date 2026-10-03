# -*- coding: utf-8 -*-
"""Advanced Filter: collect project -> Category/Family/Type tree -> Isolate."""
import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Collections.Generic import List
import System
from System import TimeSpan
from System.Windows import Visibility
from System.Windows.Media import SolidColorBrush, Color
from System.Windows.Threading import DispatcherTimer
from System.Windows.Controls import CheckBox, TreeViewItem
from Autodesk.Revit import DB
from pyrevit import forms, script

from advfilter import core, colour, revit_adapter

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document if uidoc else None


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


class FilterWindow(forms.WPFWindow):
    def __init__(self, xaml_file, records, elevations):
        forms.WPFWindow.__init__(self, xaml_file)
        self._records = records
        self._view_ids = set(r.element_id for r in records if r.in_active_view)
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
        self.ids_to_isolate = None
        self.action = None  # "isolate" / "colour" / "reset" once the window closes
        self.action_ids = None
        self.colour_rgb, self._custom_colors = load_colour_state()
        self._m = 0
        self.counts = (0, 0)  # (N, M) captured when Isolate closes the window
        self._fg_brush = SolidColorBrush(Color.FromRgb(0xE6, 0xE6, 0xE6))
        self._muted_brush = SolidColorBrush(Color.FromRgb(0x80, 0x80, 0x80))
        self._level_boxes = []
        for name in core.ordered_levels(records, elevations):
            box = CheckBox()
            box.Content = name
            box.IsChecked = True
            box.Checked += self._on_level_toggle
            box.Unchecked += self._on_level_toggle
            self._level_boxes.append(box)
            self.level_list.Items.Add(box)
        self.all_levels.Checked += self._on_all_toggle
        self.all_levels.Unchecked += self._on_all_toggle
        self._rebuild()

    def _selected_levels(self):
        return [b.Content for b in self._level_boxes if b.IsChecked]

    def _rebuild(self):
        """Rebuild the tree for the selected levels, keeping check states."""
        self._checked = core.merge_checked_paths(self._checked, self._roots)
        selected = self._selected_levels()
        if selected:
            records = core.filter_by_levels(self._records, selected)
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
        if n == 0:
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

    def _checked_in_view(self):
        """Checked ids in the active view, or None after showing an alert."""
        self._flush_search()
        checked = core.checked_element_ids(self._roots)
        if not checked:
            forms.alert("Check at least one category, family or type.",
                        title="Advanced Filter")
            return None
        in_view = core.ids_in_view(checked, self._view_ids)
        if not in_view:
            forms.alert("None of the checked elements are in the active view.",
                        title="Advanced Filter")
            return None
        return in_view

    def _finish(self, action, in_view):
        self.counts = core.selection_counts(self._roots, self._view_ids)
        self.action = action
        self.action_ids = in_view
        self.Close()

    def apply_colour_click(self, sender, args):
        if self.colour_rgb is None:
            forms.alert("Choose a colour first.", title="Advanced Filter")
            return
        in_view = self._checked_in_view()
        if in_view:
            self._finish("colour", in_view)

    def reset_colours_click(self, sender, args):
        in_view = self._checked_in_view()
        if in_view:
            self._finish("reset", in_view)

    def isolate_click(self, sender, args):
        in_view = self._checked_in_view()
        if not in_view:
            return
        self.ids_to_isolate = in_view
        self._finish("isolate", in_view)

    def cancel_click(self, sender, args):
        self.Close()


def isolate(view, int_ids):
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


def _id_list(int_ids):
    return [DB.ElementId(i) for i in int_ids]


def apply_colour(view, int_ids, rgb):
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


def reset_colours(view, int_ids):
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


def main():
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

    window = FilterWindow(script.get_bundle_file("ui.xaml"), records, elevations)
    window.ShowDialog()
    ok = False
    if window.action == "isolate":
        ok = isolate(view, window.action_ids)
    elif window.action == "colour":
        ok = apply_colour(view, window.action_ids, window.colour_rgb)
    elif window.action == "reset":
        ok = reset_colours(view, window.action_ids)
    if ok:
        notice = core.hidden_notice(*window.counts)
        if notice:
            notify(notice)


main()
