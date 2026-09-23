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
            {"location_id": "352061", "location_name": "Miami", "record_ids": ["coin-1"]}
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
            {"location_id": "352061", "location_name": "Miami", "record_ids": ["coin-1"]}
        )

        self.assertTrue(result)
        self.assertEqual(run.call_count, 4)
        dry_run = run.call_args_list[2].args[0]
        apply_run = run.call_args_list[3].args[0]
        self.assertIn("update_souvenir_manifest_api.py", " ".join(dry_run))
        self.assertNotIn("--apply", dry_run)
        self.assertIn("--record-id", dry_run)
        self.assertIn("coin-1", dry_run)
        self.assertEqual(apply_run, [*dry_run, "--apply"])
        promote_run = run.call_args_list[0].args[0]
        self.assertIn("--record-id", promote_run)
        self.assertIn("coin-1", promote_run)
        self.assertIn("--replace-existing", promote_run)


if __name__ == "__main__":
    unittest.main()
