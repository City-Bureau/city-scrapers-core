from datetime import datetime

import pytz
from scrapy import signals

RUNNING = "running"
FAILING = "failing"
STATUS_COLOR_MAP = {RUNNING: "#44cc11", FAILING: "#cb2431"}
STATUS_ICON = """
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="144" height="20">
    <linearGradient id="b" x2="0" y2="100%">
        <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
        <stop offset="1" stop-opacity=".1"/>
    </linearGradient>
    <clipPath id="a">
        <rect width="144" height="20" rx="3" fill="#fff"/>
    </clipPath>
    <g clip-path="url(#a)">
        <path fill="#555" d="M0 0h67v20H0z"/>
        <path fill="{color}" d="M67 0h77v20H67z"/>
        <path fill="url(#b)" d="M0 0h144v20H0z"/>
    </g>
    <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="110">
        <text x="345" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">{status}</text>
        <text x="345" y="140" transform="scale(.1)">{status}</text>
        <text x="1045" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">{date}</text>
        <text x="1045" y="140" transform="scale(.1)">{date}</text>
    </g>
</svg>
"""  # noqa


class StatusExtension:
    """
    Scrapy extension for maintaining an SVG badge for each scraper's status.

    TODO: Track how many items are scraped on each run.
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.has_error = False

    @classmethod
    def from_crawler(cls, crawler):
        ext = cls(crawler)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(ext.spider_error, signal=signals.spider_error)
        return ext

    def spider_closed(self):
        if self.has_error:
            return
        svg = self.create_status_svg(self.crawler.spider, RUNNING)
        self.update_status_svg(self.crawler.spider, svg)

    def spider_error(self):
        self.has_error = True
        svg = self.create_status_svg(self.crawler.spider, FAILING)
        self.update_status_svg(self.crawler.spider, svg)

    def create_status_svg(self, spider, status):
        tz = pytz.timezone(spider.timezone)
        return STATUS_ICON.format(
            color=STATUS_COLOR_MAP[status],
            status=status,
            date=tz.localize(datetime.now()).strftime("%Y-%m-%d"),
        )

    def update_status_svg(self, spider, svg):
        raise NotImplementedError
