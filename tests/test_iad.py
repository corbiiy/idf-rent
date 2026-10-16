import unittest
from pathlib import Path

from scraper.sources import iad

FIXTURE = Path(__file__).parent / "fixtures" / "iad_list.html"


class IadParserTest(unittest.TestCase):
    def setUp(self):
        self.listings = iad.parse_list(FIXTURE.read_text(encoding="utf-8"))

    def test_parking_skipped(self):
        # the fixture holds an apartment, a parking and a house: the parking must not be yielded
        self.assertEqual([l.id for l in self.listings], ["iad:2138626", "iad:2128779"])

    def test_fields(self):
        a, b = self.listings
        self.assertEqual(a.url, "https://www.iadfrance.fr/annonce/appartement-location-4-pieces-colombes-82m2/r2138626")
        self.assertEqual((a.rent, a.charges, a.area, a.rooms, a.bedrooms), (2400, None, 82.0, 4, 3))
        self.assertEqual((a.postal_code, a.city), ("92700", "Colombes"))
        self.assertEqual(a.title, "Appartement 4 pièces 82 m² - Colombes")
        self.assertEqual(a.owner_type, "Agence")
        self.assertIsNone(a.furnished)
        self.assertIsNone(a.dpe)
        self.assertIsNone(a.lat)
        self.assertEqual(len(a.photos), 1)
        self.assertTrue(a.photos[0].startswith("https://images.iadfrance.fr/property/"))
        self.assertNotIn("&amp;", a.photos[0])
        self.assertEqual(b.url, "https://www.iadfrance.fr/annonce/maison-location-5-pieces-nanterre-92m2/r2128779")
        self.assertEqual((b.rent, b.area, b.rooms, b.bedrooms, b.postal_code, b.city), (2600, 92.0, 5, 4, "92000", "Nanterre"))
        self.assertEqual(b.title, "Maison 5 pièces 92 m² - Nanterre")

    def test_list_url(self):
        self.assertEqual(iad.list_url("75"), "https://www.iadfrance.fr/annonces/paris-75/location")
        self.assertEqual(iad.list_url("92", 2), "https://www.iadfrance.fr/annonces/hauts-de-seine-92/location?page=2")

    def test_empty_page(self):
        self.assertEqual(iad.parse_list("<html><body><h1>72 biens</h1></body></html>"), [])


if __name__ == "__main__":
    unittest.main()
