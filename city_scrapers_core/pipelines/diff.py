import inspect
import json
import logging
from datetime import date, datetime, timedelta
from operator import attrgetter, itemgetter
from typing import List, Mapping, Optional
from urllib.parse import urlparse

from pytz import timezone
from scrapy import Spider, signals
from scrapy.crawler import Crawler
from scrapy.exceptions import DontCloseSpider, DropItem
from scrapy.http import Response
from scrapy.settings import Settings
from twisted.python.failure import Failure

from ..constants import CANCELLED
from ..items import Meeting

logger = logging.getLogger(__name__)


DEFAULT_GUARD_ENABLED = True
DEFAULT_GUARD_MIN_RATIO = 0.5
DEFAULT_GUARD_MIN_PREVIOUS = 3


class DiffGuardTripped(Exception):
    """Sent through the ``spider_error`` signal when the diff guard keeps the previous
    feed instead of marking its upcoming meetings cancelled."""


def _now_str() -> str:
    # The same "now" and string comparison process_item uses to decide whether a
    # previous item is in the past
    return datetime.now().isoformat()[:19]


def _is_current_item(item) -> bool:
    # Items yielded by the spider are Meeting objects or dicts without "_id". Previous
    # results re-injected on idle are OCD dicts with "_id".
    return isinstance(item, Meeting) or (isinstance(item, dict) and "_id" not in item)


def _previous_scraper_id(item: Mapping) -> str:
    extras_dict = item.get("extras") or item.get("extra") or {}
    scraper_id = extras_dict.get("cityscrapers/id")
    return scraper_id or extras_dict.get("cityscrapers.org/id") or ""


def _start_str(item: Mapping) -> str:
    start = item.get("start", item.get("start_time"))
    if isinstance(start, (datetime, date)):
        return start.isoformat()
    if isinstance(start, str):
        return start
    # Anything else doesn't count as upcoming, which errs towards tripping the guard
    return ""


def _is_upcoming(item: Mapping, now_str: str) -> bool:
    return _start_str(item)[:19] >= now_str


def _process_previous_item(scraper, item: Mapping, spider: Spider):
    """Send a previous item through the scraper's spider output handling, which runs
    it through the item pipelines and sends ``item_scraped``. Newer Scrapy releases
    dropped the request and spider arguments of this private method."""
    params = inspect.signature(scraper._process_spidermw_output).parameters
    if "spider" in params:
        scraper._process_spidermw_output(item, None, Response(""), spider)
    else:
        scraper._process_spidermw_output(item, Response(""))


class DiffPipeline:
    """Class for loading and comparing previous feed export results in OCD format.
    Either merges UIDs for consistency or marks upcoming meetings that no longer
    appear as cancelled.

    Provider-specific backends can be created by subclassing and implementing the
    `load_previous_results` method.

    **Diff guard.** A broken scrape (the site is down, returns an empty page, or its
    markup changed) yields few or no meetings, and without a guard every upcoming
    meeting in the previous feed would be published as cancelled. Once the crawl has
    finished, the pipeline checks the run and trips the guard when any of these hold:

    * zero meetings were scraped and the previous feed had any,
    * zero upcoming meetings were scraped and the previous feed had upcoming ones,
    * the previous feed had at least ``CITY_SCRAPERS_DIFF_GUARD_MIN_PREVIOUS`` (3)
      upcoming meetings and fewer than ``CITY_SCRAPERS_DIFF_GUARD_MIN_RATIO`` (0.5)
      times that many upcoming meetings were scraped,
    * the check itself raised an exception (fail safe).

    A meeting counts as scraped once it has passed every item pipeline. When the guard
    trips, previous items that weren't scraped this run are re-emitted unchanged (same
    ``_id``, ``status`` and ``updated_at``, past meetings included), an error is
    logged, the ``diff_guard/tripped`` stat is set and the ``spider_error`` signal is
    sent, so :class:`StatusExtension` shows the spider as failing and error reporting
    extensions such as scrapy-sentry-errors report it. When it doesn't trip, the diff
    works as before.

    The guard is sticky: a tripped run re-publishes the previous feed, which becomes
    the next run's baseline, so a genuine mass removal keeps tripping until someone
    sets ``CITY_SCRAPERS_DIFF_GUARD_ENABLED = False`` (for example in the spider's
    ``custom_settings``) or tunes the thresholds.

    The previous feed is only injected on a quiet idle pass: the engine is idle and no
    request was scheduled and no item processed since the previous ``spider_idle``
    call. Every ``spider_idle`` receiver runs in the same pass, so this keeps another
    receiver that schedules more requests on idle, whatever its order, from making the
    run look empty. It costs one extra idle cycle (about 5 seconds) per crawl.
    """

    def __init__(self, crawler: Crawler, output_format: str):
        """Initialize a DiffPipeline object, setting the crawler and output format

        :param crawler: Current Crawler object
        :param output_format: Currently only "ocd" is supported
        """
        self.crawler = crawler
        self.output_format = output_format
        settings = getattr(crawler, "settings", None)
        if settings is None:
            settings = Settings()
        self.guard_enabled = settings.getbool(
            "CITY_SCRAPERS_DIFF_GUARD_ENABLED", DEFAULT_GUARD_ENABLED
        )
        self.guard_min_ratio = settings.getfloat(
            "CITY_SCRAPERS_DIFF_GUARD_MIN_RATIO", DEFAULT_GUARD_MIN_RATIO
        )
        self.guard_min_previous = settings.getint(
            "CITY_SCRAPERS_DIFF_GUARD_MIN_PREVIOUS", DEFAULT_GUARD_MIN_PREVIOUS
        )
        self.guard_tripped = False
        self.scraped_count = 0
        self.scraped_upcoming_count = 0
        self.activity_count = 0
        self.idle_activity_count = None

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
                previous_id = extras_dict.get("cityscrapers/id") or extras_dict.get(
                    "cityscrapers.org/id"
                )
                crawler.spider._previous_map[previous_id] = result["_id"]
        crawler.spider._scraped_ids = set()
        for signal in (
            signals.request_scheduled,
            signals.item_scraped,
            signals.item_dropped,
            signals.item_error,
        ):
            crawler.signals.connect(pipeline.record_activity, signal=signal)
        crawler.signals.connect(pipeline.record_scraped, signal=signals.item_scraped)
        crawler.signals.connect(pipeline.spider_idle, signal=signals.spider_idle)
        return pipeline

    def record_activity(self):
        """Counts scheduled requests and processed items, so spider_idle can tell
        whether anything happened since its previous call"""
        self.activity_count += 1

    def record_scraped(self, item: Mapping):
        """Counts meetings that passed every pipeline, so items a later pipeline fails
        on don't make a broken run look healthy. Disconnected before the previous feed
        is injected."""
        self.scraped_count += 1
        if _is_upcoming(item, _now_str()):
            self.scraped_upcoming_count += 1

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
        if _is_current_item(item):
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
            scraper_id = _previous_scraper_id(item)

        if self.guard_tripped:
            # Keep previous items that weren't scraped this run as they were, past or
            # upcoming, instead of dropping or cancelling them
            if scraper_id in spider._scraped_ids:
                raise DropItem("Previous item is in scraped results")
            spider._scraped_ids.add(scraper_id)
            return item

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

    def crawl_finished(self) -> bool:
        """True when the engine is idle and nothing was scheduled or processed since
        the previous idle call. The first idle call always returns False, because
        receivers connected after this one may still schedule requests in the same
        pass."""
        activity = self.activity_count
        quiet = activity == self.idle_activity_count
        self.idle_activity_count = activity
        return quiet and self.crawler.engine.spider_is_idle()

    def spider_idle(self, spider: Spider):
        """Add _previous_results to spider queue when current results finish

        :param spider: Spider being scraped
        :raises DontCloseSpider: Makes sure spider isn't closed to make sure prior
                                 results are processed
        """
        if not self.crawl_finished():
            raise DontCloseSpider
        self.crawler.signals.disconnect(
            self.record_scraped, signal=signals.item_scraped
        )
        try:
            self.check_guard(spider)
        except Exception:
            logger.exception("Diff guard check failed for %s", spider.name)
            if not self.guard_tripped:
                self.trip_guard(spider, "the guard check raised an exception")
        scraper = self.crawler.engine.scraper
        self.crawler.signals.disconnect(self.spider_idle, signal=signals.spider_idle)
        for item in spider._previous_results:
            _process_previous_item(scraper, item, spider)
        raise DontCloseSpider

    def check_guard(self, spider: Spider):
        """Trips the guard if this run's scraped meetings look like a broken scrape
        compared to the previous feed"""
        if not self.guard_enabled:
            return
        now_str = _now_str()
        previous = spider._previous_results
        previous_upcoming = sum(1 for item in previous if _is_upcoming(item, now_str))
        scraped = self.scraped_count
        scraped_upcoming = self.scraped_upcoming_count

        if scraped == 0 and len(previous) > 0:
            reason = "scraped zero meetings"
        elif scraped_upcoming == 0 and previous_upcoming > 0:
            reason = "scraped zero upcoming meetings"
        elif (
            previous_upcoming >= self.guard_min_previous
            and scraped_upcoming < self.guard_min_ratio * previous_upcoming
        ):
            reason = (
                f"scraped upcoming meetings fell below {self.guard_min_ratio:.0%} "
                "of the previous feed"
            )
        else:
            return
        self.trip_guard(
            spider,
            reason,
            f"scraped={scraped}, scraped_upcoming={scraped_upcoming}, "
            f"previous={len(previous)}, previous_upcoming={previous_upcoming}",
        )

    def trip_guard(self, spider: Spider, reason: str, counts: Optional[str] = None):
        """Keeps the previous feed for this run, logs an error and sends spider_error.
        Never raises."""
        self.guard_tripped = True
        message = f"Diff guard tripped for {spider.name}: {reason}"
        if counts:
            message += f" ({counts})"
        message += ". Previous meetings are re-emitted unchanged instead of cancelled."
        logger.error(message)
        try:
            self.crawler.stats.set_value("diff_guard/tripped", 1)
        except Exception:
            logger.exception("Could not set diff guard stat for %s", spider.name)
        try:
            try:
                raise DiffGuardTripped(message)
            except DiffGuardTripped:
                failure = Failure()
            # send_catch_log logs receiver exceptions instead of raising them
            self.crawler.signals.send_catch_log(
                signal=signals.spider_error,
                failure=failure,
                response=None,
                spider=spider,
            )
        except Exception:
            logger.exception("Could not report diff guard error for %s", spider.name)

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
