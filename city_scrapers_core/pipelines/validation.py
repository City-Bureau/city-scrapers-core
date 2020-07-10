import logging
from collections import defaultdict

from jsonschema.validators import Draft7Validator


logger = logging.getLogger(__name__)


class ValidationPipeline:
    """
    Check against schema if present, prints % valid for each property.

    Raises an exception for invalid results if CITY_SCRAPERS_ENFORCE_VALIDATION is set.
    """

    @classmethod
    def from_crawler(cls, crawler):
        obj = cls()
        obj.enforce_validation = crawler.settings.getbool(
            "CITY_SCRAPERS_ENFORCE_VALIDATION"
        )
        return obj

    def open_spider(self, spider):
        self.item_count = 0
        self.error_count = defaultdict(int)

    def close_spider(self, spider):
        self.validation_report(spider)

    def process_item(self, item, spider):
        if not hasattr(item, "jsonschema"):
            return item
        item_dict = dict(item)
        item_dict["start"] = item_dict["start"].isoformat()[:19]
        item_dict["end"] = item_dict["end"].isoformat()[:19]
        validator = Draft7Validator(item.jsonschema)
        props = list(item.jsonschema["properties"].keys())
        errors = list(validator.iter_errors(item_dict))
        error_props = self._get_props_from_errors(errors)
        for prop in props:
            self.error_count[prop] += 1 if prop in error_props else 0
        self.item_count += 1
        return item

    def validation_report(self, spider):
        """Prints a validation report to stdout and raise an error if fails"""
        props = list(self.error_count.keys())
        line_str = "-" * 12
        logger.info(f"\n{line_str}\nValidation summary for: {spider.name}\n{line_str}")
        logger.info(f"Validating {self.item_count} items\n")
        valid_list = []
        for prop in props:
            valid = (self.item_count - self.error_count[prop]) / self.item_count
            valid_list.append(valid)
            logger.info("{}: {:.0%}".format(prop, valid))
        try:
            assert all([val >= 0.9 for val in valid_list])
        except AssertionError:
            message = (
                "Less than 90% of the scraped items from {} passed validation. See "
                "the validation summary printed in stdout, and check that the "
                "scraped items are valid according to the jsonschema property of "
                "the Meeting class."
            ).format(spider.name)
            if self.enforce_validation:
                raise ValueError(message)
            else:
                logger.info(message)

    def _get_props_from_errors(self, errors):
        error_props = []
        for error in errors:
            if len(error.path) > 0:
                error_props.append(error.path[0])
        return error_props
