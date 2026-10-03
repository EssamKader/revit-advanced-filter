# -*- coding: utf-8 -*-
"""Pure session logic for the modeless window (US-11). No Revit imports."""

ISOLATE = "isolate"
COLOUR = "colour"
RESET = "reset"
REFRESH = "refresh"
MODEL_ACTIONS = (ISOLATE, COLOUR, RESET)

DOC_CHANGED_MESSAGE = u"The active document changed — click Refresh"

_VERBS = {ISOLATE: "Isolated", COLOUR: "Coloured", RESET: "Reset"}


def result_text(action, count):
    """'Isolated 12 elements' / 'Coloured 1 element' / 'Reset 3 elements'."""
    noun = "element" if count == 1 else "elements"
    return "%s %d %s" % (_VERBS[action], count, noun)


def doc_key(path_name, title):
    """Identity of a document: saved path plus title (unsaved docs have no path)."""
    return (path_name or "", title or "")


def document_guard(window_doc_key, active_doc_key):
    """None when the active document is the window's, else the user message."""
    if active_doc_key is None or window_doc_key != active_doc_key:
        return DOC_CHANGED_MESSAGE
    return None


def merge_level_selection(old_selected, old_all, new_levels):
    """Selected level names after a Refresh, in new_levels order.

    Levels that existed before keep their state; new levels default to selected.
    """
    selected = set(old_selected)
    known = set(old_all)
    return [name for name in new_levels
            if name in selected or name not in known]


class Request(object):
    """One queued action: ids are the checked element ids at click time."""

    def __init__(self, action, ids=None, rgb=None):
        self.action = action
        self.ids = list(ids) if ids else []
        self.rgb = rgb


class RequestQueue(object):
    """FIFO of requests. ExternalEvent.Raise coalesces, so Execute drains all."""

    def __init__(self):
        self._items = []

    def put(self, request):
        self._items.append(request)

    def drain(self):
        items, self._items = self._items, []
        return items

    def __len__(self):
        return len(self._items)
