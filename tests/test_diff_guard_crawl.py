"""Engine-level tests for the DiffPipeline guard: each runs a real crawl with canned
responses in a subprocess (see tests/diff_guard_crawl.py)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from city_scrapers_core.constants import CANCELLED

SCRIPT = Path(__file__).parent / "diff_guard_crawl.py"


def crawl(tmp_path, guard, fallback):
    output = tmp_path / f"{guard}_{fallback}.json"
    subprocess.run(
        [sys.executable, str(SCRIPT), guard, fallback, str(output)],
        check=True,
        timeout=60,
    )
    return json.loads(output.read_text())


@pytest.mark.parametrize("guard", ["on", "off"])
@pytest.mark.parametrize("fallback", ["before", "after"])
def test_requests_scheduled_on_idle_are_diffed_before_previous_feed(
    tmp_path, guard, fallback
):
    result = crawl(tmp_path, guard, fallback)
    assert result["finish_reason"] == "finished"
    assert result["errors"] == []
    # Every fresh meeting is published once, with the previous _id, none cancelled
    assert sorted(item["_id"] for item in result["items"]) == sorted(
        item["_id"] for item in result["previous"]
    )
    assert not any(item["status"] == CANCELLED for item in result["items"])
    assert all(
        item["updated_at"] != "2026-01-01T00:00:00-08:00" for item in result["items"]
    )


def test_zero_scrape_crawl_trips_and_finishes(tmp_path):
    result = crawl(tmp_path, "on", "none")
    assert result["finish_reason"] == "finished"
    assert len(result["errors"]) == 1
    assert "Diff guard tripped" in result["errors"][0]
    assert result["items"] == result["previous"]
    # Waiting for a quiet idle pass costs about one extra 5 second idle cycle
    assert result["elapsed"] < 20


def test_zero_scrape_crawl_with_guard_off_cancels_upcoming(tmp_path):
    result = crawl(tmp_path, "off", "none")
    assert result["finish_reason"] == "finished"
    assert result["errors"] == []
    # The 3 upcoming meetings come back cancelled, the past one is dropped
    assert [item["status"] for item in result["items"]] == [CANCELLED] * 3
