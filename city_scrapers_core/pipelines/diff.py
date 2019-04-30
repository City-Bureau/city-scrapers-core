import json
from datetime import datetime, timedelta
from operator import attrgetter, itemgetter
from urllib.parse import urlparse

from pytz import timezone
from scrapy import signals
from scrapy.exceptions import DontCloseSpider, DropItem
from scrapy.http import Response

from city_scrapers_core.constants import CANCELLED
from city_scrapers_core.items import Meeting


class DiffPipeline:
    """
    Class for loading and comparing previous feed export results in OCD or JSCalendar
    format. Either merges UIDs for consistency or marks upcoming meetings that no longer
    appear as cancelled.

    Provider-specific backends can be created by subclassing and implementing the
    `load_previous_results` method.
    """

    def __init__(self, crawler, output_format):
        self.crawler = crawler
        self.output_format = output_format

    @classmethod
    def from_crawler(cls, crawler):
        pipelines = crawler.settings.get("ITEM_PIPELINES", {})
        if "city_scrapers_core.pipelines.JSCalendarPipeline" in pipelines:
            output_format = "jscalendar"
        elif "city_scrapers_core.pipelines.OpenCivicDataPipeline" in pipelines:
            output_format = "ocd"
        else:
            raise ValueError(
                "One of the output format pipelines must be enabled for diff middleware"
            )
        pipeline = cls(crawler, output_format)
        crawler.spider._previous_results = pipeline.load_previous_results()
        if output_format == "ocd":
            crawler.spider._previous_map = {
                result["extra"]["cityscrapers.org/id"]: result["_id"]
                for result in crawler.spider._previous_results
            }
        elif output_format == "jscalendar":
            crawler.spider._previous_map = {
                result["cityscrapers.org/id"]: result["uid"]
                for result in crawler.spider._previous_results
            }
        crawler.spider._scraped_ids = set()
        crawler.signals.connect(pipeline.spider_idle, signal=signals.spider_idle)
        return pipeline

    def process_item(self, item, spider):
        """Merge past UIDs with items if a match, cancel missing upcoming meetings"""
        # Merge uid if this is a current item
        id_key = "_id" if self.output_format == "ocd" else "uid"
        if isinstance(item, Meeting) or (isinstance(item, dict) and id_key not in item):
            if item["id"] in spider._scraped_ids:
                raise DropItem("Item has already been scraped")
            spider._scraped_ids.add(item["id"])
            if item["id"] in spider._previous_map:
                # Bypass __setitem__ call on Meeting to add uid
                if isinstance(item, Meeting):
                    item._values[id_key] = spider._previous_map[item["id"]]
                else:
                    item[id_key] = spider._previous_map[item["id"]]
            return item
        if self.output_format == "ocd":
            scraper_id = item["extra"]["cityscrapers.org/id"]
        elif self.output_format == "jscalendar":
            scraper_id = item["cityscrapers.org/id"]

        # Drop items that are already included or are in the past
        if (
            scraper_id in spider._scraped_ids
            or item["start"] < datetime.now().isoformat()[:19]
        ):
            raise DropItem("Previous item is in scraped results or the past")
        # # If the item is upcoming and not scraped, mark it cancelled
        spider._scraped_ids.add(scraper_id)
        return {**item, "status": CANCELLED}

    def spider_idle(self, spider):
        """Add _previous_results to spider queue when current results finish"""
        scraper = self.crawler.engine.scraper
        self.crawler.signals.disconnect(self.spider_idle, signal=signals.spider_idle)
        for item in spider._previous_results:
            scraper._process_spidermw_output(item, None, Response(""), spider)
        raise DontCloseSpider

    def load_previous_results(self):
        """Return a list of dictionaries loaded from a previous feed export"""
        raise NotImplementedError


class AzureDiffPipeline(DiffPipeline):
    """Azure Blob Storage backend for comparing previously scraped JSCalendar outputs"""

    def __init__(self, crawler, output_format):
        from azure.storage.blob import BlockBlobService

        feed_uri = crawler.settings.get("FEED_URI")
        account_name, account_key = feed_uri[8::].split("@")[0].split(":")
        self.spider = crawler.spider
        self.blob_service = BlockBlobService(
            account_name=account_name, account_key=account_key
        )
        self.container = feed_uri.split("@")[1].split("/")[0]
        self.feed_prefix = crawler.settings.get(
            "CITY_SCRAPERS_DIFF_FEED_PREFIX", "%Y/%m/%d"
        )
        super().__init__(crawler, output_format)

    def load_previous_results(self):
        max_days_previous = 3
        days_previous = 0
        tz = timezone(self.spider.timezone)
        while days_previous <= max_days_previous:
            matching_blobs = self.blob_service.list_blobs(
                self.container,
                prefix=(
                    tz.localize(datetime.now()) - timedelta(days=days_previous)
                ).strftime(self.feed_prefix),
            )
            spider_blobs = [
                blob
                for blob in matching_blobs
                if "{}.".format(self.spider.name) in blob.name
            ]
            if len(spider_blobs) > 0:
                break
            days_previous += 1

        if len(spider_blobs) == 0:
            return []

        blob = sorted(spider_blobs, key=attrgetter("name"))[-1]
        feed_text = self.blob_service.get_blob_to_text(self.container, blob.name)
        return [
            json.loads(line) for line in feed_text.content.split("\n") if line.strip()
        ]


class S3DiffPipeline(DiffPipeline):
    """S3 backend for comparing previously scraped JSCalendar outputs"""

    def __init__(self, crawler, output_format):
        import boto3

        parsed = urlparse(crawler.settings.get("FEED_URI"))
        self.spider = crawler.spider
        self.feed_prefix = crawler.settings.get(
            "CITY_SCRAPERS_DIFF_FEED_PREFIX", "%Y/%m/%d"
        )
        self.bucket = parsed.netloc
        self.client = boto3.client(
            "s3",
            aws_access_key_id=crawler.settings.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=crawler.settings.get("AWS_SECRET_ACCESS_KEY"),
        )
        super().__init__(crawler, output_format)

    def load_previous_results(self):
        max_days_previous = 3
        days_previous = 0
        tz = timezone(self.spider.timezone)
        while days_previous <= max_days_previous:
            match_objects = self.client.list_objects(
                Bucket=self.bucket,
                Prefix=(
                    tz.localize(datetime.now()) - timedelta(days=days_previous)
                ).strftime(self.feed_prefix),
                MaxKeys=1000,
            )
            spider_objects = [
                obj
                for obj in match_objects.get("Contents", [])
                if "{}.".format(self.spider.name) in obj["Key"]
            ]
            if len(spider_objects) > 0:
                break
            days_previous += 1

        if len(spider_objects) == 0:
            return []
        obj = sorted(spider_objects, key=itemgetter("Key"))[-1]
        feed_text = (
            self.client.get_object(Bucket=self.bucket, Key=obj["Key"])
            .get("Body")
            .read()
            .decode("utf-8")
        )
        return [json.loads(line) for line in feed_text.split("\n") if line.strip()]
