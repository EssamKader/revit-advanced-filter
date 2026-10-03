# -*- coding: utf-8 -*-
"""Advanced Filter: collect project -> Category/Family/Type tree -> Isolate."""
import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Collections.Generic import List
from System import TimeSpan
from System.Windows import Visibility
from System.Windows.Threading import DispatcherTimer
from System.Windows.Controls import CheckBox, TreeViewItem
from Autodesk.Revit import DB
from pyrevit import forms, script

from advfilter import core, revit_adapter

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document if uidoc else None


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

    def _on_search_changed(self, sender, args):
        self.search_hint.Visibility = (
            Visibility.Collapsed if self.search_box.Text else Visibility.Visible)
        # Debounce: restart the timer on every keystroke.
        self._timer.Stop()
        self._timer.Start()

    def _on_search_tick(self, sender, args):
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
        node = sender.Tag
        # While a search is active only visible leaves change (US-5); the
        # box itself keeps showing the full node.state so it never misleads.
        core.set_checked(node, core.click_target(node, self._visible),
                         self._visible)
        self._refresh_boxes()

    def _refresh_boxes(self):
        self._busy = True
        try:
            for node, box in self._boxes:
                box.IsChecked = node.state
        finally:
            self._busy = False

    def isolate_click(self, sender, args):
        checked = core.checked_element_ids(self._roots)
        if not checked:
            forms.alert("Check at least one category, family or type.",
                        title="Advanced Filter")
            return
        in_view = core.ids_in_view(checked, self._view_ids)
        if not in_view:
            forms.alert("None of the checked elements are in the active view.",
                        title="Advanced Filter")
            return
        self.ids_to_isolate = in_view
        self.Close()

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
    except Exception as ex:
        if txn.HasStarted():
            txn.RollBack()
        forms.alert("Isolate failed:\n%s" % ex, title="Advanced Filter")


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
    if window.ids_to_isolate:
        isolate(view, window.ids_to_isolate)


main()
