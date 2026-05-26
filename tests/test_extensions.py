from city_scrapers_core.extensions import AzureBlobFeedStorage


def test_azure_blob_feed_storage_accepts_feed_options_kwarg():
    """Scrapy 2.12+ passes feed_options to feed-storage classes. Verify the
    kwarg is accepted without raising."""
    uri = "azure://account:key@container/feed.json"
    storage = AzureBlobFeedStorage(uri, feed_options={"foo": "bar"})
    assert storage is not None
    assert storage.feed_options == {"foo": "bar"}


def test_azure_blob_feed_storage_works_without_feed_options():
    """Backwards compat: existing callers that don't pass feed_options still work."""
    uri = "azure://account:key@container/feed.json"
    storage = AzureBlobFeedStorage(uri)
    assert storage is not None
    assert storage.feed_options is None
