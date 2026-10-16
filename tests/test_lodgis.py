import unittest
from pathlib import Path

from scraper.sources import lodgis

FIXTURE = Path(__file__).parent / "fixtures" / "lodgis_list.html"
CAT1 = "https://www.lodgis.com/fr/paris,location-meublee/location-meuble-paris-1_16513.cat.html"


class LodgisParserTest(unittest.TestCase):
    def setUp(self):
        self.listings, self.next_url = lodgis.parse_list(FIXTURE.read_text(encoding="utf-8"), "1")

    def test_three_cards(self):
        self.assertEqual([l.id for l in self.listings], ["lodgis:LPA9312", "lodgis:LPA20130", "lodgis:LPA26572"])
        self.assertEqual(self.next_url, CAT1 + "?p=2")

    def test_fields(self):
        a, b, c = self.listings
        self.assertEqual(a.url, "https://www.lodgis.com/fr/paris,location-meublee/appartement/LPA9312-rue-des-pyramides-appartement-paris-1.mod.html")
        self.assertEqual((a.rent, a.area, a.rooms, a.bedrooms), (1171, 19, 1, 0))
        self.assertEqual((a.postal_code, a.city), ("75001", "Paris"))
        self.assertEqual(a.title, "Studio meublé 19 m² - Palais Royal - Paris 1e")
        self.assertEqual(a.photos, ["https://www.lodgis.com/photos/lpa/ap/9312/orange/appartement-rue-des-pyramides-paris--picL.jpg?v=1502913924"])
        self.assertTrue(a.furnished)
        self.assertEqual(a.owner_type, "Agence")
        self.assertIsNone(a.dpe)
        self.assertIsNone(a.posted_at)  # "Disponible à partir du" is an availability date, not a posting date
        self.assertEqual((b.rent, b.area, b.rooms, b.bedrooms, b.postal_code), (1630, 40, 2, 1, "75001"))
        # lazy-loaded card: the photo is in data-src
        self.assertEqual(c.photos, ["https://www.lodgis.com/photos/lpa/ap/26572/orange/appartement-rue-du-roule-paris--picL.jpg?v=1792051289"])
        self.assertEqual((c.rent, c.area), (2740, 40))

    def test_weekly_price_is_skipped(self):
        html = FIXTURE.read_text(encoding="utf-8").replace("</span> /mois", "</span> /semaine", 1)
        listings, _ = lodgis.parse_list(html, "1")
        self.assertEqual([l.id for l in listings], ["lodgis:LPA20130", "lodgis:LPA26572"])

    def test_promo_price_uses_current_rent(self):
        html = FIXTURE.read_text(encoding="utf-8").replace(
            '<span class="price">1&nbsp;171&nbsp;€</span> /mois',
            '<span class="promo"><span class="price">1&nbsp;171&nbsp;€</span> /mois</span><br />'
            '<span class="tarif-promo"><span class="price">1&nbsp;050&nbsp;€</span> /mois</span>', 1)
        listings, _ = lodgis.parse_list(html, "1")
        self.assertEqual(listings[0].rent, 1050)
        self.assertEqual(listings[1].rent, 1630)

    def test_studio_variants(self):
        html = FIXTURE.read_text(encoding="utf-8").replace("Appartement meublé 1 chambre", "Duplex meublé studio", 1)
        listings, _ = lodgis.parse_list(html, "1")
        self.assertEqual((listings[1].rooms, listings[1].bedrooms), (1, 0))

    def test_list_url_and_categories(self):
        self.assertEqual(lodgis.list_url(CAT1), CAT1)
        self.assertEqual(lodgis.list_url(CAT1, 3), CAT1 + "?p=3")
        hub = ('<a href="/fr/paris,location-meublee/location-meuble-paris-10_16522.cat.html">10</a>'
               '<a href="https://www.lodgis.com/fr/paris,location-meublee/location-meuble-paris-1_16513.cat.html">1</a>'
               '<a href="/fr/paris,location-meublee/location-meuble-paris-1_16513.cat.html">dup</a>')
        self.assertEqual(lodgis.category_urls(hub), [
            ("1", CAT1),
            ("10", "https://www.lodgis.com/fr/paris,location-meublee/location-meuble-paris-10_16522.cat.html"),
        ])

    def test_paris_only(self):
        class NoSession:
            def get(self, url, **kw):
                raise AssertionError("no request expected")
        self.assertEqual(list(lodgis.fetch(NoSession(), ["92", "93"], 1)), [])


if __name__ == "__main__":
    unittest.main()
