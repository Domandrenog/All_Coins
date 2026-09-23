import unittest

from PIL import Image, ImageDraw

from tools.souvenir_cropper import clean_isolated_edge_residue


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


if __name__ == "__main__":
    unittest.main()
