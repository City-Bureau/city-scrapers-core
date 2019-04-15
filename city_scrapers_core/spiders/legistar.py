from datetime import datetime

from legistar.events import LegistarEventsScraper

from .spider import CityScrapersSpider

LINK_TYPES = ["Agenda", "Minutes", "Video", "Summary", "Captions"]


class LegistarSpider(CityScrapersSpider):
    link_types = []

    def parse(self, response):
        events = self._call_legistar()
        return self.parse_legistar(events)

    def _call_legistar(self, since=None):
        les = LegistarEventsScraper()
        les.BASE_URL = self.base_url
        les.EVENTSPAGE = "{}/Calendar.aspx".format(self.base_url)
        if not since:
            since = datetime.today().year
        return les.events(since=since)

    def legistar_start(self, item):
        start_date = item.get("Meeting Date")
        start_time = item.get("Meeting Time")
        if start_date and start_time:
            try:
                return datetime.strptime(
                    "{} {}".format(start_date, start_time), "%m/%d/%Y %I:%M %p"
                )
            except ValueError:
                return datetime.strptime(start_date, "%m/%d/%Y")

    def legistar_links(self, item):
        links = []
        for link_type in LINK_TYPES + self.link_types:
            if isinstance(item.get(link_type), dict) and item[link_type].get("url"):
                links.append({"href": item[link_type]["url"], "title": link_type})
        return links

    def legistar_source(self, item):
        default_url = "{}/Calendar.aspx".format(self.base_url)
        if isinstance(item.get("Name"), dict):
            return item["Name"].get("url", default_url)
        if isinstance(item.get("Meeting Details"), dict):
            return item["Meeting Details"].get("url", default_url)
        return default_url

    @property
    def base_url(self):
        proto = "https" if self.start_urls[0].startswith("https://") else "http"
        return "{}://{}".format(proto, self.allowed_domains[0])
