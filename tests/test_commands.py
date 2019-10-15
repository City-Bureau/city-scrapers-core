import os
from unittest.mock import MagicMock

import pytest  # noqa

from city_scrapers_core.commands.validate import Command as ValidateCommand


def test_validate_updates_pipelines(monkeypatch):
    monkeypatch.setitem(os.environ, "CI", "true")
    command = ValidateCommand()
    command.settings = MagicMock()
    command.settings.get.return_value = {
        "city_scrapers_core.pipelines.ValidationPipeline": 100
    }
    command._add_validation_pipeline()
    assert command.settings.set.call_count == 0
    TEST_PIPELINES = {"test": 10}
    command.settings.get.return_value = TEST_PIPELINES
    command._add_validation_pipeline()
    command.settings.set.assert_any_call(
        "ITEM_PIPELINES",
        {
            **TEST_PIPELINES,
            "city_scrapers_core.pipelines.validation.ValidationPipeline": 11,
        },
    )
