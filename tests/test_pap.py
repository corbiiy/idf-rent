import unittest
from pathlib import Path

from scraper.sources import pap

FIXTURE = Path(__file__).parent / "fixtures" / "pap_list.html"


class PapParserTest(unittest.TestCase):
    def setUp(self):
        self.listings = pap.parse_list(FIXTURE.read_text(encoding="utf-8"))

    def test_three_cards(self):
        self.assertEqual([l.id for l in self.listings], ["pap:449900348", "pap:437702459", "pap:420001263"])

    def test_fields(self):
        a, b, c = self.listings
        self.assertEqual((a.rent, a.rooms, a.bedrooms, a.area, a.dpe), (750, 1, None, 14, "C"))
        self.assertEqual(a.url, "https://www.pap.fr/annonces/appartement-paris-1er-r449900348")
        self.assertEqual(a.photos, [])  # placeholder image is not a photo
        self.assertTrue(a.furnished)
        self.assertEqual(a.owner_type, "Particulier")
        self.assertEqual((b.rent, b.postal_code, b.city, b.dpe), (1209, "75015", "Paris 15E", "F"))
        self.assertEqual(len(b.photos), 2)
        self.assertEqual((c.rent, c.rooms, c.bedrooms, c.area, c.postal_code), (2200, 4, 2, 64, None))
        self.assertIsNone(c.furnished)

    def test_list_url(self):
        self.assertEqual(pap.list_url("92"), "https://www.pap.fr/annonce/location-appartement-maison-hauts-de-seine-92-g456")
        self.assertEqual(pap.list_url("75", 3), "https://www.pap.fr/annonce/location-appartement-maison-paris-75-g439-3")


if __name__ == "__main__":
    unittest.main()
