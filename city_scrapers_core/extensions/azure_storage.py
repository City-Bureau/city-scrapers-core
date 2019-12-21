from scrapy.extensions.feedexport import BlockingFeedStorage


class AzureBlobFeedStorage(BlockingFeedStorage):
    def __init__(self, uri):
        from azure.storage.blob import ContainerClient

        container = uri.split("@")[1].split("/")[0]
        filename = "/".join(uri.split("@")[1].split("/")[1::])
        account_name, account_key = uri[8::].split("@")[0].split(":")

        self.account_name = account_name
        self.account_key = account_key
        self.container = container
        self.filename = filename
        self.container_client = ContainerClient(
            "{}.blob.core.windows.net".format(self.account_name),
            self.container,
            credential=self.account_key,
        )

    def _store_in_thread(self, file):
        file.seek(0)
        self.container_client.upload_blob(self.filename, file, overwrite=True)
