from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from scripts.admin_stats_sync import (
    AdminStatsSyncError,
    MutationRun,
    mark_numisvault_stats_stale,
)


class FakeRequest:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def __call__(self, method, path, api_key, payload=None, query=None):
        self.calls.append((method, path, api_key, payload, query))
        if method == "GET" and path == "/entities/AdminStats":
            return [dict(record) for record in self.records]
        if method == "PUT":
            self.records[0].update(payload)
            return dict(self.records[0])
        if method == "GET" and path.startswith("/entities/AdminStats/"):
            return dict(self.records[0])
        raise AssertionError((method, path))


class AdminStatsSyncTests(unittest.TestCase):
    def test_marker_reads_one_record_and_uses_partial_put(self):
        request = FakeRequest([{"id": "stats-1", "needs_rebuild": False, "total": 9}])

        with redirect_stdout(io.StringIO()):
            changed = mark_numisvault_stats_stale("secret", request)

        self.assertTrue(changed)
        self.assertEqual(
            request.calls[0],
            ("GET", "/entities/AdminStats", "secret", None, {"limit": 2}),
        )
        self.assertEqual(
            request.calls[1],
            (
                "PUT",
                "/entities/AdminStats/stats-1",
                "secret",
                {"needs_rebuild": True},
                None,
            ),
        )

    def test_marker_does_not_write_when_already_true(self):
        request = FakeRequest([{"id": "stats-1", "needs_rebuild": True}])
        with redirect_stdout(io.StringIO()):
            changed = mark_numisvault_stats_stale("secret", request)
        self.assertFalse(changed)
        self.assertEqual(len(request.calls), 1)

    def test_zero_successful_mutations_do_not_mark(self):
        calls = []
        with MutationRun(lambda: calls.append("marked")):
            pass
        self.assertEqual(calls, [])

    def test_one_or_multiple_mutations_mark_exactly_once(self):
        for count in (1, 4):
            calls = []
            with redirect_stdout(io.StringIO()):
                with MutationRun(lambda: calls.append("marked")) as run:
                    run.record_success(count)
            self.assertEqual(calls, ["marked"])

    def test_partial_failure_marks_and_preserves_original_error(self):
        calls = []
        with self.assertRaisesRegex(ValueError, "original"):
            with redirect_stdout(io.StringIO()):
                with MutationRun(lambda: calls.append("marked")) as run:
                    run.record_success()
                    raise ValueError("original")
        self.assertEqual(calls, ["marked"])

    def test_failure_before_mutation_does_not_mark(self):
        calls = []
        with self.assertRaisesRegex(ValueError, "before"):
            with MutationRun(lambda: calls.append("marked")):
                raise ValueError("before")
        self.assertEqual(calls, [])

    def test_marker_failure_is_non_successful_without_original_error(self):
        def fail_marker():
            raise RuntimeError("marker unavailable")

        with (
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as stderr,
            self.assertRaises(AdminStatsSyncError),
        ):
            with MutationRun(fail_marker) as run:
                run.record_success()
        self.assertIn("CRITICAL", stderr.getvalue())

    def test_marker_failure_preserves_original_error(self):
        def fail_marker():
            raise RuntimeError("marker unavailable")

        with (
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as stderr,
            self.assertRaisesRegex(ValueError, "original"),
        ):
            with MutationRun(fail_marker) as run:
                run.record_success()
                raise ValueError("original")
        self.assertIn("CRITICAL", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
