from datetime import datetime
from uuid import uuid1

from city_scrapers_core.decorators import ignore_processed


class OpenCivicDataPipeline:
    """
    Pipeline for transforming Meeting items into Open Civic Data Event format
    https://opencivicdata.readthedocs.io/en/latest/data/event.html
    """

    @ignore_processed
    def process_item(self, item, spider):
        return {
            "_type": "event",
            "_id": item.get("_id") or "ocd-event/" + str(uuid1()),
            "updated_at": datetime.now().isoformat()[:19],
            "name": item["title"],
            "description": item["description"],
            "classification": item["classification"],
            "status": item["status"],
            "all_day": item["all_day"],
            "start_time": item["start"].isoformat()[:19],
            "end_time": item["end"].isoformat()[:19],
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
                "cityscrapers.org/time_notes": item["time_notes"],
                "cityscrapers.org/address": item["location"]["address"],
            },
        }

    def create_location(self, item):
        loc_str = " ".join(
            [item["location"]["name"], item["location"]["address"]]
        ).strip()
        return {"url": "", "name": loc_str, "coordinates": None}
