import unittest
from pathlib import Path

from scraper.sources import era

FIXTURE = Path(__file__).parent / "fixtures" / "era_list.html"


class EraParserTest(unittest.TestCase):
    def setUp(self):
        self.listings = era.parse_list(FIXTURE.read_text(encoding="utf-8"))

    def test_three_cards(self):
        self.assertEqual([l.id for l in self.listings], ["era:587829", "era:587478", "era:587761"])

    def test_fields(self):
        a, b, c = self.listings
        self.assertEqual(a.url, "https://www.eraimmobilier.com/annonces/587829")
        self.assertEqual((a.rent, a.charges, a.area, a.rooms, a.bedrooms, a.dpe), (1400, None, 49.0, 2, 1, "E"))
        self.assertEqual((a.postal_code, a.city), ("92100", "Boulogne-Billancourt"))
        self.assertAlmostEqual(a.lat, 48.828723740486)
        self.assertAlmostEqual(a.lng, 2.2418289247435)
        self.assertIs(a.furnished, False)  # "LOCATION VIDE" in the description
        self.assertEqual(a.owner_type, "Agence")
        self.assertEqual(a.posted_at, "2026-10-15")
        self.assertEqual(len(a.photos), 2)
        self.assertTrue(a.photos[0].startswith("https://api.eraimmobilier.com/medias/annonces/big/"))
        self.assertEqual((b.rent, b.area, b.rooms, b.postal_code, b.city, b.dpe), (980, 32.0, 2, "94000", "Creteil", "D"))
        self.assertIsNone(b.furnished)
        self.assertEqual((c.rent, c.area, c.rooms, c.bedrooms, c.postal_code, c.city), (1098, 25.0, 1, None, "75012", "Paris 12e Arrondissement"))
        self.assertIs(c.furnished, True)
        self.assertEqual(c.title, "Studio meublé VILLA DU BEL AIR 24.84 m2")

    def test_non_housing_and_non_idf_are_skipped(self):
        base = {"id": 1, "type_annonce": "Location", "code_postal": "92100", "prix": 100, "type_bien": "Parking"}
        self.assertIsNone(era.normalise(base))
        self.assertIsNone(era.normalise({**base, "type_bien": "Appartement", "code_postal": "69001"}))
        self.assertIsNone(era.normalise({**base, "type_bien": "Appartement", "type_annonce": "Vente"}))
        self.assertIsNotNone(era.normalise({**base, "type_bien": "Maison"}))

    def test_list_url(self):
        self.assertEqual(era.list_url("92"), "https://www.eraimmobilier.com/location-appartement/ile-de-france-1/hauts-de-seine-97")
        self.assertEqual(era.list_url("75", 3), "https://www.eraimmobilier.com/location-appartement/ile-de-france-1/paris-80?page=3")
        self.assertEqual(era.list_url("95", 1, "maison"), "https://www.eraimmobilier.com/location-maison/ile-de-france-1/val-doise-100")

    def test_empty_page(self):
        self.assertEqual(era.parse_list("<html><body>nothing</body></html>"), [])


if __name__ == "__main__":
    unittest.main()
