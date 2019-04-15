from datetime import datetime, timedelta

import pytest

from city_scrapers_core.constants import CANCELLED, PASSED, TENTATIVE
from city_scrapers_core.spiders import CityScrapersSpider, LegistarSpider


@pytest.fixture
def spider():
    return CityScrapersSpider(name="city_scrapers")


def test_spider_clean_title(spider):
    assert spider._clean_title(" | Test 12 : Canceledd - ") == "Test 12"


def test_spider_get_id(spider):
    item = {"start": datetime(2000, 1, 1, 0, 0, 0), "title": "Test 1 : Canceled"}
    assert spider._get_id(item) == "city_scrapers/200001010000/x/test_1"
    assert (
        spider._get_id(item, identifier="test")
        == "city_scrapers/200001010000/test/test_1"
    )


def test_spider_get_status(spider):
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    tomorrow = now + timedelta(days=1)
    assert spider._get_status({"start": yesterday}) == PASSED
    assert spider._get_status({"start": tomorrow}) == TENTATIVE
    assert (
        spider._get_status({"start": tomorrow, "description": "Canceled"}) == CANCELLED
    )
    assert spider._get_status({"start": yesterday}, text="rescheduled") == CANCELLED


def test_legistar_spider_links():
    class PatchedLegistarSpider(LegistarSpider):
        link_types = ["Fixture"]

    TEST_ITEM = {
        "Agenda": {"url": "https://example.com"},
        "Fixture": {"url": "https://example.org"},
    }
    spider = LegistarSpider(name="city_scrapers")
    patched_spider = PatchedLegistarSpider(name="city_scrapers")
    assert spider.legistar_links(TEST_ITEM) == [
        {"href": "https://example.com", "title": "Agenda"}
    ]
    assert patched_spider.legistar_links(TEST_ITEM) == [
        {"href": "https://example.com", "title": "Agenda"},
        {"href": "https://example.org", "title": "Fixture"},
    ]


def test_legistar_start():
    spider = LegistarSpider(name="city_scrapers")
    assert spider.legistar_start(
        {"Meeting Date": "1/1/2019", "Meeting Time": "12:00 PM"}
    ) == datetime(2019, 1, 1, 12)
    assert spider.legistar_start(
        {"Meeting Date": "1/1/2019", "Meeting Time": "Cancelled"}
    ) == datetime(2019, 1, 1)


def test_legistar_source():
    DEFAULT = "https://cityscrapers.legistar.com/Calendar.aspx"
    EXAMPLE = "https://example.com"
    spider = LegistarSpider(
        name="city_scrapers",
        start_urls=[DEFAULT],
        allowed_domains=["cityscrapers.legistar.com"],
    )
    assert spider.legistar_source({"Name": {"url": EXAMPLE}}) == EXAMPLE
    assert (
        spider.legistar_source({"Meeting Details": {"url": EXAMPLE}, "Name": ""})
        == EXAMPLE
    )
    assert spider.legistar_source({"Meeting Details": ""}) == DEFAULT
