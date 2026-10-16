import unittest
from pathlib import Path

from scraper.sources import foncia

FIXTURE = Path(__file__).parent / "fixtures" / "foncia_list.html"


class FonciaParserTest(unittest.TestCase):
    def setUp(self):
        self.listings = foncia.parse_list(FIXTURE.read_text(encoding="utf-8"))

    def test_housing_only(self):
        # the fixture also holds a parking ad (331653739), which must be dropped
        self.assertEqual([l.id for l in self.listings], ["foncia:331699788", "foncia:331723311"])

    def test_fields(self):
        a, b = self.listings
        self.assertEqual(a.url, "https://fr.foncia.com/location/paris-75013/appartement/331699788.htm")
        self.assertEqual(a.title, "Location Studio 28.36 m² - Paris 75013")
        self.assertEqual((a.rent, a.charges, a.area, a.rooms, a.bedrooms, a.dpe), (886, None, 28.36, 1, None, "E"))
        self.assertEqual((a.postal_code, a.city), ("75013", "Paris"))
        self.assertIs(a.furnished, False)
        self.assertEqual(a.owner_type, "Agence")
        self.assertEqual(a.posted_at, "2026-10-16T10:55:21.748Z")
        self.assertEqual(a.photos, [
            "https://d7b3sch6x3cpd.cloudfront.net/annonces/b3/aa/9a/b6/d4/dc/1e/e4/4a/7f/5d/9b/1e/15/97/7c/lg.jpeg",
            "https://d7b3sch6x3cpd.cloudfront.net/annonces/77/57/43/f7/b5/b4/52/71/15/eb/fc/d1/fc/d5/5d/4a/lg.jpeg",
        ])
        self.assertIsNone(a.lat)
        self.assertEqual(b.url, "https://fr.foncia.com/location/paris-75018/appartement-meuble/331723311.htm")
        self.assertEqual((b.rent, b.area, b.rooms, b.dpe, b.postal_code, b.city), (1740, 49.92, 3, "E", "75018", "Paris"))
        self.assertIs(b.furnished, True)

    def test_normalise_extras(self):
        ad = {
            "typeAnnonce": "location", "typeBien": "maison", "reference": "1-2", "canonicalUrl": "/location/x/maison/1-2.htm",
            "status": "active", "localisation": {"codePostal": "92100", "ville": "Boulogne"},
            "loyer": 1996.4, "loyerAnnexe": 154.72, "nbPiece": 4, "nbChambre": 3, "surface": {"habitable": 80.5},
        }
        l = foncia.normalise(ad)
        self.assertEqual((l.rent, l.charges, l.rooms, l.bedrooms, l.area, l.furnished), (1996, 155, 4, 3, 80.5, False))
        self.assertIsNone(foncia.normalise({**ad, "localisation": {"codePostal": "13001"}}))
        self.assertIsNone(foncia.normalise({**ad, "typeBien": "local-commercial"}))
        self.assertIsNone(foncia.normalise({**ad, "status": "archived"}))

    def test_list_url(self):
        self.assertEqual(foncia.list_url("92"), "https://fr.foncia.com/location/hauts-de-seine-92")
        self.assertEqual(foncia.list_url("75", 3), "https://fr.foncia.com/location/paris-75/page-3")
        for dept in foncia.DEPARTMENTS:
            self.assertNotIn("?", foncia.list_url(dept, 2))  # robots.txt disallows every URL with a query string

    def test_empty_page(self):
        self.assertEqual(foncia.parse_list("<html><body>nothing</body></html>"), [])


if __name__ == "__main__":
    unittest.main()
