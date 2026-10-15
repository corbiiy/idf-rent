import unittest

from scraper.dedupe import find_duplicate, same_photo
from scraper.model import Listing
from scraper.notify import matches
from scraper.sources import bienici


def mk(**kw):
    base = dict(id="bienici:1", source="bienici", url="https://x/1", title="t", rent=1000, charges=None, area=30.0,
                rooms=2, bedrooms=1, furnished=True, owner_type="Agence", dpe="C", postal_code="75011",
                city="Paris 11e", lat=None, lng=None, photos=[], photo_hash=None)
    base.update(kw)
    return Listing(**base)


class DedupeTest(unittest.TestCase):
    def test_same_url(self):
        a = mk(); b = mk(id="pap:9", source="pap")
        self.assertIs(find_duplicate(b, [a]), a)

    def test_same_fingerprint_and_photo(self):
        a = mk(photo_hash="dhash:ffffffffffffffff")
        b = mk(id="pap:9", source="pap", url="https://y/9", photo_hash="dhash:fffffffffffffffe")
        self.assertIs(find_duplicate(b, [a]), a)

    def test_different_photo_is_not_duplicate(self):
        a = mk(photo_hash="dhash:ffffffffffffffff")
        b = mk(id="pap:9", source="pap", url="https://y/9", photo_hash="dhash:0000000000000000")
        self.assertIsNone(find_duplicate(b, [a]))

    def test_missing_hash_never_matches(self):
        self.assertFalse(same_photo(None, "dhash:0"))


class FilterTest(unittest.TestCase):
    def test_jinka_vocabulary(self):
        l = mk()
        self.assertTrue(matches(l, {}))
        self.assertTrue(matches(l, {"rent_max": 1000, "area_min": 30, "room_min": 2, "furnished": "yes", "owner_type": "Agence", "dpe": ["A", "B", "C"]}))
        self.assertFalse(matches(l, {"rent_max": 999}))
        self.assertFalse(matches(l, {"furnished": "no"}))
        self.assertFalse(matches(l, {"owner_type": "Particulier"}))
        self.assertFalse(matches(l, {"dpe": ["A"]}))
        self.assertTrue(matches(l, {"where": {"dpts": ["75"]}}))
        self.assertTrue(matches(l, {"where": {"postalCodes": ["75011"]}}))
        self.assertFalse(matches(l, {"where": {"dpts": ["92"], "postalCodes": ["75012"]}}))
        self.assertFalse(matches(mk(expired=True), {}))


class BieniciTest(unittest.TestCase):
    def test_normalise(self):
        ad = {"id": "ag1-2", "adType": "rent", "propertyType": "flat", "city": "Paris 18e", "postalCode": "75018",
              "price": 1200, "charges": 100, "surfaceArea": 40, "roomsQuantity": 2, "bedroomsQuantity": 1,
              "isFurnished": False, "accountType": "agency", "energyClassification": "D",
              "blurInfo": {"position": {"lat": 48.88, "lon": 2.34}}, "photos": [{"url_photo": "https://p/1.jpg"}],
              "publicationDate": "2026-10-15T13:10:11.006Z", "title": "T"}
        l = bienici.normalise(ad)
        self.assertEqual(l.id, "bienici:ag1-2")
        self.assertEqual(l.url, "https://www.bienici.com/annonce/location/paris-18e/appartement/2pieces/ag1-2")
        self.assertEqual((l.rent, l.charges, l.owner_type, l.dpe, l.lat, l.lng), (1200, 100, "Agence", "D", 48.88, 2.34))
        self.assertEqual(l.photos, ["https://p/1.jpg"])


if __name__ == "__main__":
    unittest.main()


class DiscordTest(unittest.TestCase):
    def test_embed_shape(self):
        from scraper.notify import format_embed
        e = format_embed(mk(photos=["https://p/1.jpg"], posted_at="2026-10-15T13:10:11.006Z"), "Bien'ici")
        self.assertEqual(e["url"], "https://x/1")
        self.assertTrue(e["title"].startswith("1000 € — 30 m² · 2 p. · 1 ch. · meublé · DPE C"))
        self.assertEqual(e["thumbnail"], {"url": "https://p/1.jpg"})
        self.assertEqual(e["footer"]["text"], "Bien'ici · Agence")
        self.assertEqual(e["description"], "Paris 11e 75011")

    def test_batches_of_ten_to_webhook(self):
        import json, threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from scraper import notify
        received = []

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(204); self.end_headers()
            def log_message(self, *a): pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
        try:
            import os
            os.environ["DISCORD_WEBHOOK_URL"] = f"http://127.0.0.1:{srv.server_port}/hook"
            new = [mk(id=f"bienici:{i}", url=f"https://x/{i}") for i in range(25)]
            sent = notify.notify_new(new, {"bienici": "Bien'ici"}, max_messages=20)
        finally:
            os.environ.pop("DISCORD_WEBHOOK_URL", None)
            srv.shutdown()
        self.assertEqual(sent, 20)
        self.assertEqual([len(r.get("embeds", [])) for r in received], [10, 10, 0])
        self.assertIn("5 autres", received[2]["content"])
