from typing import Optional, Union

from scrapy.http import HtmlResponse, Request, Response, TextResponse


def file_response(
    file_name: str, mode: str = "r", url: Optional[str] = None
) -> Union[Response, HtmlResponse, TextResponse]:
    """
    Create a Scrapy fake HTTP response from a HTML file.
    Based on https://stackoverflow.com/a/12741030

    :param file_name: The relative or absolute filename from the tests directory
    :param url: The URL of the response
    :param mode: The mode the file should be opened with, defaults to "r"
    :return: A scrapy HTTP response which can be used for testing
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
