from datetime import datetime

from city_scrapers_core.constants import CANCELLED
from city_scrapers_core.items import Meeting


class DiffMiddleware:
    """
    Class for comparing previous feed export results in JSCalendar format and either
    merging UIDs for consistency or marking upcoming meetings that no longer appear as
    cancelled.

    Provider-specific backends can be created by subclassing and implementing the
    `load_previous_results` method.
    """

    def __init__(self, *args, **kwargs):
        self.previous_results = self.load_previous_results()
        self.previous_map = {
            result["cityscrapers.org/id"]: result["uid"]
            for result in self.previous_results
        }

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.spider, crawler.settings)

    def process_spider_output(self, response, result, spider):
        """
        Merge the UIDs of previously scraped meetings and cancel any upcoming meetings
        that no longer appear in results
        """
        scraped_ids = set()
        # Merge the previous UID into the item if it's already been scraped before
        for item in result:
            if isinstance(item, Meeting) or isinstance(item, dict):
                scraped_ids.add(item["id"])
                if item["id"] in self.previous_map:
                    # Bypass __setitem__ call on Meeting to add uid
                    if isinstance(item, Meeting):
                        item._values["uid"] = self.previous_map[item["id"]]
                    else:
                        item["uid"] = self.previous_map[item["id"]]
            yield item
        now_iso = datetime.now().isoformat()[:19]
        for item in self.previous_results:
            # Ignore items that are already included or are in the past
            if item["cityscrapers.org/id"] in scraped_ids or item["start"] < now_iso:
                continue
            # If the item is upcoming and outside the prior criteria, mark it cancelled
            scraped_ids.add(item["cityscrapers.org/id"])
            yield {**item, "status": CANCELLED}

    def load_previous_results(self):
        """Return a list of dictionaries loaded from a previous feed export"""
        raise NotImplementedError
