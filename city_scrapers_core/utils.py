from scrapy.http import HtmlResponse, Request, Response, TextResponse


def file_response(file_name, mode="r", url=None):
    """
    Create a Scrapy fake HTTP response from a HTML file
    @param file_name: The relative filename from the tests directory,
                      but absolute paths are also accepted.
    @param url: The URL of the response.
    @param mode: The mode the file should be opened with.
    returns: A scrapy HTTP response which can be used for unittesting.

    Based on https://stackoverflow.com/a/12741030, a nice bit of hacking.
    """
    if not url:
        url = "http://www.example.com"

    request = Request(url=url)

    if mode == "rb":
        with open(file_name, mode) as f:
            content = f.read()
        return Response(url=url, body=content)

    with open(file_name, mode, encoding="utf-8") as f:
        content = f.read()

    if not file_name.endswith(".html"):
        return TextResponse(url=url, body=content, encoding="utf-8")

    return HtmlResponse(url=url, request=request, body=content.encode())
