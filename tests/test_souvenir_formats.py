import os
import unittest
from unittest.mock import patch

import main

from scripts.sync_coin_images_api import API_KEY_ENV
from tools.souvenir_cropper import load_pending_souvenirs
from tools.souvenir_formats import crop_size
from tools.update_souvenir_manifest_api import preflight


class SouvenirFormatTests(unittest.TestCase):
    def test_pressed_sizes_remain_unchanged(self):
        self.assertEqual(crop_size("pressed", "portrait"), (80, 140))
        self.assertEqual(crop_size("pressed", "landscape"), (200, 115))

    def test_other_uses_rectangular_canvas(self):
        self.assertEqual(crop_size("other", "portrait"), (140, 200))
        self.assertEqual(crop_size("other", "landscape"), (200, 140))

    def test_unsupported_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "não suportado"):
            crop_size("unknown", "portrait")

    def test_main_does_not_hide_other_souvenirs(self):
        self.assertIsNone(main.catalog_type_filter("souvenir"))


class OtherSouvenirQueueTests(unittest.TestCase):
    @patch("tools.souvenir_cropper.load_dotenv")
    @patch("tools.souvenir_cropper.api_request")
    def test_external_other_record_is_included(self, api_request, _load_dotenv):
        api_request.return_value = [
            {
                "id": "other-1",
                "name": "Penny Book",
                "type": "other",
                "country": "EUA",
                "city": "Seattle",
                "image_front": "https://example.test/book.jpg",
                "reference_url": "https://example.test/Details.aspx?location=1117",
                "display_orientation": "portrait",
            },
            {
                "id": "pressed-1",
                "name": "Already migrated",
                "type": "pressed",
                "country": "EUA",
                "city": "Miami",
                "image_front": "https://raw.githubusercontent.com/Domandrenog/All_Coins/main/already.jpg",
                "reference_url": "https://example.test/Details.aspx?location=1",
            },
            {
                "id": "unknown-1",
                "name": "Unknown",
                "type": "unknown",
                "country": "EUA",
                "city": "Nowhere",
                "image_front": "https://example.test/unknown.jpg",
                "reference_url": "https://example.test/Details.aspx?location=2",
            },
        ]
        with patch.dict(os.environ, {API_KEY_ENV: "test-key"}):
            records = load_pending_souvenirs()

        self.assertEqual([record["id"] for record in records], ["other-1"])
        self.assertEqual(records[0]["_orientation"], "portrait")
        self.assertEqual(records[0]["_machine"], 1)
        self.assertEqual(records[0]["_position"], 1)


class OtherSouvenirApiGuardTests(unittest.TestCase):
    @patch("tools.update_souvenir_manifest_api.api_request")
    def test_preflight_accepts_matching_other_type(self, api_request):
        api_request.return_value = {
            "id": "other-1",
            "name": "Penny Book",
            "type": "other",
            "image_front": "https://example.test/book.jpg",
        }
        entry = {
            "type": "other",
            "source_url": "https://example.test/book.jpg",
            "internal_front": "https://raw.githubusercontent.com/example/book.jpg",
            "orientation": "portrait",
        }

        prepared = preflight("key", [("other-1", entry)])

        self.assertEqual(len(prepared), 1)

    @patch("tools.update_souvenir_manifest_api.api_request")
    def test_preflight_rejects_type_drift(self, api_request):
        api_request.return_value = {
            "id": "other-1",
            "type": "pressed",
            "image_front": "https://example.test/book.jpg",
        }
        entry = {
            "type": "other",
            "source_url": "https://example.test/book.jpg",
            "internal_front": "https://raw.githubusercontent.com/example/book.jpg",
            "orientation": "portrait",
        }

        with self.assertRaisesRegex(ValueError, "tipo mudou"):
            preflight("key", [("other-1", entry)])


if __name__ == "__main__":
    unittest.main()
