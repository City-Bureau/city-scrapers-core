from datetime import datetime, timedelta

from city_scrapers_core.decorators import ignore_processed


class MeetingPipeline:
    @ignore_processed
    def process_item(self, item, spider):
        item["title"] = spider._clean_title(item["title"])
        # Set default end time of two hours later if end time is not present or if it's
        # the same time as the start
        if not item.get("end") or (
            isinstance(item.get("end"), datetime)
            and (item["end"] - item["start"]).seconds < 60
        ):
            item["end"] = item["start"] + timedelta(hours=2)
        return item
