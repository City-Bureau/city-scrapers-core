from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from scrapy.exceptions import DropItem

from city_scrapers_core.constants import CANCELLED
from city_scrapers_core.decorators import ignore_processed
from city_scrapers_core.extensions.status import FAILING, RUNNING, StatusExtension
from city_scrapers_core.items import Meeting
from city_scrapers_core.pipelines import (
    DefaultValuesPipeline,
    DiffPipeline,
    MeetingPipeline,
    OpenCivicDataPipeline,
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


def _ocd_meeting(**kwargs):
    now = datetime.now()
    return Meeting(
        id="test_1",
        title="Test",
        description="",
        classification="Board",
        status="tentative",
        start=now,
        end=now + timedelta(hours=1),
        all_day=False,
        time_notes="",
        location={"name": "", "address": ""},
        links=[],
        source="https://example.com",
        **kwargs,
    )


def test_default_values_sets_closed_to_public_false():
    item = DefaultValuesPipeline().process_item(Meeting(title="Test"), None)
    assert item["closed_to_public"] is False


def test_ocd_includes_closed_to_public():
    spider = CityScrapersSpider(name="test", timezone="America/New_York")
    spider.agency = "Test Agency"
    pipeline = OpenCivicDataPipeline()
    closed = pipeline.process_item(_ocd_meeting(closed_to_public=True), spider)
    assert closed["extras"]["cityscrapers/closed_to_public"] is True
    # Scrapers that never set the field still export an explicit False
    open_meeting = pipeline.process_item(_ocd_meeting(), spider)
    assert open_meeting["extras"]["cityscrapers/closed_to_public"] is False


def test_ocd_exports_non_bool_closed_to_public_as_open():
    spider = CityScrapersSpider(name="test", timezone="America/New_York")
    spider.agency = "Test Agency"
    item = OpenCivicDataPipeline().process_item(
        _ocd_meeting(closed_to_public="false"), spider
    )
    assert item["extras"]["cityscrapers/closed_to_public"] is False


def test_validation_counts_non_bool_closed_to_public():
    pipeline = ValidationPipeline()
    pipeline.open_spider(None)
    pipeline.process_item(_ocd_meeting(closed_to_public=True), None)
    pipeline.process_item(_ocd_meeting(closed_to_public="false"), None)
    assert pipeline.error_count["closed_to_public"] == 1


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
        "extras": {"cityscrapers/id": "1"},
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
        "extras": {"cityscrapers/id": "1"},
    }
    spider_mock.previous_results = [previous]
    result = pipeline.process_item(previous, spider_mock)
    assert result["extras"]["cityscrapers/id"] == "1"
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


def _make_status_extension(item_count=0, has_error=False):
    """Create a StatusExtension with a mocked crawler."""
    crawler = MagicMock()
    crawler.stats.get_value.return_value = item_count
    crawler.spider.name = "test_spider"
    crawler.spider.timezone = "America/Chicago"

    ext = StatusExtension(crawler)
    ext.has_error = has_error
    ext.update_status_svg = MagicMock()
    return ext


def test_status_failing_when_zero_items():
    ext = _make_status_extension(item_count=0)
    ext.spider_closed()

    ext.update_status_svg.assert_called_once()
    svg = ext.update_status_svg.call_args[0][1]
    assert FAILING in svg
    assert RUNNING not in svg


def test_status_running_when_items_scraped():
    ext = _make_status_extension(item_count=5)
    ext.spider_closed()

    ext.update_status_svg.assert_called_once()
    svg = ext.update_status_svg.call_args[0][1]
    assert RUNNING in svg
    assert FAILING not in svg


def test_status_failing_on_error_overrides_items():
    ext = _make_status_extension(item_count=10, has_error=True)
    ext.spider_closed()

    ext.update_status_svg.assert_not_called()
