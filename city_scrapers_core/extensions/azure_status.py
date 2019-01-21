from .status import StatusExtension


class AzureBlobStatusExtension(StatusExtension):
    def update_status_svg(self, spider, svg):
        from azure.storage.blob import BlockBlobService, ContentSettings

        blob_service = BlockBlobService(
            account_name=self.crawler.settings.get("AZURE_ACCOUNT_NAME"),
            account_key=self.crawler.settings.get("AZURE_ACCOUNT_KEY"),
        )
        blob_service.create_blob_from_text(
            self.crawler.settings.get("CITY_SCRAPERS_STATUS_CONTAINER"),
            "{}.svg".format(spider.name),
            svg,
            content_settings=ContentSettings(
                content_type="image/svg+xml", cache_control="no-cache"
            ),
        )
