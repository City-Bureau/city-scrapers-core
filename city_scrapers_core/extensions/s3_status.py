from .status import StatusExtension


class S3StatusExtension(StatusExtension):
    def update_status_svg(self, spider, svg):
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
            Key="{}.svg".format(spider.name),
        )
