import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import main

from scripts.sync_coin_images_api import API_KEY_ENV
from tools.souvenir_cropper import (
    PAGE,
    apply_back_image_overrides,
    apply_type_overrides,
    build_souvenir_tasks,
    clone_souvenir_payload,
    create_souvenir_clone,
    load_pending_souvenirs,
    manifest_entry_for_task,
    read_back_image_overrides,
    read_type_overrides,
    side_display_name,
    update_manifest_back_image_override,
    write_back_image_override,
    write_type_override,
)
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

    def test_coin_can_explicitly_skip_the_back_task(self):
        records = apply_back_image_overrides(
            [{
                "id": "coin-1", "name": "Token", "type": "coin",
                "continent": "Europa", "country": "Portugal", "city": "Coimbra",
                "location_name": "Coimbra", "display_shape": "circle",
                "image_front": "https://example.test/front-and-back.jpg",
                "image_back": "", "reference_url": "https://example.test/item",
            }],
            {"coin-1": False},
        )

        tasks = build_souvenir_tasks(records)

        self.assertEqual([task["id"] for task in tasks], ["coin-1:front"])
        self.assertIs(tasks[0]["_has_back_image_override"], False)
        self.assertEqual(tasks[0]["_photo_label"], "Fotografia 1 · Frente")


class SouvenirCloneTests(unittest.TestCase):
    def source(self):
        return {
            "id": "coin-1:front",
            "_record_id": "coin-1",
            "_has_back_image_override": None,
            "name": "Fátima Sanctuary",
            "continent": "Europa",
            "country": "Portugal",
            "city": "Fátima",
            "type": "coin",
            "condition": "Não Tenho",
            "location_name": "Loja Virginia",
            "description": "Descrição original",
            "display_shape": "circle",
            "display_orientation": "auto",
            "has_back_image": True,
            "image_front": "https://example.test/montage.jpg",
            "image_back": "",
            "reference_url": "https://example.test/location=1",
            "ordem": 4,
            "hidden": False,
            "created_date": "2026-01-01",
        }

    def test_clone_changes_only_the_name_and_ignores_derived_fields(self):
        payload = clone_souvenir_payload(
            self.source(), "Fátima Sanctuary — Silver"
        )

        self.assertEqual(payload["name"], "Fátima Sanctuary — Silver")
        self.assertEqual(payload["location_name"], "Loja Virginia")
        self.assertEqual(payload["image_front"], "https://example.test/montage.jpg")
        self.assertEqual(payload["has_back_image"], True)
        self.assertNotIn("id", payload)
        self.assertNotIn("_record_id", payload)
        self.assertNotIn("created_date", payload)

    def test_clone_requires_a_different_name(self):
        with self.assertRaisesRegex(ValueError, "diferente"):
            clone_souvenir_payload(self.source(), "fátima sanctuary")

    @patch("tools.souvenir_cropper.api_request")
    def test_creation_is_verified_in_base44(self, api_request):
        source = self.source()
        payload = clone_souvenir_payload(source, "Fátima Sanctuary — Silver")
        api_request.side_effect = [
            {"id": "new-coin"},
            {"id": "new-coin", **payload},
        ]

        created = create_souvenir_clone(
            source, "Fátima Sanctuary — Silver", "test-key"
        )

        self.assertEqual(created["id"], "new-coin")
        self.assertEqual(created["name"], "Fátima Sanctuary — Silver")
        self.assertEqual(api_request.call_count, 2)
        self.assertEqual(api_request.call_args_list[0].args[:3], (
            "POST", "/entities/Souvenir", "test-key",
        ))
        self.assertEqual(
            api_request.call_args_list[0].kwargs["payload"],
            payload,
        )
        self.assertEqual(api_request.call_args_list[1].args[:3], (
            "GET", "/entities/Souvenir/new-coin", "test-key",
        ))


class BackImageOverrideTests(unittest.TestCase):
    def test_no_back_choice_is_persistent_until_reenabled(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_back_image_override(folder, "coin-1", False)
            self.assertEqual(read_back_image_overrides(folder), {"coin-1": False})

            write_back_image_override(folder, "coin-1", True)
            self.assertEqual(read_back_image_overrides(folder), {})

    def test_existing_front_crop_receives_no_back_metadata_and_new_position(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "manifest.json").write_text(
                '{"coin-1:front":{"record_id":"coin-1","machine":2,"position":2}}',
                encoding="utf-8",
            )
            update_manifest_back_image_override(
                folder,
                "coin-1",
                False,
                [{
                    "id": "coin-1:front", "_machine": 1, "_position": 1,
                    "_source_url": "https://example.test/source.jpg",
                    "_source_side": "front", "_source_was_empty": False,
                }],
            )
            manifest = json.loads(
                (folder / "manifest.json").read_text(encoding="utf-8")
            )

        entry = manifest["coin-1:front"]
        self.assertIs(entry["has_back_image_override"], False)
        self.assertTrue(entry["has_back_image_was_overridden"])
        self.assertEqual(entry["machine"], 1)
        self.assertEqual(entry["position"], 1)


class SideDisplayNameTests(unittest.TestCase):
    def test_uses_front_and_reverse_parts_from_shared_description(self):
        base = {
            "name": "Front: (Gold colored) Entry building…",
            "description": (
                "Front: (Gold colored) Entry building to children's theme park "
                "/ Reverse for both tokens: Eight stars surrounding Portugal"
            ),
        }

        front = side_display_name({**base, "_side": "front"})
        back = side_display_name({**base, "_side": "back"})

        self.assertEqual(
            front,
            "Frente — (Gold colored) Entry building to children's theme park",
        )
        self.assertEqual(
            back,
            "Verso — Eight stars surrounding Portugal",
        )

    def test_back_fallback_replaces_misleading_front_prefix(self):
        result = side_display_name({
            "_side": "back",
            "name": "Front: Coimbra token",
            "description": "",
        })

        self.assertEqual(result, "Verso — Coimbra token")


class TypeOverrideTaskTests(unittest.TestCase):
    def test_pressed_record_becomes_coin_with_front_and_back_tasks(self):
        original = {
            "id": "coin-1", "name": "Cathedral", "type": "pressed",
            "continent": "Europa", "country": "Portugal", "city": "Porto",
            "location_name": "Porto Cathedral", "display_shape": "oval",
            "image_front": "https://example.test/front-and-back.jpg",
            "image_back": "",
            "reference_url": "https://example.test/item#machine-1-position-1",
        }

        records = apply_type_overrides([original], {"coin-1": "coin"})
        tasks = build_souvenir_tasks(records)

        self.assertEqual({task["id"] for task in tasks}, {
            "coin-1:front", "coin-1:back",
        })
        self.assertEqual({task["type"] for task in tasks}, {"coin"})
        self.assertEqual({task["_format"] for task in tasks}, {"square"})
        self.assertEqual({task["_original_type"] for task in tasks}, {"pressed"})
        self.assertEqual({task["_type_was_overridden"] for task in tasks}, {True})
        self.assertEqual({task["_photo_label"] for task in tasks}, {
            "Fotografia 1 · Frente e Verso",
        })

    def test_type_override_is_persistent_until_reverted(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_type_override(folder, "coin-1", "coin", "pressed")
            self.assertEqual(read_type_overrides(folder), {"coin-1": "coin"})

            write_type_override(folder, "coin-1", "pressed", "pressed")
            self.assertEqual(read_type_overrides(folder), {})

    def test_crop_prepared_for_old_type_is_not_reused(self):
        manifest = {
            "coin-1:front": {"type": "pressed", "file": "old.jpg"},
        }
        coin_task = {
            "id": "coin-1:front", "_record_id": "coin-1",
            "_side": "front", "type": "coin",
        }

        self.assertIsNone(manifest_entry_for_task(manifest, coin_task))

    def test_page_exposes_record_type_selector(self):
        self.assertIn('id="record-type"', PAGE)
        self.assertIn("/api/record-type", PAGE)
        self.assertIn('id="coin-sides"', PAGE)
        self.assertIn("Frente e Verso", PAGE)
        self.assertIn("Só Frente", PAGE)
        self.assertIn('id="duplicate-record"', PAGE)
        self.assertIn("Adicionar moeda em falta", PAGE)
        self.assertIn("/api/duplicate-record", PAGE)
        self.assertIn("/api/record-back-image", PAGE)
        self.assertIn("Recorta agora a Frente e o Verso", PAGE)


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
            "image_back": "https://raw.githubusercontent.com/example/back.jpg",
            "has_back_image": True,
        })

    def test_front_only_coin_disables_back_without_deleting_its_url(self):
        old_back = "https://example.test/old-back.jpg"
        front = "https://raw.githubusercontent.com/example/front.jpg"
        record = {
            "id": "coin-1", "type": "coin",
            "image_front": front, "image_back": old_back,
            "has_back_image": True, "display_orientation": "auto",
        }
        entry = {
            "type": "coin", "_selected_sides": ["front"],
            "internal_front": front, "orientation": "auto",
            "has_back_image_override": False,
            "has_back_image_was_overridden": True,
        }

        payload = difference_payload(record, entry)

        self.assertEqual(payload, {"has_back_image": False})
        self.assertEqual(record["image_back"], old_back)

    def test_existing_back_url_enables_back_image_flag(self):
        target = "https://raw.githubusercontent.com/example/back.jpg"
        record = {
            "id": "coin-1", "type": "coin",
            "image_back": target, "has_back_image": False,
        }
        entry = {
            "type": "coin", "_selected_sides": ["back"],
            "internal_back": target,
        }

        payload = difference_payload(record, entry)

        self.assertEqual(payload, {"has_back_image": True})

    def test_type_override_updates_type_and_back_fields_together(self):
        target = "https://raw.githubusercontent.com/example/back.jpg"
        record = {
            "id": "coin-1", "type": "pressed",
            "image_back": "", "has_back_image": False,
        }
        entry = {
            "type": "coin", "previous_type": "pressed",
            "type_was_overridden": True, "_selected_sides": ["back"],
            "internal_back": target, "back_source_was_empty": True,
        }

        payload = difference_payload(record, entry)

        self.assertEqual(payload, {
            "type": "coin",
            "image_back": target,
            "has_back_image": True,
        })

    @patch("tools.update_souvenir_manifest_api.api_request")
    def test_preflight_accepts_explicit_type_override(self, api_request):
        api_request.return_value = {
            "id": "coin-1", "type": "pressed", "image_back": "",
        }
        entry = {
            "type": "coin", "previous_type": "pressed",
            "type_was_overridden": True, "_selected_sides": ["back"],
            "internal_back": "https://raw.githubusercontent.com/example/back.jpg",
            "back_source_was_empty": True,
        }

        prepared = preflight("key", [("coin-1", entry)])

        self.assertEqual(len(prepared), 1)

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
