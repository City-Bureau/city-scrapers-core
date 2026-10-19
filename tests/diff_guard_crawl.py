"""Runs one real Scrapy crawl for tests/test_diff_guard_crawl.py, in a subprocess
because the Twisted reactor can't be restarted.

usage: python tests/diff_guard_crawl.py <guard: on|off> <fallback: none|before|after>
                                        <output.json>

The spider's first page has no meetings. With a fallback, a spider_idle receiver
schedules a second page with the meetings on the first idle pass, either connected
before the diff pipeline ("before") or after it ("after"). The previous feed holds
the same meetings, so a correct run publishes them with their previous _id and
cancels nothing.
"""

import json
import sys
import time
from datetime import datetime, timedelta

from scrapy import Request, signals
from scrapy.crawler import CrawlerProcess
from scrapy.http import HtmlResponse

from city_scrapers_core.constants import TENTATIVE
from city_scrapers_core.items import Meeting
from city_scrapers_core.pipelines import DiffPipeline
from city_scrapers_core.spiders import CityScrapersSpider

GUARD, FALLBACK, OUTPUT = sys.argv[1:4]
NOW = datetime.now().replace(second=0, microsecond=0)
DAYS = [-30, 10, 40, 70]
SPIDER_NAME = "diff_guard_test"


def make_meeting(spider, days):
    item = Meeting(
        title="City Council",
        description="",
        classification="City Council",
        start=NOW + timedelta(days=days),
        end=None,
        all_day=False,
        time_notes="",
        location={"name": "City Hall", "address": "1 Main St"},
        links=[],
        source="https://example.com/fallback",
    )
    item["status"] = TENTATIVE
    item["id"] = spider._get_id(item)
    return item


class Spider(CityScrapersSpider):
    name = SPIDER_NAME
    agency = "Test Agency"
    timezone = "America/Los_Angeles"
    start_urls = ["https://example.com/primary"]

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.fallback_scheduled = False
        if FALLBACK == "before":
            crawler.signals.connect(spider.schedule_fallback, signals.spider_idle)
        elif FALLBACK == "after":
            # spider_opened fires after the item pipelines were created
            crawler.signals.connect(spider.connect_late, signals.spider_opened)
        return spider

    def connect_late(self):
        self.crawler.signals.connect(self.schedule_fallback, signals.spider_idle)

    def schedule_fallback(self):
        if not self.fallback_scheduled:
            self.fallback_scheduled = True
            self.crawler.engine.crawl(
                Request("https://example.com/fallback", callback=self.parse_fallback)
            )

    def parse(self, response):
        return []

    def parse_fallback(self, response):
        for days in DAYS:
            yield make_meeting(self, days)


def previous_feed():
    spider = Spider()
    feed = []
    for i, days in enumerate(DAYS):
        item = make_meeting(spider, days)
        feed.append(
            {
                "_type": "event",
                "_id": f"ocd-event/previous-{i}",
                "updated_at": "2026-01-01T00:00:00-08:00",
                "status": TENTATIVE,
                "start_time": item["start"].isoformat() + "-08:00",
                "extras": {"cityscrapers/id": item["id"]},
            }
        )
    return feed


PREVIOUS = previous_feed()


class InMemoryDiffPipeline(DiffPipeline):
    def load_previous_results(self):
        return [dict(item) for item in PREVIOUS]


class Canned:
    def process_request(self, request, spider=None):
        return HtmlResponse(request.url, body=b"<html></html>", request=request)


if __name__ == "__main__":
    items = []
    errors = []
    process = CrawlerProcess(
        {
            "LOG_LEVEL": "ERROR",
            "ROBOTSTXT_OBEY": False,
            "TELNETCONSOLE_ENABLED": False,
            "DOWNLOADER_MIDDLEWARES": {"__main__.Canned": 1},
            "ITEM_PIPELINES": {
                "__main__.InMemoryDiffPipeline": 200,
                "city_scrapers_core.pipelines.MeetingPipeline": 300,
                "city_scrapers_core.pipelines.OpenCivicDataPipeline": 400,
            },
            "CITY_SCRAPERS_DIFF_GUARD_ENABLED": GUARD == "on",
        }
    )
    crawler = process.create_crawler(Spider)
    crawler.signals.connect(
        lambda item: items.append(dict(item)), signal=signals.item_scraped, weak=False
    )
    crawler.signals.connect(
        lambda failure: errors.append(str(failure.value)),
        signal=signals.spider_error,
        weak=False,
    )
    started = time.monotonic()
    process.crawl(crawler)
    process.start()
    with open(OUTPUT, "w") as f:
        json.dump(
            {
                "items": items,
                "errors": errors,
                "previous": PREVIOUS,
                "elapsed": time.monotonic() - started,
                "finish_reason": crawler.stats.get_value("finish_reason"),
            },
            f,
        )
