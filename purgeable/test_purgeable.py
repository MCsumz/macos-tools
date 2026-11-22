"""Tests for purgeable.py. The last class reads the real CacheDelete numbers (read-only) on macOS.

    python3 -m unittest -v test_purgeable
"""
import io
import json
import os
import platform
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import purgeable  # noqa: E402

GROUP_KEYS = ["snapshots", "assets", "cloud_files", "app_data", "spotlight", "caches"]


class Grouping(unittest.TestCase):
    def test_services_land_in_their_group_and_unknown_ones_in_caches(self):
        groups = purgeable.group({
            "CACHE_DELETE_TOTAL_AVAILABLE": 999,
            "com.apple.TMCacheDelete": 500,
            "com.apple.mobileassetd.cache-delete": 30, "com.apple.installd.CacheDelete": 20,
            "com.apple.fspurgeable_document": 7,
            "com.apple.metadata.mds.cachedelete": 3,
            "com.example.unknown": 11, "com.apple.something-new": 4,
            "com.apple.fspurgeable_data": 0,
        })
        self.assertEqual(list(groups), GROUP_KEYS)
        self.assertEqual(groups, {"snapshots": 500, "assets": 50, "cloud_files": 7, "app_data": 0,
                                  "spotlight": 3, "caches": 15})

    def test_sizes_use_decimal_units_like_finder(self):
        self.assertEqual([purgeable.size(v) for v in (2_500_000_000_000, 12_345_678_901, 4_500_000, 700)],
                         ["2.5 TB", "12.3 GB", "4.5 MB", "1 KB"])


class Purge(unittest.TestCase):
    def run_purge(self, scans, frees):
        scans, frees = iter(scans), iter(frees)
        with mock.patch.object(purgeable, "purgeable_space", lambda: next(scans)), \
                mock.patch.object(purgeable, "free_bytes", lambda: next(frees)), \
                mock.patch.object(purgeable, "purge_cache_delete") as call, \
                mock.patch.object(purgeable.time, "sleep") as sleep:
            return purgeable.purge(), call, sleep

    def test_asks_for_everything_plus_headroom_and_waits_for_it_to_settle(self):
        groups = dict.fromkeys(GROUP_KEYS, 0)
        result, call, sleep = self.run_purge(
            [(5000, groups), (900, groups), (40, groups), (40, groups)], [100, 4900])
        call.assert_called_once_with(5000 + (1 << 30))
        self.assertEqual(sleep.call_count, 2)  # 900 -> 40 changed, 40 -> 40 settled
        self.assertEqual((result["state"], result["freed"], result["purgeable"], result["free"]),
                         ("purged", 4800, 40, 4900))

    def test_nothing_purgeable_makes_no_call(self):
        groups = dict.fromkeys(GROUP_KEYS, 0)
        result, call, _ = self.run_purge([(0, groups)] * 3, [100, 100])
        call.assert_not_called()
        self.assertEqual((result["state"], result["freed"]), ("no_change", 0))

    def test_free_space_that_shrank_counts_as_nothing_freed(self):
        groups = dict.fromkeys(GROUP_KEYS, 0)
        result, _, _ = self.run_purge([(10, groups)] * 3, [500, 400])
        self.assertEqual((result["state"], result["freed"]), ("no_change", 0))


class CommandLine(unittest.TestCase):
    def setUp(self):
        patches = [mock.patch.object(purgeable.platform, "system", return_value="Darwin"),
                   mock.patch.object(purgeable, "purgeable_space",
                                     return_value=(3_000_000_000, {"snapshots": 2_000_000_000, "assets": 0,
                                                                   "cloud_files": 0, "app_data": 0,
                                                                   "spotlight": 0, "caches": 1_000_000_000})),
                   mock.patch.object(purgeable, "free_bytes", return_value=50_000_000_000)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.purge = mock.patch.object(purgeable, "purge", return_value={
            "state": "purged", "purgeable": 0, "groups": dict.fromkeys(GROUP_KEYS, 0),
            "free": 53_000_000_000, "freed": 3_000_000_000}).start()
        self.addCleanup(mock.patch.stopall)

    def run_main(self, argv, tty=True, answer=""):
        out, err = io.StringIO(), io.StringIO()
        stdin = mock.Mock(isatty=lambda: tty)
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err), \
                mock.patch.object(sys, "stdin", stdin), mock.patch("builtins.input", return_value=answer):
            code = purgeable.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_scan_is_the_default_and_names_the_groups(self):
        code, out, _ = self.run_main([])
        self.assertEqual(code, 0)
        self.assertIn("Free now: 50.0 GB. Purgeable: 3.0 GB.", out)
        self.assertIn("Time Machine local snapshots", out)
        self.assertIn("Other system caches", out)
        self.assertNotIn("Spotlight", out)  # empty groups are left out
        self.purge.assert_not_called()

    def test_scan_as_json(self):
        code, out, _ = self.run_main(["scan", "--json"])
        self.assertEqual((code, json.loads(out)["purgeable"]), (0, 3_000_000_000))

    def test_purge_asks_first_and_a_no_changes_nothing(self):
        code, out, _ = self.run_main(["purge"], answer="n")
        self.assertEqual(code, 1)
        self.assertIn("Nothing was changed.", out)
        self.purge.assert_not_called()

    def test_ctrl_d_or_ctrl_c_at_the_question_is_a_no(self):
        for error in (EOFError, KeyboardInterrupt):
            with self.subTest(error=error.__name__), mock.patch("builtins.input", side_effect=error):
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err), \
                        mock.patch.object(sys, "stdin", mock.Mock(isatty=lambda: True)):
                    code = purgeable.main(["purge"])
                self.assertEqual(code, 1)
                self.assertIn("Nothing was changed.", out.getvalue())
        self.purge.assert_not_called()

    def test_purge_after_yes(self):
        code, out, _ = self.run_main(["purge"], answer="y")
        self.assertEqual(code, 0)
        self.assertIn("Freed 3.0 GB.", out)
        self.assertIn("Still purgeable: 0 KB.", out)

    def test_purge_never_runs_unasked_without_a_terminal_or_with_json(self):
        for argv, tty in ((["purge"], False), (["purge", "--json"], True)):
            with self.subTest(argv=argv, tty=tty):
                code, _, err = self.run_main(argv, tty=tty)
                self.assertEqual(code, 2)
                self.assertIn("--yes", err)
        self.purge.assert_not_called()

    def test_purge_yes_skips_the_question(self):
        code, out, _ = self.run_main(["purge", "--yes", "--json"], tty=False)
        self.assertEqual((code, json.loads(out)["freed"]), (0, 3_000_000_000))

    def test_a_changed_private_framework_is_reported_not_a_traceback(self):
        with mock.patch.object(purgeable, "scan", side_effect=AttributeError("no such symbol")):
            code, _, err = self.run_main([])
        self.assertEqual(code, 1)
        self.assertIn("CacheDelete failed: AttributeError", err)

    def test_other_systems_are_refused(self):
        with mock.patch.object(purgeable.platform, "system", return_value="Linux"):
            code, _, err = self.run_main([])
        self.assertEqual(code, 2)
        self.assertIn("macOS only", err)


# The framework lives in the dyld shared cache, not as a file on disk, so only the platform is checked.
@unittest.skipUnless(platform.system() == "Darwin", "reads the real CacheDelete numbers on macOS")
class RealMac(unittest.TestCase):
    def test_scan_reads_real_numbers(self):
        result = purgeable.scan()
        self.assertEqual(result["state"], "scanned")
        self.assertGreaterEqual(result["purgeable"], 0)
        self.assertGreater(result["free"], 0)
        self.assertEqual(list(result["groups"]), GROUP_KEYS)


if __name__ == "__main__":
    unittest.main()
