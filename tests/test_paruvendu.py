import unittest
from pathlib import Path

from scraper.sources import paruvendu

FIXTURE = Path(__file__).parent / "fixtures" / "paruvendu_list.html"


class ParuvenduParserTest(unittest.TestCase):
    def setUp(self):
        self.listings = paruvendu.parse_list(FIXTURE.read_text(encoding="utf-8"))

    def test_housing_only(self):
        # the fixture has 4 cards; the "chambre" one is skipped
        self.assertEqual([l.id for l in self.listings],
                         ["paruvendu:1296308021A1KILHAP000", "paruvendu:1296169375A1KILHAP000", "paruvendu:1296332166A1KILHAP000"])

    def test_fields(self):
        a, b, c = self.listings
        self.assertEqual(a.url, "https://www.paruvendu.fr/immobilier/location/appartement/1296308021A1KILHAP000")
        self.assertEqual((a.rent, a.area, a.rooms, a.bedrooms, a.dpe), (950, 35.0, 1, 1, "B"))
        self.assertEqual((a.postal_code, a.city), ("75010", "Paris 10"))
        self.assertTrue(a.furnished)
        self.assertEqual(a.owner_type, "Particulier")
        self.assertEqual(a.posted_at, "2026-10-15")
        self.assertEqual(a.title, "Appartement 1 pièce 35 m² - Paris 10")
        self.assertEqual(len(a.photos), 2)  # first photo comes from the card's inline script, the second from <img src>
        self.assertTrue(all(p.startswith("https://img.paruvendu.fr/media_ext/") for p in a.photos))

        # outside Paris the card only gives the department, not the postal code
        self.assertEqual((b.rent, b.area, b.rooms, b.bedrooms, b.dpe), (1750, 41.0, 2, 1, "D"))
        self.assertEqual((b.postal_code, b.city), (None, "Boulogne-Billancourt"))
        self.assertIsNone(b.furnished)
        self.assertEqual(b.owner_type, "Particulier")

        self.assertEqual((c.rent, c.area, c.rooms, c.dpe, c.city), (675, 42.0, 2, "C", "Corbeil-Essonnes"))
        self.assertEqual(c.owner_type, "Agence")
        self.assertEqual(c.posted_at, "2026-10-16")

    def test_place(self):
        self.assertEqual(paruvendu._place("Paris 10"), ("Paris 10", "75010", "75"))
        self.assertEqual(paruvendu._place("Paris 1"), ("Paris 1", "75001", "75"))
        self.assertEqual(paruvendu._place("Nanterre (92)"), ("Nanterre", None, "92"))
        self.assertEqual(paruvendu._place("Lyon (69)"), ("Lyon", None, "69"))

    def test_list_url(self):
        self.assertEqual(paruvendu.list_url("92"), "https://www.paruvendu.fr/immobilier/recherche/location/appartement/hauts-de-seine-92/")
        self.assertEqual(paruvendu.list_url("75", "maison", 3), "https://www.paruvendu.fr/immobilier/recherche/location/maison/paris-75/?p=3")
        self.assertEqual(set(paruvendu.DEPARTMENTS), {"75", "77", "78", "91", "92", "93", "94", "95"})


class DetailPostalCodeTest(unittest.TestCase):
    def test_breadcrumb_ldjson(self):
        from scraper.sources.paruvendu import detail_postal_code
        html = '{"@type":"ListItem","position":3,"name": "Boulogne-Billancourt (92100)","item":"https://x"}'
        self.assertEqual(detail_postal_code(html), "92100")
        self.assertEqual(detail_postal_code("googletag.pubads().setTargeting('DPT', ['92']).setTargeting('CP', ['92120'])"), "92120")
        self.assertIsNone(detail_postal_code('{"name": "Accueil"}'))


if __name__ == "__main__":
    unittest.main()
