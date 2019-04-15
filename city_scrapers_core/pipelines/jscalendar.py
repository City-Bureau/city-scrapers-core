from datetime import datetime
from uuid import uuid4

from city_scrapers_core.decorators import ignore_processed


class JSCalendarPipeline:
    """
    Pipeline for transforming Meeting items into JSCalendar format
    https://tools.ietf.org/html/draft-ietf-calext-jscalendar-11
    """

    @ignore_processed
    def process_item(self, item, spider):
        return {
            "@type": "jsevent",
            "uid": item.get("uid") or str(uuid4()),
            "title": item["title"],
            "updated": datetime.now().isoformat()[:19],
            "description": item["description"],
            "isAllDay": item["all_day"],
            "status": item["status"],
            "start": item["start"].isoformat()[:19],
            "timeZone": spider.timezone,
            "duration": self.create_duration(item),
            "locations": self.create_locations(item),
            "links": self.create_links(item),
            "cityscrapers.org/id": item["id"],
            "cityscrapers.org/timeNotes": item["time_notes"],
            "cityscrapers.org/agency": spider.agency,
            "cityscrapers.org/classification": item["classification"],
        }

    def create_links(self, item):
        """Generate a mapping of link URLs and dictionaries for JSCalendar"""
        link_map = {link["href"]: link for link in item["links"]}
        link_map["cityscrapers.org/source"] = {
            "href": item["source"],
            "title": "Source",
        }
        return link_map

    def create_locations(self, item):
        """Create locations dict for JSCalendar"""
        loc_dict = item["location"]
        if "address" in loc_dict:
            loc_dict["cityscrapers.org/address"] = loc_dict.pop("address", None)
        return {"location": loc_dict}

    def create_duration(self, item):
        """Create ISO 8601 duration string from start and end datetimes"""
        time_diff = item["end"] - item["start"]
        dur_str = "P"
        if time_diff.days > 0:
            dur_str += "{}D".format(time_diff.days)
        if time_diff.seconds > 0:
            dur_str += "T"
        if time_diff.seconds >= 3600:
            dur_str += "{}H".format(time_diff.seconds // 3600)
        if (time_diff.seconds // 60) % 60 > 0:
            dur_str += "{}M".format((time_diff.seconds // 60) % 60)
        return dur_str
