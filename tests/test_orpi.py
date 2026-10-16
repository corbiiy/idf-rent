import unittest
from pathlib import Path

from scraper.sources import orpi

FIXTURE = Path(__file__).parent / "fixtures" / "orpi_list.html"


class OrpiTest(unittest.TestCase):
    def setUp(self):
        self.listings = orpi.parse_list(FIXTURE.read_text(encoding="utf-8"))

    def test_housing_only(self):
        self.assertEqual(len(self.listings), 2)  # the parking item is dropped
        self.assertTrue(all(l.source == "orpi" and l.owner_type == "Agence" for l in self.listings))

    def test_fields(self):
        a = self.listings[0]
        self.assertTrue(a.id.startswith("orpi:"))
        self.assertTrue(a.url.startswith("https://www.orpi.com/annonce-location-appartement-"))
        self.assertEqual(len(a.postal_code), 5)
        self.assertEqual(a.postal_code[:2], "92")
        self.assertIsNotNone(a.rent); self.assertIsNotNone(a.area); self.assertIsNotNone(a.rooms)
        self.assertIsNotNone(a.lat); self.assertIsNotNone(a.lng)
        self.assertTrue(a.posted_at.startswith("20"))
        self.assertTrue(a.photos[0].startswith("https://"))

    def test_tags(self):
        item = {"transaction": "rent", "type": "appartement", "reference": "r", "slug": "appartement-t2-vanves-92170-a7eb0621-bef9-4e2f-ada3-99f3a36dc0c2",
                "price": 1300, "surface": 42.74, "nbRooms": 2, "city": {"name": "Vanves"}, "tags": ["1 chambre", "Non meublé"], "images": []}
        l = orpi.normalise(item)
        self.assertEqual((l.bedrooms, l.furnished, l.postal_code, l.city), (1, False, "92170", "Vanves"))
        item["tags"] = ["Meublé", "Studio"]; item["nbRooms"] = None
        l = orpi.normalise(item)
        self.assertEqual((l.furnished, l.rooms), (True, 1))

    def test_list_url_has_no_disallowed_params(self):
        u = orpi.list_url("92")
        self.assertIn("locations[0][value]=hauts-de-seine", u)
        for bad in ("agency=", "sujet=", "contact="):
            self.assertNotIn(bad, u)


if __name__ == "__main__":
    unittest.main()
