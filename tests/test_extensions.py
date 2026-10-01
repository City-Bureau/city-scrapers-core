import inspect

from city_scrapers_core.extensions import AzureBlobFeedStorage


def test_azure_blob_feed_storage_init_accepts_feed_options_kwarg():
    """Scrapy 2.12+ passes feed_options to feed-storage classes. The kwarg must
    be present in the __init__ signature so calls don't raise TypeError.

    Tested via inspect so the test runs without the `azure` extra installed,
    matching CI which doesn't install the optional dependency.
    """
    sig = inspect.signature(AzureBlobFeedStorage.__init__)
    assert "feed_options" in sig.parameters
    assert sig.parameters["feed_options"].default is None
