from city_scrapers_core.constants import NOT_CLASSIFIED, TENTATIVE
from city_scrapers_core.decorators import ignore_processed


class DefaultValuesPipeline:
    """Sets default values for Meeting items"""

    @ignore_processed
    def process_item(self, item, spider):
        item.setdefault("description", "")
        item.setdefault("all_day", False)
        item.setdefault("location", {})
        item.setdefault("links", [])
        item.setdefault("time_notes", "")
        item.setdefault("classification", NOT_CLASSIFIED)
        item.setdefault("status", TENTATIVE)
        return item
