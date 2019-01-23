from datetime import datetime

from scrapy.exceptions import DropItem

from city_scrapers_core.constants import CANCELLED
from city_scrapers_core.items import Meeting


class DiffPipeline:
    """
    Class for comparing previous feed export results in JSCalendar format and either
    merging UIDs for consistency or marking upcoming meetings that no longer appear as
    cancelled.
    """

    def __init__(self, *args, **kwargs):
        self.scraped_ids = set()

    def process_item(self, item, spider):
        """Merge past UIDs with items if a match, cancel missing upcoming meetings"""
        # Return item unchanged if diff middleware not enabled
        if not hasattr(spider, "_previous_map"):
            return item

        # Merge uid if this is a current item
        if isinstance(item, Meeting) or (
            isinstance(item, dict) and "cityscrapers.org/id" not in item
        ):
            if item["id"] in self.scraped_ids:
                raise DropItem("Item has already been scraped")
            self.scraped_ids.add(item["id"])
            if item["id"] in spider._previous_map:
                # Bypass __setitem__ call on Meeting to add uid
                if isinstance(item, Meeting):
                    item._values["uid"] = spider._previous_map[item["id"]]
                else:
                    item["uid"] = spider._previous_map[item["id"]]
            return item
        # Drop items that are already included or are in the past
        if (
            item["cityscrapers.org/id"] in self.scraped_ids
            or (
                item["cityscrapers.org/id"] in spider._current_ids
                and item["cityscrapers.org/id"] in spider._previous_ids
            )
            or item["start"] < datetime.now().isoformat()[:19]
        ):
            raise DropItem("Previous item is in scraped results or the past")
        # # If the item is upcoming and outside the prior criteria, mark it cancelled
        self.scraped_ids.add(item["cityscrapers.org/id"])
        return {**item, "status": CANCELLED}
