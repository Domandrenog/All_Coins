import os
import unittest
from unittest.mock import patch

import main

from scripts.sync_coin_images_api import API_KEY_ENV
from tools.souvenir_cropper import build_souvenir_tasks, load_pending_souvenirs
from tools.souvenir_formats import crop_size
from tools.update_souvenir_manifest_api import difference_payload, preflight


class SouvenirFormatTests(unittest.TestCase):
    def test_pressed_sizes_remain_unchanged(self):
        self.assertEqual(crop_size("pressed", "portrait"), (80, 140))
        self.assertEqual(crop_size("pressed", "landscape"), (200, 115))

    def test_other_uses_rectangular_canvas(self):
        self.assertEqual(crop_size("other", "portrait"), (140, 200))
        self.assertEqual(crop_size("other", "landscape"), (200, 140))

    def test_coin_and_card_formats(self):
        self.assertEqual(crop_size("coin", "auto", "circle"), (140, 140))
        self.assertEqual(crop_size("card", "portrait", "card_wide"), (140, 200))
        self.assertEqual(crop_size("card", "landscape", "card_wide"), (200, 140))

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

        self.assertEqual([record["id"] for record in records], ["other-1:front"])
        self.assertEqual(records[0]["_format"], "portrait")
        self.assertEqual(records[0]["_machine"], 1)
        self.assertEqual(records[0]["_position"], 1)


class MultiSideTaskTests(unittest.TestCase):
    def test_coin_creates_independent_front_and_back_tasks(self):
        tasks = build_souvenir_tasks([{
            "id": "coin-1", "name": "Token", "type": "coin",
            "continent": "América", "country": "EUA", "city": "Boston",
            "location_name": "Museum", "display_shape": "circle",
            "display_orientation": "auto",
            "image_front": "https://example.test/front.jpg",
            "image_back": "https://example.test/back.jpg",
            "reference_url": "https://example.test/item",
        }])

        self.assertEqual({task["id"] for task in tasks}, {"coin-1:front", "coin-1:back"})
        self.assertEqual({task["_format"] for task in tasks}, {"square"})
        self.assertEqual({task["_location_id"] for task in tasks}.__len__(), 1)
        self.assertEqual({task["_machine"] for task in tasks}, {1, 2})

    def test_coin_reuses_front_montage_when_back_is_empty(self):
        tasks = build_souvenir_tasks([{
            "id": "coin-1", "name": "Token", "type": "coin",
            "continent": "Europa", "country": "Portugal", "city": "Albufeira",
            "location_name": "Joias da Praia", "display_shape": "oval",
            "display_orientation": "auto",
            "image_front": "https://example.test/front-and-back.jpg",
            "image_back": "", "reference_url": "https://example.test/item",
        }])

        by_side = {task["_side"]: task for task in tasks}
        self.assertEqual(set(by_side), {"front", "back"})
        self.assertEqual(
            by_side["back"]["_source_url"],
            "https://example.test/front-and-back.jpg",
        )
        self.assertEqual(by_side["back"]["_source_side"], "front")
        self.assertTrue(by_side["back"]["_source_was_empty"])
        self.assertFalse(by_side["front"]["_source_was_empty"])
        self.assertEqual({task["_machine"] for task in tasks}, {1})
        self.assertEqual({task["_position"] for task in tasks}, {1, 2})
        self.assertEqual(
            {task["_photo_label"] for task in tasks},
            {"Fotografia 1 · Frente e Verso"},
        )


class InternalReviewTaskTests(unittest.TestCase):
    def test_internal_side_only_appears_in_all_scope(self):
        record = {
            "id": "other-1", "name": "Album", "type": "other",
            "continent": "América", "country": "EUA", "city": "Boston",
            "image_front": "https://raw.githubusercontent.com/Domandrenog/All_Coins/main/front.jpg",
            "image_back": "", "reference_url": "https://example.test/item",
        }

        pending = build_souvenir_tasks([record])
        all_tasks = build_souvenir_tasks([record], include_internal=True)

        self.assertEqual(pending, [])
        self.assertEqual([task["id"] for task in all_tasks], ["other-1:front"])
        self.assertTrue(all_tasks[0]["_internal"])


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

    def test_back_only_update_preserves_front_and_orientation(self):
        record = {
            "id": "other-1", "type": "other",
            "image_front": "https://example.test/front.jpg",
            "image_back": "https://example.test/back.jpg",
            "display_orientation": "portrait",
        }
        entry = {
            "type": "other",
            "_selected_sides": ["back"],
            "internal_back": "https://raw.githubusercontent.com/example/back.jpg",
            "back_orientation": "landscape",
        }

        payload = difference_payload(record, entry)

        self.assertEqual(payload, {
            "image_back": "https://raw.githubusercontent.com/example/back.jpg"
        })

    @patch("tools.update_souvenir_manifest_api.api_request")
    def test_preflight_accepts_empty_synthesized_coin_back(self, api_request):
        api_request.return_value = {
            "id": "coin-1", "type": "coin",
            "image_front": "https://example.test/front-and-back.jpg",
            "image_back": "",
        }
        entry = {
            "type": "coin", "_selected_sides": ["back"],
            "external_back": "https://example.test/front-and-back.jpg",
            "previous_back": "https://example.test/front-and-back.jpg",
            "internal_back": "https://raw.githubusercontent.com/example/back.jpg",
            "back_source_was_empty": True,
        }

        prepared = preflight("key", [("coin-1", entry)])

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
