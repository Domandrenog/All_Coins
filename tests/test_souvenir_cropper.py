import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image, ImageDraw

from tools.souvenir_cropper import (
    PAGE,
    clean_isolated_edge_residue,
    completion_request,
    photo_status_key,
)


class CleanIsolatedEdgeResidueTests(unittest.TestCase):
    def test_removes_border_residue_without_deleting_disconnected_coin_details(self):
        background = (248, 248, 248)
        coin = (122, 70, 40)
        image = Image.new("RGB", (200, 115), background)
        draw = ImageDraw.Draw(image)
        draw.ellipse((40, 20, 160, 94), outline=coin, width=6)
        draw.rectangle((91, 45, 109, 51), fill=coin)
        draw.rectangle((91, 63, 109, 69), fill=coin)
        draw.rectangle((78, 0, 122, 8), fill=coin)

        cleaned, removed, _ = clean_isolated_edge_residue(image)

        self.assertTrue(removed)
        self.assertEqual(cleaned.getpixel((100, 2)), background)
        self.assertEqual(cleaned.getpixel((100, 48)), coin)
        self.assertEqual(cleaned.getpixel((100, 66)), coin)
        self.assertEqual(cleaned.getpixel((40, 57)), coin)


class CompletionRequestTests(unittest.TestCase):
    def records(self):
        return [
            {
                "id": "coin-1",
                "_location_id": "352061",
                "_machine": 1,
                "image_front": "https://example.test/machine-1.jpg",
                "location_name": "Miami",
            },
            {
                "id": "coin-2",
                "_location_id": "352061",
                "_machine": 1,
                "image_front": "https://example.test/machine-1.jpg",
                "location_name": "Miami",
            },
        ]

    def write_state(self, folder: Path, *, completed: bool) -> list[dict[str, object]]:
        records = self.records()
        (folder / "manifest.json").write_text(
            json.dumps({record["id"]: {"file": "unused"} for record in records}),
            encoding="utf-8",
        )
        key = photo_status_key(records[0])
        (folder / "photo-status.json").write_text(
            json.dumps({key: {"completed": completed}}),
            encoding="utf-8",
        )
        return records

    def test_accepts_only_a_fully_confirmed_location(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            records = self.write_state(folder, completed=True)

            request = completion_request(folder, records, "352061")

        self.assertEqual(request["location_name"], "Miami")
        self.assertEqual(request["records"], 2)
        self.assertEqual(request["machines"], 1)

    def test_rejects_a_location_with_an_unconfirmed_photo(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            records = self.write_state(folder, completed=False)

            with self.assertRaisesRegex(ValueError, "máquinas: 1"):
                completion_request(folder, records, "352061")

    def test_page_contains_the_final_send_control(self):
        self.assertIn('id="finalize-location"', PAGE)
        self.assertIn('Finalizar e enviar', PAGE)


if __name__ == "__main__":
    unittest.main()
