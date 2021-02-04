from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Union
from urllib.parse import parse_qs, urlencode

import scrapy

from ..items import Meeting
from .spider import CityScrapersSpider

LINK_TYPES = ["Agenda", "Minutes", "Video", "Summary", "Captions"]


class LegistarSpider(CityScrapersSpider):
    """Subclass of :class:`CityScrapersSpider` that handles processing Legistar sites,
    which almost always share the same components and general structure.

    Any methods that don't pull the correct values can be replaced.
    """  # noqa

    link_types = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Can override since_year to start earlier
        self.since_year = datetime.now().year - 1
        self._scraped_urls = set()

    def parse(self, response: scrapy.http.Response) -> Iterable[scrapy.Request]:
        """Creates initial event requests for each queried year.

        :param response: Scrapy response to be ignored
        :return: Iterable of ``Request`` objects for event pages
        """

        secrets = self._parse_secrets(response)
        current_year = datetime.now().year
        for year in range(self.since_year, current_year + 1):
            yield scrapy.Request(
                response.url,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body=urlencode(
                    {
                        **secrets,
                        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$lstYears",
                        "ctl00_ContentPlaceHolder1_lstYears_ClientState": f'{{"value":"{year}"}}',  # noqa
                    }
                ),
                callback=self._parse_legistar_events_page,
                dont_filter=True,
            )

    def parse_legistar(self, events: Iterable[Dict]) -> Iterable[Meeting]:
        """Method to be implemented by Spider classes that will handle the response from
        Legistar. Functions similar to ``parse`` for other Spider classes.

        :param events: Iterable consisting of a dict of scraped results from Legistar
        :raises NotImplementedError: Must be implemented in subclasses
        :return: ``Meeting`` objects that will be passed to pipelines, output
        """
        raise NotImplementedError("Must implement parse_legistar")

    def legistar_start(self, item: Dict) -> datetime:
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

    def legistar_links(self, item: Dict) -> List[Dict]:
        """Pulls relevant links from a Legistar item

        :param item: Scraped item from Legistar
        :return: List of meeting links
        """

        links = []
        for link_type in LINK_TYPES + self.link_types:
            if isinstance(item.get(link_type), dict) and item[link_type].get("url"):
                links.append({"href": item[link_type]["url"], "title": link_type})
        return links

    def legistar_source(self, item: Dict) -> str:
        """Pulls the source URL from a Legistar item. Pulls a specific meeting URL if
        available, otherwise defaults to the general Legistar calendar page.

        :param item: Scraped item from Legistar
        :return: Source URL
        """

        default_url = self.start_urls[0]
        if isinstance(item.get("Name"), dict):
            return item["Name"].get("url", default_url)
        if isinstance(item.get("Meeting Details"), dict):
            return item["Meeting Details"].get("url", default_url)
        return default_url

    def _parse_legistar_events_page(
        self, response: scrapy.http.Response
    ) -> Iterable[Union[Meeting, scrapy.http.Request]]:
        legistar_events = self._parse_legistar_events(response)
        yield from self.parse_legistar(legistar_events)
        yield from self._parse_next_page(response)

    def _parse_legistar_events(self, response: scrapy.http.Response) -> Iterable[Dict]:
        events_table = response.css("table.rgMasterTable")[0]

        headers = []
        for header in events_table.css("th[class^='rgHeader']"):
            header_text = (
                " ".join(header.css("*::text").extract()).replace("&nbsp;", " ").strip()
            )
            header_inputs = header.css("input")
            if header_text:
                headers.append(header_text)
            elif len(header_inputs) > 0:
                headers.append(header_inputs[0].attrib["value"])
            else:
                headers.append(header.css("img")[0].attrib["alt"])

        events = []
        for row in events_table.css("tr.rgRow, tr.rgAltRow"):
            try:
                data = defaultdict(lambda: None)
                for header, field in zip(headers, row.css("td")):
                    field_text = (
                        " ".join(field.css("*::text").extract())
                        .replace("&nbsp;", " ")
                        .strip()
                    )
                    url = None
                    if len(field.css("a")) > 0:
                        link_el = field.css("a")[0]
                        if "onclick" in link_el.attrib and link_el.attrib[
                            "onclick"
                        ].startswith(("radopen('", "window.open", "OpenTelerikWindow")):
                            url = response.urljoin(
                                link_el.attrib["onclick"].split("'")[1]
                            )
                        elif "href" in link_el.attrib:
                            url = response.urljoin(link_el.attrib["href"])
                    if url:
                        if header in ["", "ics"] and "View.ashx?M=IC" in url:
                            header = "iCalendar"
                            value = {"url": url}
                        else:
                            value = {"label": field_text, "url": url}
                    else:
                        value = field_text

                    data[header] = value

                ical_url = data.get("iCalendar", {}).get("url")
                if ical_url is None or ical_url in self._scraped_urls:
                    continue
                else:
                    self._scraped_urls.add(ical_url)
                events.append(dict(data))
            except Exception:
                pass

        return events

    def _parse_next_page(
        self, response: scrapy.http.Response
    ) -> Iterable[scrapy.Request]:
        next_page_link = response.css("a.rgCurrentPage + a")
        if len(next_page_link) == 0:
            return
        event_target = next_page_link[0].attrib["href"].split("'")[1]
        next_page_payload = {
            **parse_qs(response.request.body.decode("utf-8")),
            **self._parse_secrets(response),
            "__EVENTTARGET": event_target,
        }
        yield scrapy.Request(
            response.url,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=urlencode(next_page_payload),
            callback=self._parse_legistar_events_page,
            dont_filter=True,
        )

    def _parse_secrets(self, response: scrapy.http.Response) -> Dict:
        secrets = {
            "__EVENTARGUMENT": None,
            "__VIEWSTATE": response.css("[name='__VIEWSTATE']")[0].attrib["value"],
        }
        event_validation = response.css("[name='__EVENTVALIDATION']")
        if len(event_validation) > 0:
            secrets["__EVENTVALIDATION"] = event_validation[0].attrib["value"]
        return secrets
