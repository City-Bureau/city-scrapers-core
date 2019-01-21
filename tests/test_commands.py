import os
import subprocess
from unittest.mock import MagicMock

import pytest
from scrapy.exceptions import UsageError

from city_scrapers_core.commands.validate import Command as ValidateCommand


def test_validate_checks_ci(monkeypatch):
    monkeypatch.setitem(os.environ, "CI", "")
    settings_mock = MagicMock()
    settings_mock.get.return_value = {}
    opts_mock = MagicMock()
    opts_mock.all = False
    with pytest.raises(UsageError):
        command = ValidateCommand()
        command.settings = settings_mock
        command.run([], opts_mock)


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


def test_validate_gets_changed_spiders(monkeypatch):
    monkeypatch.setitem(os.environ, "TRAVIS_PULL_REQUEST", "1")
    monkeypatch.setattr(ValidateCommand, "spiders_dir", "city_scrapers/spiders")
    command = ValidateCommand()
    diff_output = """
    city_scrapers/script.py
    city_scrapers/spiders/spider_1.py
    city_scrapers/spiders/spider_2.py
    city_scrapers/tests/spider_1.py
    """
    check_output_mock = MagicMock()
    check_output_mock.return_value = diff_output.encode()
    monkeypatch.setattr(subprocess, "check_output", check_output_mock)
    assert command._get_changed_spiders() == ["spider_1", "spider_2"]
