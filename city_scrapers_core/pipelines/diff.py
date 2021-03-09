import json
from datetime import datetime, timedelta
from operator import attrgetter, itemgetter
from typing import List, Mapping
from urllib.parse import urlparse

from pytz import timezone
from scrapy import Spider, signals
from scrapy.crawler import Crawler
from scrapy.exceptions import DontCloseSpider, DropItem
from scrapy.http import Response

from ..constants import CANCELLED
from ..items import Meeting


class DiffPipeline:
    """Class for loading and comparing previous feed export results in OCD format.
    Either merges UIDs for consistency or marks upcoming meetings that no longer
    appear as cancelled.

    Provider-specific backends can be created by subclassing and implementing the
    `load_previous_results` method.
    """

    def __init__(self, crawler: Crawler, output_format: str):
        """Initialize a DiffPipeline object, setting the crawler and output format

        :param crawler: Current Crawler object
        :param output_format: Currently only "ocd" is supported
        """
        self.crawler = crawler
        self.output_format = output_format

    @classmethod
    def from_crawler(cls, crawler: Crawler):
        """Classmethod for creating a pipeline object from a Crawler

        :param crawler: Crawler currently being run
        :raises ValueError: Raises an error if an output format is not supplied
        :return: Instance of DiffPipeline
        """
        pipelines = crawler.settings.get("ITEM_PIPELINES", {})
        if "city_scrapers_core.pipelines.OpenCivicDataPipeline" in pipelines:
            output_format = "ocd"
        else:
            raise ValueError(
                "An output format pipeline must be enabled for diff middleware"
            )
        pipeline = cls(crawler, output_format)
        crawler.spider._previous_results = pipeline.load_previous_results()
        if output_format == "ocd":
            crawler.spider._previous_map = {}
            for result in crawler.spider._previous_results:
                extras_dict = result.get("extras") or result.get("extra") or {}
                previous_id = extras_dict.get("cityscrapers.org/id")
                crawler.spider._previous_map[previous_id] = result["_id"]
        crawler.spider._scraped_ids = set()
        crawler.signals.connect(pipeline.spider_idle, signal=signals.spider_idle)
        return pipeline

    def process_item(self, item: Mapping, spider: Spider) -> Mapping:
        """Processes Item objects or general dict-like objects and compares them to
        previously scraped values.

        :param item: Dict-like item to process from a scraper
        :param spider: Spider currently being scraped
        :raises DropItem: Drops items with IDs that have been already scraped
        :raises DropItem: Drops items that are in the past and already scraped
        :return: Returns the item, merged with previous values if found
        """
        # Merge uid if this is a current item
        id_key = "_id"
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
            extras_dict = item.get("extras") or item.get("extra") or {}
            scraper_id = extras_dict.get("cityscrapers.org/id", "")

        # Drop items that are already included or are in the past
        dt_str = datetime.now().isoformat()[:19]
        if (
            scraper_id in spider._scraped_ids
            or item.get("start", item.get("start_time")) < dt_str
        ):
            raise DropItem("Previous item is in scraped results or the past")
        # # If the item is upcoming and not scraped, mark it cancelled
        spider._scraped_ids.add(scraper_id)
        return {**item, "status": CANCELLED}

    def spider_idle(self, spider: Spider):
        """Add _previous_results to spider queue when current results finish

        :param spider: Spider being scraped
        :raises DontCloseSpider: Makes sure spider isn't closed to make sure prior
                                 results are processed
        """
        scraper = self.crawler.engine.scraper
        self.crawler.signals.disconnect(self.spider_idle, signal=signals.spider_idle)
        for item in spider._previous_results:
            scraper._process_spidermw_output(item, None, Response(""), spider)
        raise DontCloseSpider

    def load_previous_results(self) -> List[Mapping]:
        """Method that must be implemented for loading previously-scraped results

        :raises NotImplementedError: Required to be implemented on subclasses
        :return: Items previously scraped and loaded from a storage backend
        """
        raise NotImplementedError


class AzureDiffPipeline(DiffPipeline):
    """Implements :class:`DiffPipeline` for Azure Blob Storage"""

    def __init__(self, crawler: Crawler, output_format: str):
        """Initialize :class:`AzureDiffPipeline` from a crawler and set account values

        :param crawler: Current Crawler object
        :param output_format: Currently only "ocd" is supported
        """

        from azure.storage.blob import ContainerClient

        feed_uri = crawler.settings.get("FEED_URI")
        account_name, account_key = feed_uri[8::].split("@")[0].split(":")
        self.spider = crawler.spider
        self.container = feed_uri.split("@")[1].split("/")[0]
        self.container_client = ContainerClient(
            f"{account_name}.blob.core.windows.net",
            self.container,
            credential=account_key,
        )
        self.feed_prefix = crawler.settings.get(
            "CITY_SCRAPERS_DIFF_FEED_PREFIX", "%Y/%m/%d"
        )
        super().__init__(crawler, output_format)

    def load_previous_results(self) -> List[Mapping]:
        """Loads previously scraped items on Azure Blob Storage

        :return: Previously scraped results
        """
        max_days_previous = 3
        days_previous = 0
        tz = timezone(self.spider.timezone)
        while days_previous <= max_days_previous:
            matching_blobs = self.container_client.list_blobs(
                name_starts_with=(
                    tz.localize(datetime.now()) - timedelta(days=days_previous)
                ).strftime(self.feed_prefix)
            )
            spider_blobs = [
                blob for blob in matching_blobs if f"{self.spider.name}." in blob.name
            ]
            if len(spider_blobs) > 0:
                break
            days_previous += 1

        if len(spider_blobs) == 0:
            return []

        blob = sorted(spider_blobs, key=attrgetter("name"))[-1]
        feed_blob = self.container_client.get_blob_client(blob.name)
        feed_text = feed_blob.download_blob().content_as_text()
        return [json.loads(line) for line in feed_text.split("\n") if line.strip()]


class S3DiffPipeline(DiffPipeline):
    """Implements :class:`DiffPipeline` for AWS S3"""

    def __init__(self, crawler: Crawler, output_format: str):
        """Initialize :class:`S3DiffPipeline` from crawler

        :param crawler: Current Crawler object
        :param output_format: Only "ocd" is supported
        """
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

    def load_previous_results(self) -> List[Mapping]:
        """Load previously scraped items on AWS S3

        :return: Previously scraped results
        """
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
                if f"{self.spider.name}." in obj["Key"]
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


class GCSDiffPipeline(DiffPipeline):
    """Implements :class:`DiffPipeline` for Google Cloud Storage"""

    def __init__(self, crawler: Crawler, output_format: str):
        """Initialize :class:`GCSDiffPipeline` from crawler

        :param crawler: Current Crawler object
        :param output_format: Only "ocd" is supported
        """
        from google.cloud import storage

        parsed = urlparse(crawler.settings.get("FEED_URI"))
        self.spider = crawler.spider
        self.feed_prefix = crawler.settings.get(
            "CITY_SCRAPERS_DIFF_FEED_PREFIX", "%Y/%m/%d"
        )
        self.bucket_name = parsed.netloc
        self.client = storage.Client()
        self.bucket = self.client.bucket(self.bucket_name)
        super().__init__(crawler, output_format)

    def load_previous_results(self) -> List[Mapping]:
        """Load previously scraped items on Google Cloud Storage

        :return: Previously scraped results
        """
        max_days_previous = 3
        days_previous = 0
        tz = timezone(self.spider.timezone)
        while days_previous <= max_days_previous:
            match_blobs = self.client.list_blobs(
                self.bucket_name,
                prefix=(
                    tz.localize(datetime.now()) - timedelta(days=days_previous)
                ).strftime(self.feed_prefix),
            )
            spider_blobs = [
                blob for blob in match_blobs if f"{self.spider.name}." in blob.name
            ]
            if len(spider_blobs) > 0:
                break
            days_previous += 1

        if len(spider_blobs) == 0:
            return []
        blob = sorted(spider_blobs, key=attrgetter("name"))[-1]
        feed_text = self.bucket.blob(blob.name).download_as_bytes().decode("utf-8")
        return [json.loads(line) for line in feed_text.split("\n") if line.strip()]
