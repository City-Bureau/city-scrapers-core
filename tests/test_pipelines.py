from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from scrapy.exceptions import DropItem

from city_scrapers_core.constants import CANCELLED
from city_scrapers_core.decorators import ignore_processed
from city_scrapers_core.items import Meeting
from city_scrapers_core.pipelines import (
    DiffPipeline,
    JSCalendarPipeline,
    MeetingPipeline,
)
from city_scrapers_core.spiders import CityScrapersSpider


def test_ignore_processed():
    TEST_DICT = {"TEST": 1}
    TEST_JSCALENDAR = {"uid": "1"}
    TEST_OCD = {"_id": "1"}

    class MockPipeline:
        @ignore_processed
        def func(self, item, spider):
            return TEST_DICT

    pipeline = MockPipeline()
    assert pipeline.func({}, None) == TEST_DICT
    assert pipeline.func(TEST_JSCALENDAR, None) == TEST_JSCALENDAR
    assert pipeline.func(TEST_OCD, None) == TEST_OCD


def test_meeting_pipeline_sets_end():
    pipeline = MeetingPipeline()
    meeting = pipeline.process_item(
        Meeting(title="Test", start=datetime.now()), CityScrapersSpider(name="test")
    )
    assert meeting["end"] > meeting["start"]
    now = datetime.now()
    meeting = pipeline.process_item(
        Meeting(title="Test", start=now, end=now), CityScrapersSpider(name="test")
    )
    assert meeting["end"] > meeting["start"]


def test_jscalendar_pipeline_links():
    pipeline = JSCalendarPipeline()
    assert pipeline.create_links(Meeting(links=[], source="https://example.com")) == {
        "cityscrapers.org/source": {"href": "https://example.com", "title": "Source"}
    }
    assert pipeline.create_links(
        Meeting(
            links=[{"href": "https://example.org", "title": "Test"}],
            source="https://example.com",
        )
    ) == {
        "https://example.org": {"href": "https://example.org", "title": "Test"},
        "cityscrapers.org/source": {"href": "https://example.com", "title": "Source"},
    }


def test_jscalendar_pipeline_duration():
    pipeline = JSCalendarPipeline()
    start = datetime.now()
    end_1 = start + timedelta(days=1, hours=2, minutes=3)
    end_2 = start + timedelta(hours=3, minutes=5, seconds=20)
    assert pipeline.create_duration(Meeting(start=start, end=end_1)) == "P1DT2H3M"
    assert pipeline.create_duration(Meeting(start=start, end=end_2)) == "PT3H5M"


def test_diff_merges_uids():
    spider_mock = MagicMock()
    spider_mock._previous_map = {"1": "TEST", "2": "TEST"}
    pipeline = DiffPipeline(None, "jscalendar")
    pipeline.previous_map = {"1": "TEST", "2": "TEST"}
    items = [{"id": "1"}, Meeting(id="2"), {"id": "3"}, Meeting(id="4")]
    results = [pipeline.process_item(item, spider_mock) for item in items]
    assert all("uid" in r for r in results[:2]) and all(
        "uid" not in r for r in results[2:]
    )


def test_diff_ignores_previous_items():
    now = datetime.now()
    pipeline = DiffPipeline(None, "jscalendar")
    spider_mock = MagicMock()
    previous = {
        "uid": "1",
        "cityscrapers.org/id": "1",
        "start": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    spider_mock._previous_results = [previous]
    with pytest.raises(DropItem):
        pipeline.process_item(previous, spider_mock)


def test_diff_cancels_upcoming_previous_items():
    now = datetime.now()
    pipeline = DiffPipeline(None, "jscalendar")
    spider_mock = MagicMock()
    previous = {
        "uid": "1",
        "cityscrapers.org/id": "1",
        "start": (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    spider_mock.previous_results = [previous]
    result = pipeline.process_item(previous, spider_mock)
    assert result["cityscrapers.org/id"] == "1"
    assert result["status"] == CANCELLED
