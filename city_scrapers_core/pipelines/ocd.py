from datetime import datetime
from typing import Mapping
from uuid import uuid1

import pytz
from scrapy import Spider

from ..decorators import ignore_processed


class OpenCivicDataPipeline:
    """Pipeline for transforming Meeting items into the `Open Civic Data Event format
    <https://opencivicdata.readthedocs.io/en/latest/data/event.html>`_.
    """

    @ignore_processed
    def process_item(self, item: Mapping, spider: Spider) -> Mapping:
        """Takes a dict-like object and converts it into an Open Civic Data Event.

        :param item: Item to be converted
        :param spider: Current spider being run
        :return: Dict formatted as an OCD event
        """

        tz = pytz.timezone(spider.timezone)
        return {
            "_type": "event",
            "_id": item.get("_id") or "ocd-event/" + str(uuid1()),
            "updated_at": tz.localize(datetime.now()).isoformat(timespec="seconds"),
            "name": item["title"],
            "description": item["description"],
            "classification": item["classification"],
            "status": item["status"],
            "all_day": item["all_day"],
            "start_time": tz.localize(item["start"]).isoformat(timespec="seconds"),
            "end_time": tz.localize(item["end"]).isoformat(timespec="seconds"),
            "timezone": spider.timezone,
            "location": self.create_location(item),
            "documents": [],
            "links": [
                {"note": link["title"], "url": link["href"]} for link in item["links"]
            ],
            "sources": [{"url": item["source"], "note": ""}],
            "participants": [
                {
                    "note": "host",
                    "name": spider.agency,
                    "entity_type": "organization",
                    "entity_name": spider.agency,
                    # TODO: Include an actual ID
                    "entity_id": "",
                }
            ],
            "extra": {
                "cityscrapers.org/id": item["id"],
                "cityscrapers.org/agency": spider.agency,
                "cityscrapers.org/time_notes": item.get("time_notes", ""),
                "cityscrapers.org/address": item["location"]["address"],
            },
        }

    def create_location(self, item: Mapping) -> Mapping:
        """Creates an OCD-formatted location from a scraped item's data

        :param item: Item to process the location
        :return: Dict of the location
        """

        loc_str = " ".join(
            [item["location"]["name"] or "", item["location"]["address"] or ""]
        ).strip()
        return {"url": "", "name": loc_str, "coordinates": None}
