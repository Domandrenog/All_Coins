import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from tools.promote_souvenir_crops import load_entries, photo_status_key
from tools.update_souvenir_manifest_api import load_manifest


class CompletedSouvenirSelectionTests(unittest.TestCase):
    def test_promoter_ignores_an_unfinished_machine(self):
        with TemporaryDirectory() as temporary:
            staging = Path(temporary)
            crop_one = staging / "one.jpg"
            crop_two = staging / "two.jpg"
            Image.new("RGB", (200, 115), "white").save(crop_one)
            Image.new("RGB", (80, 140), "white").save(crop_two)
            first = {
                "location_id": "location-1", "slug": "one", "name": "One",
                "machine": 1, "position": 1, "source_url": "https://example.test/one.jpg",
                "reference_url": "https://example.test/?location=location-1#machine-1-position-1",
                "file": str(crop_one), "orientation": "landscape",
            }
            second = {
                "location_id": "location-1", "slug": "two", "name": "Two",
                "machine": 2, "position": 1, "source_url": "https://example.test/two.jpg",
                "reference_url": "https://example.test/?location=location-1#machine-2-position-1",
                "file": str(crop_two), "orientation": "portrait",
            }
            (staging / "manifest.json").write_text(
                json.dumps({"record-1": first, "record-2": second}), encoding="utf-8"
            )
            (staging / "photo-status.json").write_text(
                json.dumps({
                    photo_status_key(first): {"completed": True},
                    photo_status_key(second): {"completed": False},
                }),
                encoding="utf-8",
            )

            selected, groups = load_entries(staging, "location-1", {"record-1"})

        self.assertEqual(set(selected), {"record-1"})
        self.assertEqual(set(groups), {1})

    def test_api_manifest_filter_keeps_only_requested_ids(self):
        with TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "manifest.json"
            manifest.write_text(
                json.dumps({
                    "record-1": {"location_id": "location-1", "machine": 1, "position": 1},
                    "record-2": {"location_id": "location-1", "machine": 2, "position": 1},
                }),
                encoding="utf-8",
            )

            rows = load_manifest(manifest, "location-1", {"record-1"})

        self.assertEqual([record_id for record_id, _ in rows], ["record-1"])


if __name__ == "__main__":
    unittest.main()
