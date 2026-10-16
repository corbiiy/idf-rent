import unittest
from pathlib import Path

from scraper.sources import arthurimmo

FIXTURE = Path(__file__).parent / "fixtures" / "arthurimmo_list.html"


class ArthurimmoParserTest(unittest.TestCase):
    def setUp(self):
        self.listings = arthurimmo.parse_list(FIXTURE.read_text(encoding="utf-8"))

    def test_three_cards(self):
        self.assertEqual([l.id for l in self.listings], ["arthurimmo:34027756", "arthurimmo:34000700", "arthurimmo:33986912"])

    def test_fields(self):
        a, b, c = self.listings
        self.assertEqual(a.url, "https://www.arthurimmo.com/annonces/location/appartement/torcy-77200/34027756.htm")
        self.assertEqual((a.rent, a.area, a.rooms, a.postal_code, a.city), (1160, 53.0, 2, "77200", "Torcy"))
        self.assertEqual(a.title, "Appartement | 2 pièces | 53 m² - Torcy")
        self.assertTrue(a.furnished)
        self.assertEqual(a.owner_type, "Agence")
        self.assertIsNone(a.dpe)
        self.assertIsNone(a.posted_at)
        self.assertEqual(len(a.photos), 8)
        self.assertEqual(a.photos[0], "https://media.studio-net.fr/biens/34027756/x6ac60ac593820?width=330&height=250")
        self.assertEqual((b.rent, b.area, b.rooms, b.postal_code, b.city), (1060, 40.0, 3, "77500", "Chelles"))
        self.assertIs(b.furnished, False)  # "non meublé" in the description
        self.assertEqual((c.rent, c.area, c.rooms, c.postal_code, c.city), (600, 10.0, 1, "94000", "Créteil"))
        self.assertIsNone(c.furnished)

    def test_non_idf_and_non_housing_are_dropped(self):
        html = FIXTURE.read_text(encoding="utf-8")
        outside = html.replace("torcy-77200", "abzac-33230").replace("Torcy 77200", "Abzac 33230")
        self.assertEqual([l.id for l in arthurimmo.parse_list(outside)], ["arthurimmo:34000700", "arthurimmo:33986912"])
        parking = html.replace("/location/appartement/chelles-77500/34000700", "/location/parking/chelles-77500/34000700")
        self.assertEqual([l.id for l in arthurimmo.parse_list(parking)], ["arthurimmo:34027756", "arthurimmo:33986912"])

    def test_list_url(self):
        self.assertEqual(arthurimmo.list_url(), "https://www.arthurimmo.com/immobilier/location/immo-ile-de-france/bien-appartement?sort=-created_at")
        self.assertEqual(arthurimmo.list_url("maison", 2), "https://www.arthurimmo.com/immobilier/location/immo-ile-de-france/bien-maison?sort=-created_at&page=2")


if __name__ == "__main__":
    unittest.main()
