import json
from datetime import datetime, timedelta
from operator import attrgetter

from pytz import timezone

from .diff import DiffMiddleware


class AzureDiffMiddleware(DiffMiddleware):
    """Azure Blob Storage backend for comparing previously scraped JSCalendar outputs"""

    def __init__(self, spider, settings):
        from azure.storage.blob import BlockBlobService

        self.spider = spider
        feed_uri = settings.get("FEED_URI")
        account_name, account_key = feed_uri[8::].split("@")[0].split(":")
        self.blob_service = BlockBlobService(
            account_name=account_name, account_key=account_key
        )
        self.container = feed_uri.split("@")[1].split("/")[0]
        self.feed_prefix = settings.get("CITY_SCRAPERS_DIFF_FEED_PREFIX", "%Y/%m/%d")
        super().__init__()

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
                blob for blob in matching_blobs if self.spider.name in blob.name
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
