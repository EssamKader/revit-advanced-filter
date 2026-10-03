# -*- coding: utf-8 -*-
"""Pure tests for lib/advfilter/session.py (US-11)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "AdvancedFilter.extension", "lib"))

from advfilter import session  # noqa: E402


class ResultTextTests(unittest.TestCase):
    def test_plural_and_singular(self):
        self.assertEqual(session.result_text("isolate", 12), "Isolated 12 elements")
        self.assertEqual(session.result_text("colour", 1), "Coloured 1 element")
        self.assertEqual(session.result_text("reset", 3), "Reset 3 elements")
        self.assertEqual(session.result_text("isolate", 0), "Isolated 0 elements")


class DocumentGuardTests(unittest.TestCase):
    def test_same_document(self):
        key = session.doc_key("C:/a.rvt", "A")
        self.assertIsNone(session.document_guard(key, session.doc_key("C:/a.rvt", "A")))

    def test_different_path_or_title(self):
        key = session.doc_key("C:/a.rvt", "A")
        self.assertEqual(session.document_guard(key, session.doc_key("C:/b.rvt", "A")),
                         session.DOC_CHANGED_MESSAGE)
        self.assertEqual(session.document_guard(key, session.doc_key("C:/a.rvt", "B")),
                         session.DOC_CHANGED_MESSAGE)

    def test_unsaved_documents_use_title(self):
        a = session.doc_key(None, "Project1")
        self.assertIsNone(session.document_guard(a, session.doc_key("", "Project1")))
        self.assertIsNotNone(session.document_guard(a, session.doc_key("", "Project2")))

    def test_unreadable_active_document(self):
        self.assertIsNotNone(session.document_guard(session.doc_key("x", "y"), None))

    def test_message_text(self):
        self.assertEqual(session.DOC_CHANGED_MESSAGE,
                         u"The active document changed \u2014 click Refresh")


class MergeLevelTests(unittest.TestCase):
    def test_keeps_old_choices_and_defaults_new_to_selected(self):
        got = session.merge_level_selection(["L1"], ["L1", "L2"], ["L1", "L2", "L3"])
        self.assertEqual(got, ["L1", "L3"])

    def test_removed_levels_dropped_and_order_follows_new(self):
        got = session.merge_level_selection(["L1", "L2"], ["L1", "L2", "L3"], ["L3", "L2"])
        self.assertEqual(got, ["L2"])

    def test_nothing_selected_stays_so_for_known_levels(self):
        self.assertEqual(session.merge_level_selection([], ["L1"], ["L1"]), [])

    def test_empty_old(self):
        self.assertEqual(session.merge_level_selection([], [], ["A", "B"]), ["A", "B"])


class QueueTests(unittest.TestCase):
    def test_fifo_and_drain_empties(self):
        q = session.RequestQueue()
        q.put(session.Request("isolate", (1, 2)))
        q.put(session.Request("colour", [3], (1, 2, 3)))
        self.assertEqual(len(q), 2)
        items = q.drain()
        self.assertEqual([i.action for i in items], ["isolate", "colour"])
        self.assertEqual(items[0].ids, [1, 2])
        self.assertEqual(items[1].rgb, (1, 2, 3))
        self.assertEqual(q.drain(), [])

    def test_request_defaults(self):
        r = session.Request("refresh")
        self.assertEqual((r.ids, r.rgb), ([], None))


if __name__ == "__main__":
    unittest.main()
