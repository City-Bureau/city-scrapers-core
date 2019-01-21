from datetime import datetime, timedelta

import pytest  # noqa

from city_scrapers_core.decorators import ignore_jscalendar
from city_scrapers_core.items import Meeting
from city_scrapers_core.pipelines import JSCalendarPipeline, MeetingPipeline
from city_scrapers_core.spiders import CityScrapersSpider


def test_ignore_jscalendar():
    TEST_DICT = {"TEST": 1}
    TEST_JSCALENDAR = {"cityscrapers.org/id": 2}

    class MockPipeline:
        @ignore_jscalendar
        def func(self, item, spider):
            return TEST_DICT

    pipeline = MockPipeline()
    assert pipeline.func({}, None) == TEST_DICT
    assert pipeline.func(TEST_JSCALENDAR, None) == TEST_JSCALENDAR


def test_meeting_pipeline_sets_end():
    pipeline = MeetingPipeline()
    meeting = pipeline.process_item(
        Meeting(title="Test", start=datetime.now()), CityScrapersSpider(name="test")
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
