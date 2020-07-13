from scrapy import Item, Spider

from ..constants import NOT_CLASSIFIED, TENTATIVE
from ..decorators import ignore_processed


class DefaultValuesPipeline:
    """Pipeline for setting default values on scraped Item objects"""

    @ignore_processed
    def process_item(self, item: Item, spider: Spider) -> Item:
        """Pipeline hook for setting multiple default values for scraped Item objects

        :param item: An individual Item that's been scraped
        :param spider: Spider passed to the pipeline
        :return: Item with defaults set
        """

        item.setdefault("description", "")
        item.setdefault("all_day", False)
        item.setdefault("location", {})
        item.setdefault("links", [])
        item.setdefault("time_notes", "")
        item.setdefault("classification", NOT_CLASSIFIED)
        item.setdefault("status", TENTATIVE)
        return item
