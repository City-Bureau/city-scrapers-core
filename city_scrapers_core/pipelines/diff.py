from datetime import datetime

from scrapy import signals
from scrapy.exceptions import DontCloseSpider, DropItem
from scrapy.http import Response

from city_scrapers_core.constants import CANCELLED
from city_scrapers_core.items import Meeting


class DiffPipeline:
    """
    Class for loading and comparing previous feed export results in JSCalendar format.
    Either merges UIDs for consistency or marks upcoming meetings that no longer appear
    as cancelled.

    Provider-specific backends can be created by subclassing and implementing the
    `load_previous_results` method.
    """

    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        pipeline = cls(crawler)
        crawler.spider._previous_results = pipeline.load_previous_results()
        crawler.spider._previous_map = {
            result["cityscrapers.org/id"]: result["uid"]
            for result in crawler.spider._previous_results
        }
        crawler.spider._scraped_ids = set()
        crawler.signals.connect(pipeline.spider_idle, signal=signals.spider_idle)
        return pipeline

    def process_item(self, item, spider):
        """Merge past UIDs with items if a match, cancel missing upcoming meetings"""
        # Merge uid if this is a current item
        if isinstance(item, Meeting) or (
            isinstance(item, dict) and "cityscrapers.org/id" not in item
        ):
            if item["id"] in spider._scraped_ids:
                raise DropItem("Item has already been scraped")
            spider._scraped_ids.add(item["id"])
            if item["id"] in spider._previous_map:
                # Bypass __setitem__ call on Meeting to add uid
                if isinstance(item, Meeting):
                    item._values["uid"] = spider._previous_map[item["id"]]
                else:
                    item["uid"] = spider._previous_map[item["id"]]
            return item
        # Drop items that are already included or are in the past
        if (
            item["cityscrapers.org/id"] in spider._scraped_ids
            or item["start"] < datetime.now().isoformat()[:19]
        ):
            raise DropItem("Previous item is in scraped results or the past")
        # # If the item is upcoming and not scraped, mark it cancelled
        spider._scraped_ids.add(item["cityscrapers.org/id"])
        return {**item, "status": CANCELLED}

    def spider_idle(self, spider):
        """Add _previous_results to spider queue when current results finish"""
        scraper = self.crawler.engine.scraper
        self.crawler.signals.disconnect(self.spider_idle, signal=signals.spider_idle)
        for item in spider._previous_results:
            scraper._process_spidermw_output(item, None, Response(""), spider)
        raise DontCloseSpider

    def load_previous_results(self):
        """Return a list of dictionaries loaded from a previous feed export"""
        raise NotImplementedError
