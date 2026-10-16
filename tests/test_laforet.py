import unittest
from pathlib import Path

from scraper.sources import laforet

FIXTURE = Path(__file__).parent / "fixtures" / "laforet_list.html"


class LaforetParserTest(unittest.TestCase):
    def setUp(self):
        self.listings = laforet.parse_list(FIXTURE.read_text(encoding="utf-8"))

    def test_three_cards(self):
        self.assertEqual([l.id for l in self.listings], ["laforet:52980830", "laforet:52980511", "laforet:52979365"])

    def test_fields(self):
        a, b, c = self.listings
        self.assertEqual(a.url, "https://www.laforet.com/agence-immobiliere/sevres/louer/chaville/appartement-4-pieces-52980830")
        self.assertEqual((a.rent, a.area, a.rooms, a.bedrooms), (1805, 84.38, 4, 3))
        self.assertEqual((a.postal_code, a.city), ("92370", "Chaville"))
        self.assertTrue(a.furnished)
        self.assertEqual(a.owner_type, "Agence")
        self.assertIsNone(a.dpe)
        self.assertEqual(len(a.photos), 2)
        self.assertTrue(a.photos[0].startswith("https://www.laforet.com/glide/office9/laforet_sevres/catalog/images/pr_p/5/2/9/8/0/8/3/0/52980830a.jpg?w=400&h=250"))
        self.assertEqual(a.title, "Appartement 4 pièces 84.38 m² - Chaville")
        self.assertEqual((b.rent, b.area, b.rooms, b.bedrooms, b.postal_code, b.city), (730, 26.28, 1, None, "06800", "Cagnes Sur Mer"))
        self.assertEqual((c.rent, c.area, c.rooms, c.bedrooms, c.postal_code, c.city), (2250, 63.81, 3, 2, "75020", "Paris"))
        self.assertEqual(c.url, "https://www.laforet.com/agence-immobiliere/paris19jourdain/louer/paris-20/appartement-3-pieces-52979365")

    def test_fetch_keeps_only_idf(self):
        class FakeResp:
            status_code = 200
            url = "x"
            text = FIXTURE.read_text(encoding="utf-8")

        class FakeSession:
            calls = []

            def get(self, url, **kw):
                self.calls.append(url)
                return FakeResp()

        s = FakeSession()
        got = list(laforet.fetch(s, ["75", "92"], max_pages=1))
        # the fake serves the same page for the appartement and maison lists, so each IDF card comes twice
        self.assertEqual([l.id for l in got], ["laforet:52980830", "laforet:52979365"] * 2)
        self.assertEqual(s.calls, [laforet.list_url("appartement"), laforet.list_url("maison")])
        self.assertEqual({l.id for l in laforet.fetch(FakeSession(), ["75"], max_pages=1)}, {"laforet:52979365"})

    def test_list_url(self):
        self.assertEqual(laforet.list_url(), "https://www.laforet.com/louer/location-appartement")
        self.assertEqual(laforet.list_url("maison"), "https://www.laforet.com/louer/location-maison")
        self.assertEqual(laforet.list_url("appartement", 3), "https://www.laforet.com/louer/location-appartement?page=3")


if __name__ == "__main__":
    unittest.main()
