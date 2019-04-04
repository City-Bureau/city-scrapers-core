import json
from datetime import datetime, timedelta
from operator import itemgetter
from urllib.parse import urlparse

from pytz import timezone

from .diff import DiffPipeline


class S3DiffPipeline(DiffPipeline):
    """S3 backend for comparing previously scraped JSCalendar outputs"""

    def __init__(self, crawler):
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
        super().__init__(crawler)

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
