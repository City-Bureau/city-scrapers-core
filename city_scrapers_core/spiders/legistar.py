from datetime import datetime
from typing import Iterable, List, Mapping, Optional, Tuple
from urllib.parse import urlparse

import scrapy
from legistar.events import LegistarEventsScraper

from ..items import Meeting
from .spider import CityScrapersSpider

LINK_TYPES = ["Agenda", "Minutes", "Video", "Summary", "Captions"]


class LegistarSpider(CityScrapersSpider):
    """Subclass of :class:`CityScrapersSpider` that handles processing Legistar sites,
    which almost always share the same components and general structure.

    Uses the `Legistar events scraper <https://github.com/opencivicdata/python-legistar-scraper/blob/master/legistar/events.py>`_
    from the ```python-legistar-scraper`` library <https://github.com/opencivicdata/python-legistar-scraper>`.

    Any methods that don't pull the correct values can be replaced.
    """  # noqa

    link_types = []

    def parse(self, response: scrapy.http.Response) -> Iterable[Meeting]:
        """Parse response from the :class:`LegistarEventsScraper`. Ignores the ``scrapy``
        :class:`Response` which is still requested to be able to hook into ``scrapy``
        broadly.

        :param response: Scrapy response to be ignored
        :return: Iterable of processed meetings
        """

        events = self._call_legistar()
        return self.parse_legistar(events)

    def parse_legistar(
        self, events: Iterable[Tuple[Mapping, Optional[str]]]
    ) -> Iterable[Meeting]:
        """Method to be implemented by Spider classes that will handle the response from
        Legistar. Functions similar to ``parse`` for other Spider classes.

        :param events: Iterable consisting of tuples of a dict-like object of scraped
                       results from legistar and an agenda URL (if available)
        :raises NotImplementedError: Must be implemented in subclasses
        :return: [description]
        """

        raise NotImplementedError("Must implement parse_legistar")

    def _call_legistar(
        self, since: int = None
    ) -> Iterable[Tuple[Mapping, Optional[str]]]:
        les = LegistarEventsScraper()
        les.BASE_URL = self.base_url
        les.EVENTSPAGE = f"{self.base_url}/Calendar.aspx"
        if not since:
            since = datetime.today().year
        return les.events(since=since)

    def legistar_start(self, item: Mapping) -> datetime:
        """Pulls the start time from a Legistar item

        :param item: Scraped item from Legistar
        :return: Meeting start datetime
        """

        start_date = item.get("Meeting Date")
        start_time = item.get("Meeting Time")
        if start_date and start_time:
            try:
                return datetime.strptime(
                    f"{start_date} {start_time}", "%m/%d/%Y %I:%M %p"
                )
            except ValueError:
                return datetime.strptime(start_date, "%m/%d/%Y")

    def legistar_links(self, item: Mapping) -> List[Mapping[str, str]]:
        """Pulls relevant links from a Legistar item

        :param item: Scraped item from Legistar
        :return: List of meeting links
        """

        links = []
        for link_type in LINK_TYPES + self.link_types:
            if isinstance(item.get(link_type), dict) and item[link_type].get("url"):
                links.append({"href": item[link_type]["url"], "title": link_type})
        return links

    def legistar_source(self, item: Mapping) -> str:
        """Pulls the source URL from a Legistar item. Pulls a specific meeting URL if
        available, otherwise defaults to the general Legistar calendar page.

        :param item: Scraped item from Legistar
        :return: Source URL
        """

        default_url = f"{self.base_url}/Calendar.aspx"
        if isinstance(item.get("Name"), dict):
            return item["Name"].get("url", default_url)
        if isinstance(item.get("Meeting Details"), dict):
            return item["Meeting Details"].get("url", default_url)
        return default_url

    @property
    def base_url(self) -> str:
        """Property with the Legistar site's base URL

        :return: Legistar base URL
        """

        parsed_url = urlparse(self.start_urls[0])
        return f"{parsed_url.scheme}://{parsed_url.netloc}"
