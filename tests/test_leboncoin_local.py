import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "local"))
import leboncoin_parse as lp  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "leboncoin_next_data.html"


class NextDataTest(unittest.TestCase):
    def setUp(self):
        self.listings = lp.parse_next_data(FIXTURE.read_text(encoding="utf-8"))

    def test_housing_only(self):
        self.assertEqual([l.id for l in self.listings], ["leboncoin:1000000001", "leboncoin:1000000002"])

    def test_fields(self):
        a, b = self.listings
        self.assertEqual((a.rent, a.area, a.rooms, a.furnished, a.dpe, a.postal_code, a.city, a.owner_type), (850, 18.0, 1, True, "D", "75011", "Paris", "Particulier"))
        self.assertEqual(a.url, "https://www.leboncoin.fr/ad/locations/1000000001")
        self.assertEqual(a.photos, ["https://img.example/1-large.jpg"])
        self.assertEqual((a.lat, a.lng), (48.8585, 2.3798))
        self.assertEqual(a.posted_at, "2026-10-21 09:12:00")
        self.assertEqual((b.rent, b.bedrooms, b.furnished, b.owner_type, b.postal_code), (740, 1, False, "Agence", "92120"))
        self.assertEqual(b.url, "https://www.leboncoin.fr/ad/locations/1000000002")
        self.assertEqual(b.photos, [])

    def test_no_next_data(self):
        self.assertEqual(lp.parse_next_data("<html><body>nothing</body></html>"), [])


class CardsTest(unittest.TestCase):
    def test_card_fallback(self):
        cards = [{"href": "/ad/locations/1000000009?from=list", "title": "T2 lumineux", "price": "920 €", "details": "2 pièces · 38 m² · Meublé", "place": "Paris 75012", "img": "https://img.example/9.jpg"},
                 {"href": "/boutique/123", "title": "x"}]
        out = lp.parse_cards(cards)
        self.assertEqual(len(out), 1)
        l = out[0]
        self.assertEqual((l.id, l.rent, l.area, l.rooms, l.furnished, l.postal_code, l.city), ("leboncoin:1000000009", 920, 38.0, 2, True, "75012", "Paris"))
        self.assertEqual(l.url, "https://www.leboncoin.fr/ad/locations/1000000009?from=list")


class ChallengeTest(unittest.TestCase):
    def test_markers(self):
        self.assertTrue(lp.looks_like_challenge('<html><script src="https://ct.captcha-delivery.com/c.js"></script></html>'))
        self.assertTrue(lp.looks_like_challenge("<html><script>x</script></html>", url="https://www.leboncoin.fr/captcha"))
        self.assertFalse(lp.looks_like_challenge(FIXTURE.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
