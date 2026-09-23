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
                "_machine": 2,
                "image_front": "https://example.test/machine-2.jpg",
                "location_name": "Miami",
            },
        ]

    def write_state(
        self, folder: Path, *, completed_machines: set[int]
    ) -> list[dict[str, object]]:
        records = self.records()
        (folder / "manifest.json").write_text(
            json.dumps({
                record["id"]: {"file": "unused"}
                for record in records
                if record["_machine"] in completed_machines
            }),
            encoding="utf-8",
        )
        statuses = {
            photo_status_key(record): {"completed": record["_machine"] in completed_machines}
            for record in records
        }
        (folder / "photo-status.json").write_text(
            json.dumps(statuses),
            encoding="utf-8",
        )
        return records

    def test_selects_only_records_from_completed_photos(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            records = self.write_state(folder, completed_machines={1})

            request = completion_request(folder, records, "352061")

        self.assertEqual(request["location_name"], "Miami")
        self.assertEqual(request["records"], 1)
        self.assertEqual(request["photos"], 1)
        self.assertEqual(request["record_ids"], ["coin-1"])
        self.assertEqual(request["record_sides"], ["coin-1:front"])

    def test_rejects_when_no_photo_is_completed(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            records = self.write_state(folder, completed_machines=set())

            with self.assertRaisesRegex(ValueError, "pelo menos uma fotografia"):
                completion_request(folder, records, "352061")

    def test_page_contains_the_final_send_control(self):
        self.assertIn('id="finalize-location"', PAGE)
        self.assertIn('Finalizar e enviar concluídas', PAGE)
        self.assertIn('Não existem lados externos pendentes', PAGE)
        self.assertIn("currentRecord.type === 'coin'", PAGE)
        self.assertIn('id="scope"', PAGE)
        self.assertIn('Todos com imagem', PAGE)
        self.assertIn('id="continent"', PAGE)
        self.assertIn('id="country"', PAGE)
        self.assertIn('id="city"', PAGE)
        self.assertIn("Em pé — 140 × 200 px", PAGE)


if __name__ == "__main__":
    unittest.main()
