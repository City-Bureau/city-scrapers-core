from datetime import timedelta

from city_scrapers_core.decorators import ignore_jscalendar


class MeetingPipeline:
    @ignore_jscalendar
    def process_item(self, item, spider):
        item["title"] = spider._clean_title(item["title"])
        if not item.get("end"):
            item["end"] = item["start"] + timedelta(hours=2)
        return item
