import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image, ImageDraw

from tools.souvenir_cropper import (
    PAGE,
    clean_isolated_edge_residue,
    completion_queue,
    completion_request,
    location_progress_rows,
    order_quad_points,
    perspective_crop,
    photo_status_for_task,
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


class PerspectiveCropTests(unittest.TestCase):
    def test_orders_vertices_independently_of_click_order(self):
        ordered = order_quad_points([
            (90.0, 90.0), (10.0, 10.0), (10.0, 90.0), (90.0, 10.0),
        ])

        self.assertEqual(ordered, (
            (10.0, 10.0), (90.0, 10.0), (90.0, 90.0), (10.0, 90.0),
        ))

    def test_straightens_quad_to_requested_output_size(self):
        image = Image.new("RGB", (120, 100), "white")
        draw = ImageDraw.Draw(image)
        draw.polygon([(20, 10), (100, 20), (90, 90), (10, 80)], fill=(184, 115, 51))

        cropped = perspective_crop(
            image,
            [(90, 90), (20, 10), (10, 80), (100, 20)],
            (80, 140),
        )

        self.assertEqual(cropped.size, (80, 140))
        self.assertNotEqual(cropped.getpixel((40, 70)), (255, 255, 255))

    def test_rejects_repeated_vertices(self):
        with self.assertRaisesRegex(ValueError, "diferentes"):
            order_quad_points([(10, 10), (10, 10), (90, 90), (10, 90)])


class LocationProgressTests(unittest.TestCase):
    def test_counts_pending_and_total_sides_for_each_location(self):
        rows = location_progress_rows([
            {
                "_location_id": "one", "_record_id": "a", "_machine": 1,
                "_internal": False, "continent": "Europa", "country": "Portugal",
                "city": "Albufeira", "location_name": "Joias da Praia",
            },
            {
                "_location_id": "one", "_record_id": "b", "_machine": 2,
                "_internal": True, "continent": "Europa", "country": "Portugal",
                "city": "Albufeira", "location_name": "Joias da Praia",
            },
            {
                "_location_id": "two", "_record_id": "c", "_machine": 1,
                "_internal": True, "continent": "Europa", "country": "Espanha",
                "city": "Madrid", "location_name": "Museu",
            },
        ])

        by_id = {row["id"]: row for row in rows}
        self.assertEqual(by_id["one"]["pending_sides"], 1)
        self.assertEqual(by_id["one"]["total_sides"], 2)
        self.assertEqual(by_id["one"]["pending_souvenirs"], 1)
        self.assertEqual(by_id["one"]["total_souvenirs"], 2)
        self.assertEqual(by_id["two"]["pending_sides"], 0)
        self.assertEqual(by_id["two"]["total_sides"], 1)


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

    def test_global_queue_includes_every_newly_completed_location(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            records = [
                {
                    "id": "pending-1", "_record_id": "pending-1",
                    "_location_id": "location-a", "_machine": 1,
                    "_source_url": "https://example.test/a.jpg", "_side": "front",
                    "_internal": False, "location_name": "A",
                },
                {
                    "id": "pending-old", "_record_id": "pending-old",
                    "_location_id": "location-a", "_machine": 1,
                    "_source_url": "https://example.test/a.jpg", "_side": "front",
                    "_internal": True, "location_name": "A",
                },
                {
                    "id": "internal-1", "_record_id": "internal-1",
                    "_location_id": "location-b", "_machine": 1,
                    "_source_url": "https://example.test/b.jpg", "_side": "front",
                    "_internal": True, "location_name": "B",
                },
                {
                    "id": "old-1", "_record_id": "old-1",
                    "_location_id": "location-c", "_machine": 1,
                    "_source_url": "https://example.test/c.jpg", "_side": "front",
                    "_internal": True, "location_name": "C",
                },
            ]
            (folder / "manifest.json").write_text(
                json.dumps({record["id"]: {"file": "unused"} for record in records}),
                encoding="utf-8",
            )
            (folder / "photo-status.json").write_text(
                json.dumps({
                    photo_status_key(records[0]): {"completed": True},
                    photo_status_key(records[2]): {"completed": True, "queued": True},
                    photo_status_key(records[3]): {"completed": True},
                }),
                encoding="utf-8",
            )

            requests = completion_queue(folder, records)

        self.assertEqual(
            [request["location_id"] for request in requests],
            ["location-a", "location-b"],
        )
        self.assertEqual(sum(request["photos"] for request in requests), 2)
        self.assertEqual(sum(request["sides"] for request in requests), 2)
        self.assertEqual(requests[0]["record_sides"], ["pending-1:front"])

    def test_shared_source_front_completion_does_not_complete_back(self):
        source = "https://example.test/front-and-back.jpg"
        statuses = {
            "old-front-status": {
                "completed": True,
                "source_url": source,
                "side": "front",
            }
        }
        back_task = {
            "_location_id": "406415",
            "_machine": 2,
            "_side": "back",
            "_source_url": source,
        }

        self.assertIsNone(photo_status_for_task(statuses, back_task))

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
        self.assertIn("faltam ${pending}/${all} lados", PAGE)
        self.assertIn('id="selection-mode"', PAGE)
        self.assertIn("Marcar 4 vértices", PAGE)
        self.assertIn("Correção de perspetiva ativa", PAGE)
        self.assertIn("/api/completion-summary", PAGE)
        self.assertIn("Todas as fotografias que marcaste como completas serão enviadas", PAGE)


if __name__ == "__main__":
    unittest.main()
