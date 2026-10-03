# -*- coding: utf-8 -*-
"""Mock-object verification of the search wiring in script.py (no Revit)."""
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "AdvancedFilter.extension", "lib"))
SCRIPT = os.path.join(ROOT, "AdvancedFilter.extension", "BIM Tools.tab",
                      "Filter.panel", "Advanced Filter.pushbutton", "script.py")

from advfilter import core  # noqa: E402


class Evt(object):
    def __init__(self):
        self.handlers = []

    def __iadd__(self, h):
        self.handlers.append(h)
        return self

    def __isub__(self, h):
        self.handlers.remove(h)
        return self

    def fire(self, *args):
        for h in list(self.handlers):
            h(*args)


class FakeCheckBox(object):
    def __init__(self):
        self.Content = None
        self.Tag = None
        self.IsChecked = False
        self.IsThreeState = True
        self.Click = Evt()
        self.Checked = Evt()
        self.Unchecked = Evt()


class FakeRadio(object):
    def __init__(self, checked):
        self.IsChecked = checked
        self.Checked = Evt()


class FakeItems(list):
    def Add(self, x):
        self.append(x)

    def Clear(self):
        del self[:]


class FakeTreeViewItem(object):
    def __init__(self):
        self.Header = None
        self.Items = FakeItems()
        self.Visibility = "Visible"
        self.IsExpanded = False


class FakeTimer(object):
    def __init__(self):
        self.Interval = None
        self.Tick = Evt()
        self.running = False
        self.starts = 0

    def Start(self):
        self.running = True
        self.starts += 1

    def Stop(self):
        self.running = False

    @property
    def IsEnabled(self):
        return self.running


class FakeTextBox(object):
    def __init__(self):
        self.Text = ""
        self.TextChanged = Evt()


class FakeBlock(object):
    Visibility = "Visible"


class FakeExternalEvent(object):
    """Records Raise; tests call the handler's Execute by hand."""
    created = []

    def __init__(self, handler):
        self.handler = handler
        self.raised = 0
        self.disposed = False

    @staticmethod
    def Create(handler):
        ev = FakeExternalEvent(handler)
        FakeExternalEvent.created.append(ev)
        return ev

    def Raise(self):
        self.raised += 1

    def Dispose(self):
        self.disposed = True


class FakeDomain(object):
    def __init__(self):
        self.data = {}

    def GetData(self, key):
        return self.data.get(key)

    def SetData(self, key, value):
        self.data[key] = value


DOMAIN = FakeDomain()


class FakeWPFWindow(object):
    def __init__(self, xaml_file):
        self.Closed = Evt()
        self.WindowState = "Normal"
        self.shown = 0
        self.activated = 0
        self.closed_calls = 0
        self.tree = types.SimpleNamespace(Items=FakeItems()) if hasattr(types, "SimpleNamespace") else None
        self.level_list = types.SimpleNamespace(Items=FakeItems())
        self.all_levels = types.SimpleNamespace(
            IsChecked=True, Checked=Evt(), Unchecked=Evt())
        self.scope_project = FakeRadio(True)
        self.scope_view = FakeRadio(False)
        self.search_box = FakeTextBox()
        self.search_hint = FakeBlock()
        self.status_text = types.SimpleNamespace(Text="", Foreground=None)
        self.isolate_button = types.SimpleNamespace(IsEnabled=True)
        self.colour_check = types.SimpleNamespace(IsChecked=False)
        self.colour_swatch = types.SimpleNamespace(Visibility="Collapsed", Background=None)
        self.apply_colour_button = types.SimpleNamespace(IsEnabled=True)
        self.reset_colours_button = types.SimpleNamespace(IsEnabled=True)

    def Show(self):
        self.shown += 1

    def Activate(self):
        self.activated += 1

    def setup_owner(self):
        pass

    def Close(self):
        self.closed_calls += 1
        self.Closed.fire(self, None)


CONFIG = types.SimpleNamespace()
SAVES = []


def load_script(fresh=True):
    """Exec script.py against fake modules; fresh=False keeps the AppDomain slot."""
    mods = {}
    if fresh:
        DOMAIN.data.clear()
        del FakeExternalEvent.created[:]

    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        mods[name] = m
        return m

    class Vis(object):
        Visible = "Visible"
        Collapsed = "Collapsed"

    clr = mod("clr", AddReference=lambda n: None)
    mod("System", Array=None, AppDomain=types.SimpleNamespace(CurrentDomain=DOMAIN),
        TimeSpan=types.SimpleNamespace(FromMilliseconds=lambda ms: ms))
    mod("System.Collections")
    mod("System.Collections.Generic", List=list)
    mod("System.Windows", Visibility=Vis,
        WindowState=types.SimpleNamespace(Minimized="Minimized", Normal="Normal"))
    mod("System.Windows.Threading", DispatcherTimer=FakeTimer)
    mod("System.Windows.Controls", CheckBox=FakeCheckBox,
        TreeViewItem=FakeTreeViewItem)
    mod("System.Windows.Media",
        SolidColorBrush=lambda c: ("brush", c),
        Color=types.SimpleNamespace(FromRgb=lambda r, g, b: (r, g, b)))
    mod("Autodesk")
    mod("Autodesk.Revit", DB=types.SimpleNamespace(),
        UI=types.SimpleNamespace(IExternalEventHandler=object,
                                 ExternalEvent=FakeExternalEvent))
    mod("pyrevit", forms=types.SimpleNamespace(
        WPFWindow=FakeWPFWindow, alert=lambda *a, **k: None),
        script=types.SimpleNamespace(
            get_config=lambda: CONFIG, save_config=lambda: SAVES.append(1)))
    saved = dict((k, sys.modules.get(k)) for k in mods)
    sys.modules.update(mods)
    try:
        ns = {"__revit__": types.SimpleNamespace(ActiveUIDocument=None,
                                                 ViewActivated=Evt()),
              "__name__": "script_under_test"}
        with open(SCRIPT, "rb") as f:
            exec(compile(f.read(), SCRIPT, "exec"), ns)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return ns


def rec(eid, cat, fam, typ, level="L1"):
    return core.ElementRecord(eid, cat, fam, typ, True, level)


@unittest.skipUnless(hasattr(types, "SimpleNamespace"), "needs CPython 3")
class ScriptSearchTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_script()
        records = [rec(1, "Walls", "Basic Wall", "Generic 200"),
                   rec(2, "Walls", "Basic Wall", "Generic 300"),
                   rec(3, "Doors", "Single", "D1"),
                   rec(4, "Doors", "Single", "D2", level="L2")]
        self.w = self.ns["FilterWindow"]("x.xaml", records, {"L1": 0.0, "L2": 4.0})

    def node(self, name):
        for n in self.w._items:
            if n.name == name:
                return n

    def vis(self, name):
        return self.w._items[self.node(name)].Visibility

    def search(self, text):
        self.w.search_box.Text = text
        self.w._on_search_changed(None, None)
        self.w._on_search_tick(None, None)

    def test_all_visible_initially_and_timer_interval(self):
        self.assertTrue(all(i.Visibility == "Visible" for i in self.w._items.values()))
        self.assertEqual(self.w._timer.Interval, 200)

    def test_debounce_restarts_timer_and_toggles_hint(self):
        self.w.search_box.Text = "w"
        self.w._on_search_changed(None, None)
        self.w.search_box.Text = "wa"
        self.w._on_search_changed(None, None)
        self.assertEqual(self.w._timer.starts, 2)
        self.assertTrue(self.w._timer.running)
        self.assertEqual(self.w.search_hint.Visibility, "Collapsed")
        # Nothing applied until the tick fires.
        self.assertIsNone(self.w._visible)

    def test_search_hides_and_expands(self):
        self.search("generic 200")
        self.assertEqual(self.vis("Generic 200"), "Visible")
        self.assertEqual(self.vis("Generic 300"), "Collapsed")
        self.assertEqual(self.vis("Doors"), "Collapsed")
        self.assertTrue(self.w._items[self.node("Walls")].IsExpanded)

    def test_clear_restores_full_tree(self):
        self.search("zzz")
        self.assertTrue(all(i.Visibility == "Collapsed" for i in self.w._items.values()))
        self.w.search_clear_click(None, None)
        self.assertEqual(self.w.search_box.Text, "")
        self.assertTrue(all(i.Visibility == "Visible" for i in self.w._items.values()))
        self.assertFalse(self.w._timer.running)

    def test_check_states_preserved_across_search(self):
        g200 = self.node("Generic 200")
        core.set_checked(g200, True)
        self.search("doors")
        self.assertTrue(g200.state)
        self.search("")
        self.assertEqual(core.checked_element_ids(self.w._roots), [1])

    def test_parent_click_under_search_affects_visible_only(self):
        self.search("generic 200")
        walls = self.node("Walls")
        box = [b for n, b in self.w._boxes if n is walls][0]
        self.w._on_click(box, None)
        self.assertIs(self.node("Generic 200").state, True)
        self.assertIs(self.node("Generic 300").state, False)
        # Box keeps showing the full state: indeterminate.
        self.assertIsNone(box.IsChecked)
        self.w._on_click(box, None)
        self.assertIs(self.node("Generic 200").state, False)

    def test_level_rebuild_reapplies_search(self):
        self.search("single")
        d2 = self.node("D2")
        self.assertEqual(self.vis("D2"), "Visible")
        self.w._level_boxes[1].IsChecked = False  # untick L2
        self.w._on_level_toggle(None, None)
        self.assertIsNone(self.node("D2"))
        self.assertEqual(self.vis("Single"), "Visible")
        self.assertEqual(self.vis("Walls"), "Collapsed")
        self.assertEqual(self.vis("D1"), "Visible")


if __name__ == "__main__":
    unittest.main()
