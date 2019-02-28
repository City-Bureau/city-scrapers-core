import re
from datetime import datetime

from pytz import timezone
from scrapy import Spider

from ..constants import CANCELLED, PASSED, TENTATIVE


class CityScrapersSpider(Spider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add parameters for feed storage in spider local time
        if not hasattr(self, "timezone"):
            self.timezone = "America/Chicago"
        self.tz = timezone(self.timezone)
        self.now = self.tz.localize(datetime.now())
        self.year = self.now.year
        self.month = self.now.strftime("%m")
        self.day = self.now.strftime("%d")
        self.hour_min = self.now.strftime("%H%M")

    def _clean_title(self, title):
        """Remove cancelled strings from title"""
        return re.sub(
            r"([\s:-]{1,3})?(cancel\w+|rescheduled)([\s:-]{1,3})?",
            "",
            title,
            flags=re.IGNORECASE,
        ).strip()

    def _get_id(self, item, identifier=None):
        """Create an ID based off of the meeting details, title and any identifiers"""
        underscore_title = re.sub(
            r"\s+",
            "_",
            re.sub(r"[^A-Z^a-z^0-9^]+", " ", self._clean_title(item["title"])),
        ).lower()
        item_id = (identifier or "x").replace("/", "-")
        start_str = item["start"].strftime("%Y%m%d%H%M")
        return "/".join([self.name, start_str, item_id, underscore_title])

    def _get_status(self, item, text=""):
        """
        Generates one of the allowed statuses from constants based on the title and time
        of the meeting
        """
        meeting_text = " ".join(
            [item.get("title", ""), item.get("description", ""), text]
        ).lower()
        start_with_tz = self.tz.localize(item["start"])
        if any(word in meeting_text for word in ["cancel", "rescheduled", "postpone"]):
            return CANCELLED
        if start_with_tz < self.now:
            return PASSED
        return TENTATIVE
