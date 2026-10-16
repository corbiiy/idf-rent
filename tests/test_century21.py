import unittest
from pathlib import Path

from scraper.sources import century21

FIXTURE = Path(__file__).parent / "fixtures" / "century21_list.html"


class Century21ParserTest(unittest.TestCase):
    def setUp(self):
        self.listings = century21.parse_list(FIXTURE.read_text(encoding="utf-8"))

    def test_three_cards(self):
        self.assertEqual([l.id for l in self.listings],
                         ["century21:17052896788", "century21:17045561515", "century21:17011965495"])

    def test_fields(self):
        a, b, c = self.listings
        self.assertEqual(a.url, "https://www.century21.fr/trouver_logement/detail/17052896788/")
        self.assertEqual((a.rent, a.area, a.rooms), (1300, 51.06, 3))
        self.assertEqual((a.postal_code, a.city), (None, "Boulogne Billancourt"))  # the 92 list only shows the department
        self.assertEqual(a.title, "Appartement T3 - Boulogne Billancourt")
        self.assertEqual(a.owner_type, "Agence")
        self.assertIsNone(a.dpe)
        self.assertIsNone(a.furnished)
        self.assertEqual(a.photos, ["https://www.century21.fr/imagesBien/s3/202/2421/c21_202_2421_14267_8_10FC7EC7-ED37-4332-8265-7ED60C6530B4.jpg"])
        self.assertEqual((b.rent, b.area, b.rooms, b.city), (695, 17.75, 1, "Gennevilliers"))  # "695,07 €" rounds to 695
        self.assertTrue(b.furnished)  # "meublé" in the description
        self.assertEqual(len(b.photos), 1)  # lazy-loaded data-src
        self.assertEqual((c.rent, c.area, c.rooms, c.postal_code, c.city), (1278, 34.34, 2, "75012", "Paris"))
        self.assertEqual(c.url, "https://www.century21.fr/trouver_logement/detail/17011965495/")

    def test_list_url(self):
        self.assertEqual(century21.list_url("92"), "https://www.century21.fr/annonces/location-appartement/d-92_hauts_de_seine/")
        self.assertEqual(century21.list_url("92", "maison", 2), "https://www.century21.fr/annonces/location-maison/d-92_hauts_de_seine/page-2/")
        self.assertEqual(century21.list_url("75"), "https://www.century21.fr/annonces/location-appartement/v-paris/")
        self.assertEqual(century21.list_url("95", page=3), "https://www.century21.fr/annonces/location-appartement/d-95_val_d_oise/page-3/")


class DetailPostalCodeTest(unittest.TestCase):
    def test_breadcrumb(self):
        from scraper.sources.century21 import detail_postal_code
        html = '''<a href="/annonces/location-appartement/cp-92100/"><span itemprop="name">Location Appartement BOULOGNE BILLANCOURT (92100)</span></a>'''
        self.assertEqual(detail_postal_code(html), "92100")
        self.assertIsNone(detail_postal_code("<span itemprop=\"name\">Accueil</span>"))


if __name__ == "__main__":
    unittest.main()
