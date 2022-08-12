import json
from datetime import datetime
from typing import Dict, Iterable, List

import scrapy
from city_scrapers_core.constants import NOT_CLASSIFIED
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider

# from ..constants import NOT_CLASSIFIED
# from ..items import Meeting
# from .spider import CityScrapersSpider


class EventsCalendarSpider(CityScrapersSpider):
    """Subclass of CityScrapersSpider that may be useful
    for WordPress sites with the Events Calendar plugin.
    Three additional things need to be implemented when subclassing:
        1. a categories dict
        2. _parse_location()
        3. _parse_links()"""

    @property
    def categories(self) -> Dict:
        """categories dict should be of the following format:
        categories = {
            BOARD: ["category-1", "category-2"],
            ..
        }"""
        raise NotImplementedError("Must assign categories field")

    def _parse_location(self, item: Dict) -> Dict:
        raise NotImplementedError("Must implement _parse_location")

    def _parse_links(self, item: Dict) -> List[Dict]:
        raise NotImplementedError("Must implement _parse_links")

    def parse(self, response: scrapy.http.Response) -> Iterable[scrapy.Request]:
        res = json.loads(response.text)
        for item in res["events"]:
            classification = self._parse_classification(item)
            if classification == NOT_CLASSIFIED:
                continue
            meeting = Meeting(
                title=item["title"],
                description=item["description"],
                classification=self._parse_classification(item),
                start=self._parse_start(item["start_date_details"]),
                end=self._parse_end(item["end_date_details"]),
                all_day=item["all_day"],
                time_notes="",
                location=self._parse_location(item),
                links=self._parse_links(item),
                source=self._parse_source(item),
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

        if "next_rest_url" in res:
            yield response.follow(res["next_rest_url"], callback=self.parse)

    def _parse_classification(self, item: Dict) -> str:
        """Parse classification from categories dict,
        which needs to be specified in the subclass."""
        if item["categories"]:
            for CLASSIFICATION in self.categories:
                if item["categories"][0]["slug"] in self.categories[CLASSIFICATION]:
                    return CLASSIFICATION
        return NOT_CLASSIFIED

    def _parse_start(self, item: Dict) -> str:
        return datetime(
            int(item["year"]),
            int(item["month"]),
            int(item["day"]),
            int(item["hour"]),
            int(item["minutes"]),
            int(item["seconds"]),
        )

    def _parse_end(self, item: Dict) -> datetime:
        return datetime(
            int(item["year"]),
            int(item["month"]),
            int(item["day"]),
            int(item["hour"]),
            int(item["minutes"]),
            int(item["seconds"]),
        )

    def _parse_source(self, item: Dict) -> str:
        """Pulls specific meeting URL if available,
        otherwise defaults to the general page."""
        source = item["url"] if item["url"] else self.start_urls[0]
        return source
