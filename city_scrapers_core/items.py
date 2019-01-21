import scrapy

from .constants import CLASSIFICATIONS, STATUSES


class Meeting(scrapy.Item):
    id = scrapy.Field()
    title = scrapy.Field()
    description = scrapy.Field()
    classification = scrapy.Field()
    status = scrapy.Field()
    start = scrapy.Field()
    end = scrapy.Field()
    all_day = scrapy.Field()
    time_notes = scrapy.Field()
    location = scrapy.Field()
    links = scrapy.Field()
    source = scrapy.Field()
    jsonschema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Meeting Item",
        "type": "object",
        "definitions": {
            "location": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "address": {"type": "string"},
                },
            },
            "link": {
                "type": "object",
                "properties": {
                    "href": {"type": "string", "format": "uri"},
                    "title": {"type": "string"},
                },
                "required": ["href"],
            },
        },
        "properties": {
            "id": {
                "type": "string",
                "description": "An ID based on the scraper slug, date and time of the meeting",  # noqa
            },
            "title": {"type": "string", "description": "The title of the meeting"},
            "description": {
                "type": "string",
                "description": "A description of the specific meeting",
            },
            "all_day": {
                "type": "boolean",
                "description": "Whether the meeting occurs for the entire day",
            },
            "status": {
                "type": "string",
                "description": "The status of the meeting at the time it is scraped",
                "enum": list(STATUSES),
            },
            "classification": {
                "type": "string",
                "description": "The type of meeting from the list of options",
                "enum": list(CLASSIFICATIONS),
            },
            "start": {
                "type": "string",
                "description": "The datetime the meeting begins in local time in ISO 8601 format",  # noqa
                "format": "date-time",
            },
            "end": {
                "type": "string",
                "description": "The datetime the meeting ends in local time in ISO 8601 format",  # noqa
                "format": "date-time",
            },
            "time_notes": {
                "type": "string",
                "description": "Any additional notes about the meeting time",
            },
            "location": {
                "type": "object",
                "description": "The location where the meeting occurs",
            },
            "links": {"type": "array"},
            "source": {"type": "string", "format": "url"},
        },
        "required": ["id", "title", "start", "source"],
    }
