from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from scrapy.exceptions import DropItem

from city_scrapers_core.constants import CANCELLED
from city_scrapers_core.decorators import ignore_processed
from city_scrapers_core.items import Meeting
from city_scrapers_core.pipelines import (
    DiffPipeline,
    MeetingPipeline,
    ValidationPipeline,
)
from city_scrapers_core.spiders import CityScrapersSpider


def test_ignore_processed():
    TEST_DICT = {"TEST": 1}
    TEST_OCD = {"_id": "1"}

    class MockPipeline:
        @ignore_processed
        def func(self, item, spider):
            return TEST_DICT

    pipeline = MockPipeline()
    assert pipeline.func({}, None) == TEST_DICT
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


def test_diff_merges_uids():
    spider_mock = MagicMock()
    spider_mock._previous_map = {"1": "TEST", "2": "TEST"}
    pipeline = DiffPipeline(None, "ocd")
    pipeline.previous_map = {"1": "TEST", "2": "TEST"}
    items = [{"id": "1"}, Meeting(id="2"), {"id": "3"}, Meeting(id="4")]
    results = [pipeline.process_item(item, spider_mock) for item in items]
    assert all("_id" in r for r in results[:2]) and all(
        "_id" not in r for r in results[2:]
    )


def test_diff_ignores_previous_items():
    now = datetime.now()
    pipeline = DiffPipeline(None, "ocd")
    spider_mock = MagicMock()
    previous = {
        "_id": "1",
        "start": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        "extra": {"cityscrapers.org/id": "1"},
    }
    spider_mock._previous_results = [previous]
    with pytest.raises(DropItem):
        pipeline.process_item(previous, spider_mock)


def test_diff_cancels_upcoming_previous_items():
    now = datetime.now()
    pipeline = DiffPipeline(None, "ocd")
    spider_mock = MagicMock()
    previous = {
        "_id": "1",
        "start": (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        "extra": {"cityscrapers.org/id": "1"},
    }
    spider_mock.previous_results = [previous]
    result = pipeline.process_item(previous, spider_mock)
    assert result["extra"]["cityscrapers.org/id"] == "1"
    assert result["status"] == CANCELLED


def test_validation_handles_errors():
    pipeline = ValidationPipeline()
    pipeline.open_spider(None)
    pipeline.enforce_validation = True
    item = Meeting(
        id="test",
        title="Test",
        description="",
        classification="Board",
        status="tentative",
        start=datetime.now(),
        end=datetime.now() + timedelta(hours=1),
        all_day=False,
        time_notes="",
        location={"name": "", "address": ""},
        links=None,
        source="",
    )
    pipeline.process_item(item, None)
    assert pipeline.item_count == 1
    assert pipeline.error_count["links"] == 1


def test_validation_throws_error():
    pipeline = ValidationPipeline()
    pipeline.open_spider(None)
    pipeline.enforce_validation = True
    item = Meeting(
        id="test",
        title="Test",
        description="",
        classification="Board",
        status="tentative",
        start=datetime.now(),
        end=datetime.now() + timedelta(hours=1),
        all_day=False,
        time_notes="",
        location={"name": "", "address": ""},
        links=None,
        source="",
    )
    pipeline.process_item(item, None)
    spider_mock = MagicMock()
    spider_mock.name = "mock"
    with pytest.raises(ValueError):
        pipeline.validation_report(spider_mock)
    pipeline.error_count["links"] = 0
    pipeline.validation_report(spider_mock)
