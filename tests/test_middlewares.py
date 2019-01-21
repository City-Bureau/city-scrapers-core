from datetime import datetime, timedelta

import pytest

from city_scrapers_core.constants import CANCELLED
from city_scrapers_core.items import Meeting
from city_scrapers_core.middlewares.diff import DiffMiddleware


@pytest.fixture
def middleware():
    class PatchedDiff(DiffMiddleware):
        def load_previous_results(self):
            return []

    return PatchedDiff()


def test_diff_merges_uids(middleware):
    middleware.previous_map = {"1": "TEST", "2": "TEST"}
    items = [{"id": "1"}, Meeting(id="2"), {"id": "3"}, Meeting(id="4")]
    results = list(middleware.process_spider_output(None, items, None))
    assert all("uid" in r for r in results[:2]) and all(
        "uid" not in r for r in results[2:]
    )


def test_diff_ignores_previous_items(middleware):
    now = datetime.now()
    middleware.previous_results = [
        {
            "cityscrapers.org/id": "1",
            "start": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        }
    ]
    results = list(middleware.process_spider_output(None, [], None))
    assert len(results) == 0


def test_diff_cancels_upcoming_previous_items(middleware):
    now = datetime.now()
    middleware.previous_results = [
        {
            "cityscrapers.org/id": "1",
            "start": (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        }
    ]
    results = list(middleware.process_spider_output(None, [], None))
    assert len(results) == 1
    assert results[0]["cityscrapers.org/id"] == "1"
    assert results[0]["status"] == CANCELLED
