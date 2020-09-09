import json
from datetime import datetime, timedelta
from operator import itemgetter
from urllib.parse import quote, urlparse

from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError


class Command(ScrapyCommand):
    requires_project = True

    def syntax(self):
        return "[options]"

    def short_desc(self):
        return "Combine all recent feeds into latest.json and upcoming.json"

    def run(self, args, opts):
        storages = self.settings.get("FEED_STORAGES", {})
        if "s3" in storages:
            self.combine_s3()
        elif "azure" in storages:
            self.combine_azure()
        else:
            raise UsageError(
                "Either 's3' or 'azure' must be in FEED_STORAGES to combine past feeds"
            )

    def combine_s3(self):
        import boto3

        parsed = urlparse(self.settings.get("FEED_URI"))
        bucket = parsed.netloc
        feed_prefix = self.settings.get("CITY_SCRAPERS_DIFF_FEED_PREFIX", "%Y/%m/%d")
        client = boto3.client(
            "s3",
            aws_access_key_id=self.settings.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=self.settings.get("AWS_SECRET_ACCESS_KEY"),
        )

        max_days_previous = 3
        days_previous = 0
        prefix_objects = []
        while days_previous <= max_days_previous:
            prefix_objects = client.list_objects(
                Bucket=bucket,
                Prefix=(datetime.now() - timedelta(days=days_previous)).strftime(
                    feed_prefix
                ),
            ).get("Contents", [])
            if len(prefix_objects) > 0:
                break
            days_previous += 1

        spider_keys = self.get_spider_paths([obj["Key"] for obj in prefix_objects])
        meetings = []
        for key in spider_keys:
            feed_text = (
                client.get_object(Bucket=bucket, Key=key)
                .get("Body")
                .read()
                .decode("utf-8")
            )
            meetings.extend(
                [json.loads(line) for line in feed_text.split("\n") if line.strip()]
            )
            # Copy latest results for each spider
            spider_key = key.split("/")[-1]
            client.copy_object(
                Bucket=bucket,
                Key=spider_key,
                CopySource={"Bucket": bucket, "Key": key},
            )
        meetings = sorted(meetings, key=itemgetter(self.start_key))
        yesterday_iso = (datetime.now() - timedelta(days=1)).isoformat()[:19]
        upcoming = [
            meeting
            for meeting in meetings
            if meeting[self.start_key][:19] > yesterday_iso
        ]

        client.put_object(
            Body=("\n".join([json.dumps(meeting) for meeting in meetings])).encode(),
            Bucket=bucket,
            CacheControl="no-cache",
            Key="latest.json",
        )
        client.put_object(
            Body=("\n".join([json.dumps(meeting) for meeting in upcoming])).encode(),
            Bucket=bucket,
            CacheControl="no-cache",
            Key="upcoming.json",
        )

    def combine_azure(self):
        from azure.storage.blob import ContainerClient, ContentSettings

        feed_uri = self.settings.get("FEED_URI")
        feed_prefix = self.settings.get("CITY_SCRAPERS_DIFF_FEED_PREFIX", "%Y/%m/%d")
        account_name, account_key = feed_uri[8::].split("@")[0].split(":")
        container = feed_uri.split("@")[1].split("/")[0]
        container_client = ContainerClient(
            f"{account_name}.blob.core.windows.net",
            container,
            credential=account_key,
        )

        max_days_previous = 3
        days_previous = 0
        prefix_blobs = []
        while days_previous <= max_days_previous:
            prefix_blobs = [
                blob
                for blob in container_client.list_blobs(
                    name_starts_with=(
                        datetime.now() - timedelta(days=days_previous)
                    ).strftime(feed_prefix)
                )
            ]
            if len(prefix_blobs) > 0:
                break
            days_previous += 1

        spider_blob_names = self.get_spider_paths([blob.name for blob in prefix_blobs])
        meetings = []
        for blob_name in spider_blob_names:
            feed_blob = container_client.get_blob_client(blob_name)
            feed_text = feed_blob.download_blob().content_as_text()
            meetings.extend(
                [json.loads(line) for line in feed_text.split("\n") if line]
            )
            # Copy latest results for each spider
            spider_blob_name = blob_name.split("/")[-1]
            spider_blob = container_client.get_blob_client(spider_blob_name)
            spider_blob.start_copy_from_url(
                f"https://{account_name}.blob.core.windows.net"
                f"/{quote(container)}/{blob_name}"
            )
        meetings = sorted(meetings, key=itemgetter(self.start_key))
        yesterday_iso = (datetime.now() - timedelta(days=1)).isoformat()[:19]
        upcoming = [
            meeting
            for meeting in meetings
            if meeting[self.start_key][:19] > yesterday_iso
        ]

        container_client.upload_blob(
            "latest.json",
            "\n".join([json.dumps(meeting) for meeting in meetings]),
            content_settings=ContentSettings(cache_control="no-cache"),
            overwrite=True,
        )

        container_client.upload_blob(
            "upcoming.json",
            "\n".join([json.dumps(meeting) for meeting in upcoming]),
            content_settings=ContentSettings(cache_control="no-cache"),
            overwrite=True,
        )

    def get_spider_paths(self, path_list):
        """Get a list of the most recent scraper results for each spider"""
        spider_paths = []
        for spider in self.crawler_process.spider_loader.list():
            all_spider_paths = [p for p in path_list if f"{spider}." in p]
            if len(all_spider_paths) > 0:
                spider_paths.append(sorted(all_spider_paths)[-1])
        return spider_paths

    @property
    def start_key(self):
        pipelines = self.settings.get("ITEM_PIPELINES", {})
        if "city_scrapers_core.pipelines.OpenCivicDataPipeline" in pipelines:
            return "start_time"
        return "start"
