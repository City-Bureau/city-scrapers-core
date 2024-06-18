import random
import re
from datetime import datetime
from urllib.parse import urljoin

from azure.storage.blob import ContainerClient, ContentSettings
from city_scrapers_core.constants import BOARD
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.relativedelta import relativedelta
from scrapy import FormRequest, Request, Selector


class BoardDocsSpiderMeta(type):
    def __init__(cls, name, bases, dct):
        required_static_vars = [
            "boarddocs_state",
            "boarddocs_committee_id",
            "boarddocs_slug",
            "timezone",
        ]
        missing_vars = [var for var in required_static_vars if var not in dct]

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            raise NotImplementedError(
                f"{name} must define the following static variable(s): {missing_vars_str}."  # noqa
            )

        super().__init__(name, bases, dct)


class BoardDocsSpider(CityScrapersSpider, metaclass=BoardDocsSpiderMeta):
    """
    Subclass of :class:`CityScrapersSpider` that handles processing
    meetings hosted on the BoardDocs platform. This spider also uploads
    meeting materials to an Azure container if `city_scrapers_env`
    setting is set to "prod".
    """

    custom_settings = {"ROBOTSTXT_OBEY": False}
    base_url = "https://go.boarddocs.com"
    classification = BOARD
    location = {"name": "TBD", "address": ""}
    links = []
    boarddocs_state = None
    timezone = None
    boarddocs_slug = None
    boarddocs_committee_id = None

    def start_requests(self):
        """
        Initiates a POST request to fetch the meetings list from BoardDocs API.
        Includes a random integer query parameter for cache-busting, mimicking
        user behavior and aiming to prevent rate limiting. If in prod mode,
        also sets up the Azure client for uploading meeting materials.
        """
        self.city_scrapers_env = self.settings.get("CITY_SCRAPERS_ENV")
        if self.city_scrapers_env == "prod":
            self.setup_azure_client()
            self.log("Prod environment: agendas will be uploaded to Azure")
        else:
            self.log("Non-prod environment: no agendas will be uploaded to Azure")
        yield Request(
            f"{self.base_url}/{self.boarddocs_state}/{self.boarddocs_slug}/Board.nsf/BD-GetMeetingsList?open&0.{self.gen_random_int()}",  # noqa
            method="POST",
            body=f"current_committee_id={self.boarddocs_committee_id}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            callback=self.parse,
        )

    def setup_azure_client(self):
        """Sets up Azure ContainerClient for blob upload."""
        azure_account_name = self.settings.get("AZURE_ACCOUNT_NAME")
        azure_account_key = self.settings.get("AZURE_ACCOUNT_KEY")
        azure_container = self.settings.get("AZURE_CONTAINER")

        for var_tuple in [
            (azure_account_name, "AZURE_ACCOUNT_NAME"),
            (azure_account_key, "AZURE_ACCOUNT_KEY"),
            (azure_container, "AZURE_CONTAINER"),
        ]:
            if not var_tuple[0]:
                raise KeyError(f"Missing settings value {var_tuple[1]}")

        account_url = f"{azure_account_name}.blob.core.windows.net"
        self.container_client = ContainerClient(
            account_url,
            container_name=azure_container,
            credential=azure_account_key,
        )

    def parse(self, response):
        """Parse the JSON list of meetings"""
        meetings = response.json()
        filtered_meetings = self._get_clean_meetings(meetings)
        for item in filtered_meetings:
            meeting_id = item["unique"]
            start_date = item["start_date"]
            # Make request to HTML page endpoint for agenda
            random_int = self.gen_random_int()
            agenda_url = f"https://go.boarddocs.com/{self.boarddocs_state}/{self.boarddocs_slug}/Board.nsf/Download-AgendaDetailed?open&{random_int}"  # noqa
            # request agenda page - send with form data
            formdata = {
                "id": meeting_id,
                "current_committee_id": self.boarddocs_committee_id,
            }
            yield FormRequest(
                agenda_url,
                method="POST",
                formdata=formdata,
                meta={"meeting_id": meeting_id, "start_date": start_date},
                callback=self.upload_agenda,
            )

    def upload_agenda(self, response):
        """Meeting materials can only be accessed using a POST request so
        we aren't able to provide a list of links in the traditional way.
        Instead, we first upload meeting materials to a city-scraper Azure
        container and then returns a list of links to those materials"""
        meeting_id = response.meta["meeting_id"]
        start_date = response.meta["start_date"]

        # If in prod mode, upload to Azure, otherwise skip
        links = []
        if self.city_scrapers_env == "prod" and not response.body:
            self.log("No content found at agenda endpoint")
        elif self.city_scrapers_env == "prod":
            directory = "meetings-downloads"
            filename = f"{directory}/{self.boarddocs_state}-{self.boarddocs_slug}-{meeting_id}.html"  # noqa
            content_settings = ContentSettings(content_type="text/html")
            clean_content = self._convert_relative_urls(response.text)
            blob_client = self.container_client.upload_blob(
                name=filename,
                data=clean_content,
                content_settings=content_settings,
                overwrite=True,
            )
            self.log(
                f"Uploaded agenda to city-scraper Azure storage: {blob_client.url}"
            )
            links.append(
                {"href": blob_client.url, "title": f"Meeting Agenda ({start_date})"}
            )

        # parse actual meeting
        detail_url = f"https://go.boarddocs.com/{self.boarddocs_state}/{self.boarddocs_slug}/Board.nsf/BD-GetMeeting?open&0.{self.gen_random_int()}"  # noqa
        details_body = (
            f"current_committee_id={self.boarddocs_committee_id}&id={meeting_id}"
        )
        yield Request(
            detail_url,
            method="POST",
            callback=self._parse_detail,
            meta={
                "start_date": start_date,
                "meeting_id": meeting_id,
                "links": links,
            },
            body=details_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def _convert_relative_urls(self, html_string):
        """Converts all relative URLs to absolute URLs in href and src attributes
        in HTML text.

        Args:
        html_string (str): The HTML content as a string.
        base_url (str): The base URL to resolve relative URLs against.

        Returns:
        str: The modified HTML string with absolute URLs.
        """
        sel = Selector(text=html_string)

        # Iterate over all elements that have 'href' attributes
        for link in sel.xpath("//*[@href]"):
            relative_url = link.xpath("@href").get()
            absolute_url = urljoin(self.base_url, relative_url)
            link.root.set("href", absolute_url)

        # Iterate over all elements that have 'src' attributes
        for src in sel.xpath("//*[@src]"):
            relative_url = src.xpath("@src").get()
            absolute_url = urljoin(self.base_url, relative_url)
            src.root.set("src", absolute_url)

        return sel.get()

    def _parse_detail(self, response):
        """Parse the HTML detail response for each meeting"""
        start_date = response.meta["start_date"]
        meeting_id = response.meta["meeting_id"]
        links = response.meta["links"]
        if re.search("no access", response.text, re.IGNORECASE):
            # For unknown reasons, some URLs return some HTML that includes a
            # "No access" message. This might be because the meeting is not
            # public or information is not yet available.
            self.logger.warning(
                f'"No access" found in the HTML of meeting {meeting_id} ({start_date})'
            )
            self.logger.warning("Aborting parse of this meeting.")
            return
        title = self._parse_title(response)
        meeting = Meeting(
            title=title,
            description=self._parse_description(response),
            classification=self._parse_classification(title),
            start=self._parse_start(response, start_date),
            end=None,
            all_day=False,
            time_notes="",
            location=self._parse_location(response),
            links=links,
            source=self._parse_source(),
        )
        meeting["status"] = self._get_status(meeting)
        meeting["id"] = self._get_id(meeting)
        yield meeting

    def _get_clean_meetings(self, data):
        """
        Cleans the data by removing any items with a date older than 2 months.
        Also adds a start_date key to each item with the parsed date.
        """
        today = datetime.today()
        two_months_ago = today - relativedelta(months=2)

        # Filter the data and add start_date
        filtered_data = []
        for item in data:
            if not item:
                # Some items are empty
                continue
            item_date = datetime.strptime(item["numberdate"], "%Y%m%d").date()
            if item_date > two_months_ago.date():
                item["start_date"] = item_date
                filtered_data.append(item)
        return filtered_data

    def gen_random_int(self):
        """Generates a random 15-digit number for cache-busting."""
        random_15_digit_number = random.randint(10**14, (10**15) - 1)
        return random_15_digit_number

    def _parse_title(self, response):
        return response.css(".meeting-name::text").get().strip()

    def _parse_start(self, response, start_date):
        """
        Extracts the meeting start time from the description and combines
        it with the start_date. Assumes the time is always before the "│"
        character.
        """
        description_text = response.css(".meeting-description::text").get()
        time_match = re.search(r"(\d{1,2}:\d{2}\s*[apAP]\.?[mM]\.?)", description_text)
        if time_match:
            time_str = time_match.group(1)
            time_str_cleaned = time_str.replace(".", "")
            time_obj = datetime.strptime(time_str_cleaned, "%I:%M %p").time()
            return datetime.combine(start_date, time_obj)
        else:
            # If no time is found, return the start_date at midnight
            return datetime.combine(start_date, datetime.min.time())

    def _parse_description(self, response):
        """
        Extracts the meeting description, cleans the HTML tags, removes
        the time and pipe if present, and normalizes the whitespace.
        """
        # Use Scrapy's CSS selector to get the text directly, avoiding the need for bs4
        description_texts = response.css(".meeting-description ::text").getall()
        cleaned_text = " ".join(description_texts).strip()

        # Remove the time and pipe if present
        cleaned_text = re.sub(
            r"^\d{1,2}:\d{2}\s*[apAP]\.?[mM]\.?\s*│\s*", "", cleaned_text, 1
        )

        # Normalize whitespace
        normalized_text = " ".join(cleaned_text.split())
        return normalized_text

    def _parse_classification(self, title):
        """Classification info is generally not available from the BoardDocs
        API. If location is available, the child class should override this
        method or set a standing classifcation as a class var"""
        return self.classification

    def _parse_location(self, response):
        """Location info is generally not available from the BoardDocs API.
        If location is available, the child class should override this
        method or set a standing location as a class var"""
        return self.location

    def _parse_source(self):
        """We can't use the source from the detail page because it's a POST
        request. So we return the generic board docs page for thr board"""
        return f"{self.base_url}/{self.boarddocs_state}/{self.boarddocs_slug}/Board.nsf/Public"  # noqa
