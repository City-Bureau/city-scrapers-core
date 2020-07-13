from datetime import datetime, timedelta

from scrapy import Item, Spider

from ..decorators import ignore_processed


class MeetingPipeline:
    """General pipeline for setting some defaults on meetings, can be subclassed for
    additional processing.
    """

    @ignore_processed
    def process_item(self, item: Item, spider: Spider) -> Item:
        """Custom processing to set defaults on meeting, including cleaning up title and
        setting a default end time if one is not provided

        :param item: Scraped item passed to pipeline
        :return: Processed item
        """
        item["title"] = spider._clean_title(item["title"])
        # Set default end time of two hours later if end time is not present or if it's
        # the same time as the start
        if not item.get("end") or (
            isinstance(item.get("end"), datetime)
            and (item["end"] - item["start"]).seconds < 60
        ):
            item["end"] = item["start"] + timedelta(hours=2)
        return item
