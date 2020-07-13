from datetime import datetime

import pytz
from scrapy import Spider, signals
from scrapy.crawler import Crawler

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
    """Scrapy extension for maintaining an SVG badge for each scraper's status."""

    def __init__(self, crawler: Crawler):
        self.crawler = crawler
        self.has_error = False
        # TODO: Track how many items are scraped on each run.

    @classmethod
    def from_crawler(cls, crawler: Crawler):
        """Generate an extension from a crawler

        :param crawler: Current scrapy crawler
        """
        ext = cls(crawler)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(ext.spider_error, signal=signals.spider_error)
        return ext

    def spider_closed(self):
        """Updates the status SVG with a running status unless the spider has
        encountered an error in which case it exits
        """
        if self.has_error:
            return
        svg = self.create_status_svg(self.crawler.spider, RUNNING)
        self.update_status_svg(self.crawler.spider, svg)

    def spider_error(self):
        """Sets the `has_error` flag on the first spider error and immediately updates the
        SVG with a "failing" status
        """
        self.has_error = True
        svg = self.create_status_svg(self.crawler.spider, FAILING)
        self.update_status_svg(self.crawler.spider, svg)

    def create_status_svg(self, spider: Spider, status: str) -> str:
        """Format a template status SVG string based on a spider and status information

        :param spider: Spider to determine the status for
        :param status: String indicating scraper status, one of "running", "failing"
        :return: An SVG string formatted for a given spider and status
        """

        tz = pytz.timezone(spider.timezone)
        return STATUS_ICON.format(
            color=STATUS_COLOR_MAP[status],
            status=status,
            date=tz.localize(datetime.now()).strftime("%Y-%m-%d"),
        )

    def update_status_svg(self, spider: Spider, svg: str):
        """Method for updating the status button SVG for a storage provider. Must be
        implemented on subclasses.

        :param spider: Spider with the status being tracked
        :param svg: Templated SVG string
        :raises NotImplementedError: Raises if not implemented on subclass
        """
        raise NotImplementedError


class AzureBlobStatusExtension(StatusExtension):
    """
    Implements :class:`StatusExtension` for Azure Blob Storage
    """

    def update_status_svg(self, spider: Spider, svg: str):
        """Implements writing templated status SVG to Azure Blob Storage

        :param spider: Spider with the status being tracked
        :param svg: Templated SVG string
        """

        from azure.storage.blob import ContainerClient, ContentSettings

        container_client = ContainerClient(
            f"{self.crawler.settings.get('AZURE_ACCOUNT_NAME')}.blob.core.windows.net",
            self.crawler.settings.get("CITY_SCRAPERS_STATUS_CONTAINER"),
            credential=self.crawler.settings.get("AZURE_ACCOUNT_KEY"),
        )
        container_client.upload_blob(
            f"{spider.name}.svg",
            svg,
            content_settings=ContentSettings(
                content_type="image/svg+xml", cache_control="no-cache"
            ),
            overwrite=True,
        )


class S3StatusExtension(StatusExtension):
    """Implements :class:`StatusExtension` for AWS S3"""

    def update_status_svg(self, spider: Spider, svg: str):
        """Implements writing templated status SVG to AWS S3

        :param spider: Spider with the status being tracked
        :param svg: Templated SVG string
        """

        import boto3

        s3_client = boto3.client(
            "s3",
            aws_access_key_id=self.crawler.settings.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=self.crawler.settings.get("AWS_SECRET_ACCESS_KEY"),
        )
        s3_client.put_object(
            Body=svg.encode(),
            Bucket=self.crawler.settings.get("CITY_SCRAPERS_STATUS_BUCKET"),
            CacheControl="no-cache",
            ContentType="image/svg+xml",
            Key=f"{spider.name}.svg",
        )
