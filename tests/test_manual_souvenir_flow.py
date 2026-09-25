import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import main


class ManualSouvenirFinalizationTests(unittest.TestCase):
    def git_results(self, sha="a" * 40):
        return ["", "", sha, f"{sha}\trefs/heads/main"]

    @patch.object(main, "verify_souvenir_raw_images", return_value=False)
    @patch.object(main, "run_git")
    @patch.object(main, "run", return_value=True)
    @patch.object(main, "worktree_has_only_souvenir_location_changes", return_value=True)
    def test_never_updates_base44_when_raw_publication_is_not_verified(
        self, _guard, run, run_git, _verify
    ):
        run_git.side_effect = self.git_results()

        result = main.finalize_manual_souvenirs(
            {
                "location_id": "352061", "location_name": "Miami",
                "continent": "América", "country": "EUA", "city": "Miami",
                "record_sides": ["coin-1:front"],
            }
        )

        self.assertFalse(result)
        self.assertEqual(run.call_count, 2)
        self.assertNotIn("update_souvenir_manifest_api.py", " ".join(run.call_args_list[-1].args[0]))

    @patch.object(main, "verify_souvenir_raw_images", return_value=True)
    @patch.object(main, "run_git")
    @patch.object(main, "run", return_value=True)
    @patch.object(main, "worktree_has_only_souvenir_location_changes", return_value=True)
    def test_runs_dry_run_before_applying_base44_updates(
        self, _guard, run, run_git, _verify
    ):
        run_git.side_effect = self.git_results()

        result = main.finalize_manual_souvenirs(
            {
                "location_id": "352061", "location_name": "Miami",
                "continent": "América", "country": "EUA", "city": "Miami",
                "record_sides": ["coin-1:front"],
            }
        )

        self.assertTrue(result)
        self.assertEqual(run.call_count, 4)
        dry_run = run.call_args_list[2].args[0]
        apply_run = run.call_args_list[3].args[0]
        self.assertIn("update_souvenir_manifest_api.py", " ".join(dry_run))
        self.assertNotIn("--apply", dry_run)
        self.assertIn("--record-side", dry_run)
        self.assertIn("coin-1:front", dry_run)
        self.assertEqual(apply_run, [*dry_run, "--apply"])
        promote_run = run.call_args_list[0].args[0]
        self.assertIn("--record-side", promote_run)
        self.assertIn("coin-1:front", promote_run)
        self.assertIn("--country-dir", promote_run)
        self.assertIn("--replace-existing", promote_run)

    def test_acknowledge_removes_only_successful_photos_from_queue(self):
        with TemporaryDirectory() as temporary:
            staging = Path(temporary)
            statuses = {
                "done": {"completed": True, "queued": True},
                "waiting": {"completed": True, "queued": True},
            }
            (staging / "photo-status.json").write_text(
                json.dumps(statuses), encoding="utf-8"
            )
            (staging / "record-type-overrides.json").write_text(
                json.dumps({"coin-1": "coin", "coin-2": "other"}),
                encoding="utf-8",
            )
            with patch.object(main, "SOUVENIR_STAGING", staging):
                main.acknowledge_manual_souvenir_request({
                    "photo_status_keys": ["done"],
                    "record_ids": ["coin-1"],
                })
            saved = json.loads(
                (staging / "photo-status.json").read_text(encoding="utf-8")
            )
            overrides = json.loads(
                (staging / "record-type-overrides.json").read_text(encoding="utf-8")
            )

        self.assertFalse(saved["done"]["queued"])
        self.assertTrue(saved["waiting"]["queued"])
        self.assertEqual(overrides, {"coin-2": "other"})

    @patch.object(main, "acknowledge_manual_souvenir_request")
    @patch.object(main, "finalize_manual_souvenirs", side_effect=[True, False])
    def test_global_queue_processes_all_locations_and_acknowledges_only_successes(
        self, finalize, acknowledge
    ):
        first = {"location_id": "one", "record_sides": ["a:front"]}
        second = {"location_id": "two", "record_sides": ["b:front"]}

        result = main.finalize_manual_souvenir_queue({
            "locations": 2,
            "photos": 2,
            "sides": 2,
            "batches": [first, second],
        })

        self.assertFalse(result)
        self.assertEqual(finalize.call_count, 2)
        acknowledge.assert_called_once_with(first)


if __name__ == "__main__":
    unittest.main()
