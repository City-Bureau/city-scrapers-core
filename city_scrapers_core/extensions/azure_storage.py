from scrapy.extensions.feedexport import BlockingFeedStorage


class AzureBlobFeedStorage(BlockingFeedStorage):
    def __init__(self, uri):
        from azure.storage.blob import BlobServiceClient

        container = uri.split("@")[1].split("/")[0]
        filename = "/".join(uri.split("@")[1].split("/")[1::])
        account_name, account_key = uri[8::].split("@")[0].split(":")

        self.account_name = account_name
        self.account_key = account_key
        self.container = container
        self.filename = filename
        self.blob_service = BlobServiceClient(
            "{}.blob.core.windows.net".format(self.account_name),
            credential=self.account_key,
        )
        self.container_client = self.blob_service.get_container_client(self.container)

    def _store_in_thread(self, file):
        file.seek(0)
        self.container_client.upload_blob(self.filename, file, overwrite=True)
