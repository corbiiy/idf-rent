import unittest
from datetime import datetime, timezone, timedelta
from unittest import mock

from scraper import run
from scraper.dedupe import find_duplicate
from scraper.http import SourceBlocked
from scraper.model import Listing
from tests.test_core import mk


def iso(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).replace(microsecond=0).isoformat()


class FakeSource:
    def __init__(self, slug, listings=(), error=None, interval=0):
        self.SLUG, self.LABEL, self.COLOR = slug, slug, "#000"
        self.MIN_INTERVAL = interval
        self._listings, self._error = list(listings), error

    def fetch(self, session, departments, max_pages=2):
        if self._error:
            raise self._error
        yield from self._listings

    def is_live(self, session, listing):
        return True


class DueSourcesTest(unittest.TestCase):
    def test_min_interval_and_ordering(self):
        srcs = {"a": FakeSource("a"), "b": FakeSource("b", interval=3600), "c": FakeSource("c")}
        status = {"a": {"last_run": iso(5)}, "b": {"last_run": iso(10)}, "c": {"last_run": iso(50)}}
        with mock.patch.dict(run.SOURCES, srcs, clear=True):
            self.assertEqual(run.due_sources(["a", "b", "c"], status), ["c", "a"])
            status["b"]["last_run"] = iso(120)
            self.assertEqual(run.due_sources(["a", "b", "c"], status), ["b", "c", "a"])


class RunCycleTest(unittest.TestCase):
    def test_status_records_ok_and_errors_independently(self):
        ok = mk(id="a:1", source="a", url="https://a/1")
        srcs = {"a": FakeSource("a", [ok]), "b": FakeSource("b", error=SourceBlocked("403")), "c": FakeSource("c", error=ValueError("boom"))}
        with mock.patch.dict(run.SOURCES, srcs, clear=True):
            stored, new, status = run.run_cycle([], session=None, departments=["75"], sources=["a", "b", "c"],
                                                liveness=False, hash_photos=False, status={})
        self.assertEqual([l.id for l in new], ["a:1"])
        self.assertIsNone(status["a"]["last_error"]); self.assertEqual(status["a"]["count"], 1)
        self.assertTrue(status["b"]["last_error"].startswith("blocked:"))
        self.assertTrue(status["c"]["last_error"].startswith("ValueError"))
        self.assertTrue(all(status[s]["last_run"] for s in "abc"))

    def test_budget_defers_remaining_sources(self):
        srcs = {s: FakeSource(s, [mk(id=f"{s}:1", source=s, url=f"https://{s}/1")]) for s in "ab"}
        with mock.patch.dict(run.SOURCES, srcs, clear=True), mock.patch("scraper.run.time.monotonic", side_effect=[0, 0, 500, 500, 500]):
            _, new, status = run.run_cycle([], None, ["75"], ["a", "b"], liveness=False, hash_photos=False, status={}, budget=100)
        self.assertEqual([l.source for l in new], ["a"])
        self.assertNotIn("b", status)


class GeoDedupeTest(unittest.TestCase):
    def test_same_ad_on_two_networks_without_photo_hash(self):
        a = mk(id="era:1", source="era", url="https://era/1", lat=48.85612, lng=2.35223)
        b = mk(id="laforet:9", source="laforet", url="https://laforet/9", lat=48.85634, lng=2.35201)
        self.assertIs(find_duplicate(b, [a]), a)
        far = mk(id="laforet:8", source="laforet", url="https://laforet/8", lat=48.86, lng=2.36)
        self.assertIsNone(find_duplicate(far, [a]))


if __name__ == "__main__":
    unittest.main()
