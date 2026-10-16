import unittest
from pathlib import Path

from scraper.sources import ladresse

FIXTURE = Path(__file__).parent / "fixtures" / "ladresse_list.html"


class LadresseParserTest(unittest.TestCase):
    def setUp(self):
        self.listings = ladresse.parse_list(FIXTURE.read_text(encoding="utf-8"))

    def test_three_cards(self):
        self.assertEqual([l.id for l in self.listings], ["ladresse:14658060", "ladresse:14657983", "ladresse:14657364"])

    def test_fields(self):
        a, b, c = self.listings
        self.assertEqual(a.url, "https://www.ladresse.com/annonce/location/appartement/chelles-77500/14658060")
        self.assertEqual((a.rent, a.charges, a.area, a.rooms, a.bedrooms), (1313, None, 60.0, 3, 2))
        self.assertEqual((a.postal_code, a.city), ("77500", "Chelles"))
        self.assertEqual((a.lat, a.lng), (48.876363815581, 2.5888262874132))
        self.assertEqual(a.title, "Appartement 3 pièces 60 m² - Chelles")
        self.assertEqual(a.photos, ["https://admin.exceladresse.com/office7/ladresseAc3-509/catalog/images/pr_p/1/4/6/5/8/0/6/0/14658060a.jpg?version=1792143838"])
        self.assertIsNone(a.furnished)
        self.assertEqual(a.owner_type, "Agence")
        self.assertIsNone(a.dpe)
        self.assertIsNone(a.posted_at)
        # furnished studio
        self.assertEqual((b.rent, b.area, b.rooms, b.bedrooms, b.postal_code, b.city), (550, 10.0, 1, 1, "91940", "Les Ulis"))
        self.assertTrue(b.furnished)
        self.assertEqual((b.lat, b.lng), (48.689266212756, 2.1728643358754))
        # Paris 7e, "exclu" card
        self.assertEqual(c.url, "https://www.ladresse.com/annonce/location/appartement/paris-75007/14657364")
        self.assertEqual((c.rent, c.area, c.rooms, c.bedrooms, c.postal_code, c.city), (2100, 52.0, 3, 2, "75007", "Paris"))
        self.assertEqual((c.lat, c.lng), (48.8513, 2.31045))

    def test_list_url(self):
        self.assertEqual(ladresse.list_url("92"), "https://www.ladresse.com/recherche/location/appartement/hauts-de-seine-92?tri=date-desc")
        self.assertEqual(ladresse.list_url("75", "maison", 3), "https://www.ladresse.com/recherche/location/maison/paris-75/3?tri=date-desc")

    def test_empty_page(self):
        self.assertEqual(ladresse.parse_list("<html><body><div class='biens'><ul></ul></div></body></html>"), [])


if __name__ == "__main__":
    unittest.main()
