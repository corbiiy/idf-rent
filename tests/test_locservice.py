import unittest
from pathlib import Path

from scraper.sources import locservice

FIXTURE = Path(__file__).parent / "fixtures" / "locservice_list.html"


class LocServiceParserTest(unittest.TestCase):
    def setUp(self):
        self.listings = locservice.parse_list(FIXTURE.read_text(encoding="utf-8"))

    def test_housing_only(self):
        # the fixture has 4 cards; the "Chambre à louer" one is skipped
        self.assertEqual([l.id for l in self.listings], ["locservice:2597821", "locservice:2596505", "locservice:2580848"])

    def test_fields(self):
        a, b, c = self.listings
        self.assertEqual(a.url, "https://www.locservice.fr/paris-75/location-appartement-paris-15/2597821")
        self.assertEqual((a.rent, a.area, a.rooms, a.bedrooms), (2400, 59.0, 3, 2))
        self.assertEqual((a.postal_code, a.city), ("75015", "Paris 15"))
        self.assertTrue(a.furnished)
        self.assertEqual(a.owner_type, "Particulier")
        self.assertEqual(a.title, "Appartement T3 meublé - Paris 15")
        self.assertEqual(len(a.photos), 1)
        self.assertTrue(a.photos[0].startswith("https://img.locservice.fr/"))
        self.assertIsNone(a.dpe)
        self.assertIsNone(a.posted_at)

        self.assertEqual((b.rent, b.area, b.rooms, b.bedrooms, b.postal_code, b.city), (1790, 21.0, 1, None, "75001", "Paris 01"))
        self.assertTrue(b.furnished)

        self.assertEqual(c.url, "https://www.locservice.fr/hauts-de-seine-92/location-appartement-chaville/2580848")
        self.assertEqual((c.rent, c.area, c.rooms, c.postal_code, c.city), (1690, 65.0, 3, "92370", "Chaville"))
        self.assertFalse(c.furnished)

    def test_list_url(self):
        self.assertEqual(locservice.list_url("75"), "https://www.locservice.fr/paris-75/location.html")
        self.assertEqual(locservice.list_url("75", 2), "https://www.locservice.fr/paris-75/location-p2.html")
        self.assertEqual(locservice.list_url("92"), "https://www.locservice.fr/hauts-de-seine-92/location-hauts-de-seine.html")
        self.assertEqual(locservice.list_url("95", 3), "https://www.locservice.fr/val-d-oise-95/location-val-d-oise-p3.html")
        self.assertEqual(set(locservice.DEPARTMENTS), {"75", "77", "78", "91", "92", "93", "94", "95"})


if __name__ == "__main__":
    unittest.main()
