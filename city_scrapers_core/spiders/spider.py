import re
from datetime import datetime
from typing import Mapping, Optional

from pytz import timezone
from scrapy import Spider

from ..constants import CANCELLED, PASSED, TENTATIVE


class CityScrapersSpider(Spider):
    """Base Spider class for City Scrapers projects. Provides a few utilities for common
    tasks like creating a meeting ID and checking the status based on meeting details.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add parameters for feed storage in spider local time
        if not hasattr(self, "timezone"):
            self.timezone = "America/Chicago"
        tz = timezone(self.timezone)
        now = tz.localize(datetime.now())
        self.year = now.year
        self.month = now.strftime("%m")
        self.day = now.strftime("%d")
        self.hour_min = now.strftime("%H%M")

    def _clean_title(self, title: str) -> str:
        """Remove cancelled strings from title"""
        clean_title = re.sub(
            r"([\s:-]{1,3})?(cancel\w+|rescheduled)([\s:-]{1,3})?",
            "",
            title,
            flags=re.IGNORECASE,
        ).strip()
        # Remove leading and trailing pipes, dashes, and colons
        return re.sub(r"(^[|\-:]\s+|\s*[|\-:]$)", "", clean_title).strip()

    def get_id(self, item: Mapping, identifier: Optional[str] = None) -> str:
        """Create an ID for a meeting based on its details like title and start time as
        well as any agency-provided unique identifiers.

        :param item: Meeting to generate an ID for
        :param identifier: Optional unique meeting identifier if available, defaults to
                           None
        :return: ID string based on meeting details
        """
        return self._get_id(item, identifier=identifier)

    def _get_id(self, item: Mapping, identifier: Optional[str] = None) -> str:
        """Create an ID based off of the meeting details, title and any identifiers"""
        underscore_title = re.sub(
            r"\s+",
            "_",
            re.sub(r"[^A-Z^a-z^0-9^]+", " ", self._clean_title(item["title"])),
        ).lower()
        item_id = (identifier or "x").replace("/", "-")
        start_str = item["start"].strftime("%Y%m%d%H%M")
        return "/".join([self.name, start_str, item_id, underscore_title])

    def get_status(self, item: Mapping, text: str = "") -> str:
        """Determine the status of a meeting based off of its details as well as any
        additional text that may indicate whether it has been cancelled.

        :param item: Meeting to get the status for
        :param text: Any additional text not included in the meeting details that may
                     indicate whether it's been cancelled, defaults to ""
        :return: Status constant
        """
        return self._get_status(item, text=text)

    def _get_status(self, item: Mapping, text: str = "") -> str:
        """
        Generates one of the allowed statuses from constants based on the title and time
        of the meeting
        """
        meeting_text = " ".join(
            [item.get("title", ""), item.get("description", ""), text]
        ).lower()
        if any(word in meeting_text for word in ["cancel", "rescheduled", "postpone"]):
            return CANCELLED
        if item["start"] < datetime.now():
            return PASSED
        return TENTATIVE
