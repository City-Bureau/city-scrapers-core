from scrapy import signals
from scrapy.exceptions import DontCloseSpider
from scrapy.http import Response

from city_scrapers_core.items import Meeting


class DiffMiddleware:
    """
    Class for loading previously scraped results into currently scraped results for
    comparison in DiffPipeline.

    Provider-specific backends can be created by subclassing and implementing the
    `load_previous_results` method.
    """

    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls(crawler)
        crawler.spider._previous_results = middleware.load_previous_results()
        crawler.spider._previous_map = {
            result["cityscrapers.org/id"]: result["uid"]
            for result in crawler.spider._previous_results
        }
        crawler.spider._previous_ids = set()
        crawler.spider._current_ids = set()
        crawler.signals.connect(middleware.spider_idle, signal=signals.spider_idle)
        return middleware

    def process_spider_output(self, response, result, spider):
        """
        Add previous meetings to the iterable of results for processing in DiffPipeline
        """
        for item in result:
            if isinstance(item, Meeting) or isinstance(item, dict):
                spider._current_ids.add(item["id"])
            yield item

    def spider_idle(self, spider):
        """Add _previous_results to spider queue when current results finish"""
        scraper = self.crawler.engine.scraper
        self.crawler.signals.disconnect(self.spider_idle, signal=signals.spider_idle)
        for item in spider._previous_results:
            if not (
                item["cityscrapers.org/id"] in spider._previous_ids
                or item["cityscrapers.org/id"] in spider._current_ids
            ):
                spider._previous_ids.add(item["cityscrapers.org/id"])
                scraper._process_spidermw_output(item, None, Response(""), spider)
        raise DontCloseSpider

    def load_previous_results(self):
        """Return a list of dictionaries loaded from a previous feed export"""
        raise NotImplementedError
