"""Tests for the DiffPipeline guard against broken scrapes, with a fake crawler. Real
crawls are in test_diff_guard_crawl.py."""

import json
import logging
from datetime import date, datetime
from pathlib import Path

import pytest
from freezegun import freeze_time
from scrapy import Spider, signals
from scrapy.exceptions import DontCloseSpider, DropItem
from scrapy.settings import Settings
from scrapy.signalmanager import SignalManager
from scrapy.statscollectors import MemoryStatsCollector

from city_scrapers_core.constants import CANCELLED, TENTATIVE
from city_scrapers_core.extensions.status import FAILING, RUNNING, StatusExtension
from city_scrapers_core.items import Meeting
from city_scrapers_core.pipelines import DiffPipeline
from city_scrapers_core.pipelines.diff import DiffGuardTripped

NOW = "2026-10-14 14:51:00"
SPIDER_NAME = "test_spider"
FILES = Path(__file__).parent / "files"


class InMemoryDiffPipeline(DiffPipeline):
    def load_previous_results(self):
        return [dict(item) for item in self.crawler._previous_feed]


class FakeScraper:
    """Stands in for Scrapy's Scraper: spider_idle passes each previous result to
    _process_spidermw_output, which runs it through the pipeline"""

    def __init__(self, pipeline, outputs):
        self.pipeline = pipeline
        self.outputs = outputs
        self.injected = 0

    def _process_spidermw_output(self, item, request, response, spider):
        self.injected += 1
        process(self.pipeline, item, spider, self.outputs)


def process(pipeline, item, spider, outputs, delivered=True):
    """Run one item through the pipeline and, like Scrapy, send item_scraped once it
    passes. delivered=False stands in for a later pipeline failing on it."""
    try:
        result = pipeline.process_item(item, spider)
    except DropItem:
        return
    outputs.append(result)
    if delivered:
        pipeline.crawler.signals.send_catch_log(
            signal=signals.item_scraped, item=result, response=None, spider=spider
        )


class FakeEngine:
    scraper = None
    idle = True

    def spider_is_idle(self):
        return self.idle


class FakeCrawler:
    def __init__(self, previous_feed, settings=None):
        self.settings = Settings(
            {
                "ITEM_PIPELINES": {
                    "tests.test_diff_guard.InMemoryDiffPipeline": 200,
                    "city_scrapers_core.pipelines.MeetingPipeline": 300,
                    "city_scrapers_core.pipelines.OpenCivicDataPipeline": 400,
                },
                **(settings or {}),
            }
        )
        self.signals = SignalManager(self)
        self.stats = MemoryStatsCollector(self)
        self.spider = Spider(name=SPIDER_NAME)
        self.spider.timezone = "America/Los_Angeles"
        self.engine = FakeEngine()
        self._previous_feed = previous_feed


def previous_item(slug, start_time, status=TENTATIVE):
    """OCD item as stored in the previous feed"""
    return {
        "_type": "event",
        "_id": f"ocd-event/{slug}",
        "updated_at": "2026-10-14T06:42:24-07:00",
        "name": f"Meeting {slug}",
        "status": status,
        "start_time": start_time,
        "extras": {"cityscrapers/id": f"{SPIDER_NAME}/{slug}"},
    }


def meeting(slug, start):
    return Meeting(
        id=f"{SPIDER_NAME}/{slug}",
        title=f"Meeting {slug}",
        start=start,
        status=TENTATIVE,
    )


UPCOMING = [
    previous_item("u1", "2026-10-15T17:30:00-07:00"),
    previous_item("u2", "2026-11-19T17:30:00-08:00"),
    previous_item("u3", "2026-12-17T17:30:00-08:00"),
    previous_item("u4", "2027-01-21T17:30:00-08:00"),
]
PAST = [
    previous_item("p1", "2026-09-17T17:30:00-07:00"),
    previous_item("p2", "2026-08-20T17:30:00-07:00", status=CANCELLED),
]


def make_pipeline(previous_feed, settings=None):
    crawler = FakeCrawler(previous_feed, settings)
    errors = []
    crawler.signals.connect(
        lambda failure: errors.append(failure),
        signal=signals.spider_error,
        weak=False,
    )
    pipeline = InMemoryDiffPipeline.from_crawler(crawler)
    outputs = []
    crawler.engine.scraper = FakeScraper(pipeline, outputs)
    return pipeline, outputs, errors


def idle_until_injected(pipeline):
    """Send spider_idle the way the engine does until the previous feed is injected.
    The guarded pipeline waits one quiet idle call first."""
    scraper = pipeline.crawler.engine.scraper
    for _ in range(2):
        with pytest.raises(DontCloseSpider):
            pipeline.spider_idle(pipeline.crawler.spider)
        if scraper.injected:
            return
    assert scraper.injected or not pipeline.crawler.spider._previous_results


def run_pipeline(previous_feed, scraped, settings=None, delivered=True):
    """Scraped items first, then spider_idle re-injects the previous feed. Returns
    (outputs, pipeline, errors)."""
    pipeline, outputs, errors = make_pipeline(previous_feed, settings)
    for item in scraped:
        process(pipeline, item, pipeline.crawler.spider, outputs, delivered)
    idle_until_injected(pipeline)
    return outputs, pipeline, errors


def previous_outputs(outputs):
    return {o["_id"]: o for o in outputs if isinstance(o, dict) and "_id" in o}


@freeze_time(NOW)
def test_zero_scraped_reemits_previous_feed_unchanged(caplog):
    previous_feed = UPCOMING + PAST
    with caplog.at_level(logging.ERROR, logger="city_scrapers_core.pipelines.diff"):
        outputs, pipeline, errors = run_pipeline(previous_feed, [])

    # Every previous item, upcoming and past, comes back exactly as it was
    assert outputs == previous_feed
    assert pipeline.guard_tripped
    assert pipeline.crawler.stats.get_value("diff_guard/tripped") == 1
    assert len(errors) == 1
    assert isinstance(errors[0].value, DiffGuardTripped)
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert SPIDER_NAME in record.getMessage()
    assert "scraped zero meetings" in record.getMessage()
    assert "previous_upcoming=4" in record.getMessage()


@freeze_time(NOW)
def test_zero_scraped_trips_even_below_min_previous():
    outputs, pipeline, errors = run_pipeline(UPCOMING[:1], [])
    assert pipeline.guard_tripped
    assert outputs == UPCOMING[:1]
    assert len(errors) == 1


@freeze_time(NOW)
def test_zero_scraped_with_empty_previous_feed_does_not_trip():
    outputs, pipeline, errors = run_pipeline([], [])
    assert outputs == []
    assert not pipeline.guard_tripped
    assert errors == []


@freeze_time(NOW)
def test_zero_upcoming_trips_below_min_previous():
    # One upcoming meeting before, only past meetings scraped now
    scraped = [meeting("p1", datetime(2026, 9, 17, 17, 30))]
    outputs, pipeline, errors = run_pipeline(UPCOMING[:1] + PAST, scraped)
    assert pipeline.guard_tripped
    assert len(errors) == 1
    assert "scraped zero upcoming meetings" in str(errors[0].value)
    assert previous_outputs(outputs) == {p["_id"]: p for p in UPCOMING[:1] + PAST[1:]}


@freeze_time(NOW)
def test_zero_upcoming_with_no_previous_upcoming_does_not_trip():
    scraped = [meeting("p1", datetime(2026, 9, 17, 17, 30))]
    outputs, pipeline, errors = run_pipeline(PAST, scraped)
    assert not pipeline.guard_tripped
    assert errors == []
    # Missing past meeting dropped as before
    assert previous_outputs(outputs) == {}


@freeze_time(NOW)
def test_sharp_drop_reemits_missing_meetings_unchanged():
    previous_feed = UPCOMING + PAST
    # 1 of 4 previous upcoming meetings scraped, below the default 50%
    scraped = [
        meeting("u1", datetime(2026, 10, 15, 17, 30)),
        meeting("p1", datetime(2026, 9, 17, 17, 30)),
    ]
    outputs, pipeline, errors = run_pipeline(previous_feed, scraped)

    assert pipeline.guard_tripped
    assert len(errors) == 1
    assert "fell below 50%" in str(errors[0].value)
    assert "scraped_upcoming=1" in str(errors[0].value)
    scraped_out = [o for o in outputs if isinstance(o, Meeting)]
    assert [o["_id"] for o in scraped_out] == ["ocd-event/u1", "ocd-event/p1"]
    # Items scraped this run aren't duplicated; the rest pass through unchanged
    assert previous_outputs(outputs) == {
        item["_id"]: item
        for item in previous_feed
        if item["_id"] not in ("ocd-event/u1", "ocd-event/p1")
    }


@freeze_time(NOW)
def test_drop_at_ratio_boundary_still_cancels():
    # 2 of 4 is not below 50%
    scraped = [
        meeting("u1", datetime(2026, 10, 15, 17, 30)),
        meeting("u2", datetime(2026, 11, 19, 17, 30)),
    ]
    outputs, pipeline, errors = run_pipeline(UPCOMING, scraped)
    assert not pipeline.guard_tripped
    assert errors == []
    assert {k: v["status"] for k, v in previous_outputs(outputs).items()} == {
        "ocd-event/u3": CANCELLED,
        "ocd-event/u4": CANCELLED,
    }


@freeze_time(NOW)
def test_sharp_drop_ignored_below_min_previous():
    # Only 2 upcoming meetings before, under the minimum of 3, and one of them was
    # scraped, so the other is cancelled as before
    scraped = [
        meeting("u1", datetime(2026, 10, 15, 17, 30)),
        meeting("p1", datetime(2026, 9, 17, 17, 30)),
    ]
    outputs, pipeline, errors = run_pipeline(UPCOMING[:2] + PAST, scraped)
    assert not pipeline.guard_tripped
    assert errors == []
    assert {k: v["status"] for k, v in previous_outputs(outputs).items()} == {
        "ocd-event/u2": CANCELLED,
    }


@freeze_time(NOW)
def test_healthy_run_cancels_single_missing_meeting():
    scraped = [
        meeting("u1", datetime(2026, 10, 15, 17, 30)),
        meeting("u2", datetime(2026, 11, 19, 17, 30)),
        meeting("u3", datetime(2026, 12, 17, 17, 30)),
        meeting("new", datetime(2027, 2, 18, 17, 30)),
        meeting("p1", datetime(2026, 9, 17, 17, 30)),
    ]
    outputs, pipeline, errors = run_pipeline(UPCOMING + PAST, scraped)

    assert not pipeline.guard_tripped
    assert errors == []
    assert pipeline.crawler.stats.get_value("diff_guard/tripped") is None
    # _id merged onto scraped items that were in the previous feed
    scraped_out = [o for o in outputs if isinstance(o, Meeting)]
    assert [o.get("_id") for o in scraped_out] == [
        "ocd-event/u1",
        "ocd-event/u2",
        "ocd-event/u3",
        None,
        "ocd-event/p1",
    ]
    # Only the missing upcoming meeting is re-emitted, marked cancelled; the missing
    # past meeting is dropped
    assert previous_outputs(outputs) == {
        "ocd-event/u4": {**UPCOMING[3], "status": CANCELLED}
    }


@freeze_time(NOW)
def test_duplicate_scraped_items_counted_once():
    scraped = [meeting("u1", datetime(2026, 10, 15, 17, 30))] * 3
    _, pipeline, _ = run_pipeline(UPCOMING, scraped)
    assert pipeline.scraped_upcoming_count == 1
    assert pipeline.guard_tripped


@freeze_time(NOW)
def test_items_failing_in_later_pipelines_trip_the_guard():
    scraped = [
        meeting("u1", datetime(2026, 10, 15, 17, 30)),
        meeting("u2", datetime(2026, 11, 19, 17, 30)),
    ]
    outputs, pipeline, errors = run_pipeline(UPCOMING, scraped, delivered=False)
    assert pipeline.guard_tripped
    assert "scraped zero meetings" in str(errors[0].value)
    assert previous_outputs(outputs) == {p["_id"]: p for p in UPCOMING[2:]}


@freeze_time(NOW)
def test_date_and_string_starts_are_counted_without_losing_items():
    scraped = [
        {"id": f"{SPIDER_NAME}/u1", "start": date(2026, 10, 15)},
        {"id": f"{SPIDER_NAME}/u2", "start": "2026-11-19T17:30:00"},
        {"id": f"{SPIDER_NAME}/x", "start": object()},
        {"id": f"{SPIDER_NAME}/y"},
    ]
    outputs, pipeline, _ = run_pipeline([], scraped)
    assert [o["id"] for o in outputs] == [s["id"] for s in scraped]
    assert pipeline.scraped_upcoming_count == 2


@freeze_time(NOW)
def test_thresholds_are_configurable():
    scraped = [
        meeting("u1", datetime(2026, 10, 15, 17, 30)),
        meeting("u2", datetime(2026, 11, 19, 17, 30)),
    ]
    # 2 of 4 is below 75%
    _, pipeline, _ = run_pipeline(
        UPCOMING, scraped, settings={"CITY_SCRAPERS_DIFF_GUARD_MIN_RATIO": 0.75}
    )
    assert pipeline.guard_tripped
    # The ratio rule needs at least 5 previous upcoming meetings
    _, pipeline, _ = run_pipeline(
        UPCOMING, scraped[:1], settings={"CITY_SCRAPERS_DIFF_GUARD_MIN_PREVIOUS": 5}
    )
    assert not pipeline.guard_tripped


@freeze_time(NOW)
def test_guard_can_be_disabled():
    outputs, pipeline, errors = run_pipeline(
        UPCOMING + PAST, [], settings={"CITY_SCRAPERS_DIFF_GUARD_ENABLED": False}
    )
    assert not pipeline.guard_tripped
    assert errors == []
    # Same as before the guard existed: every upcoming meeting cancelled
    assert outputs == [{**item, "status": CANCELLED} for item in UPCOMING]


@freeze_time(NOW)
def test_guard_check_failure_fails_safe(caplog, monkeypatch):
    def broken_check(self, spider):
        raise RuntimeError("boom")

    monkeypatch.setattr(InMemoryDiffPipeline, "check_guard", broken_check)
    scraped = [meeting("u1", datetime(2026, 10, 15, 17, 30))]
    outputs, pipeline, errors = run_pipeline(UPCOMING + PAST, scraped)
    assert "Diff guard check failed" in caplog.text
    assert pipeline.guard_tripped
    assert len(errors) == 1
    assert "guard check raised an exception" in str(errors[0].value)
    assert previous_outputs(outputs) == {p["_id"]: p for p in UPCOMING[1:] + PAST}


@freeze_time(NOW)
def test_reporting_failure_does_not_crash_the_run(caplog):
    pipeline, outputs, _ = make_pipeline(UPCOMING)

    def broken_receiver(failure):
        raise RuntimeError("receiver broke")

    pipeline.crawler.signals.connect(
        broken_receiver, signal=signals.spider_error, weak=False
    )
    pipeline.crawler.stats = None  # stats.set_value raises
    idle_until_injected(pipeline)
    assert pipeline.guard_tripped
    assert outputs == UPCOMING
    assert "Could not report diff guard error" in caplog.text


@freeze_time(NOW)
def test_waits_for_a_quiet_idle_pass():
    pipeline, outputs, _ = make_pipeline(UPCOMING)
    crawler = pipeline.crawler
    spider = crawler.spider

    def idle():
        with pytest.raises(DontCloseSpider):
            pipeline.spider_idle(spider)

    idle()  # the first call always waits
    assert outputs == []
    # Another receiver scheduled a request in the same idle pass
    crawler.signals.send_catch_log(signal=signals.request_scheduled)
    idle()
    assert outputs == []
    crawler.engine.idle = False
    idle()
    assert outputs == []
    crawler.engine.idle = True
    # The request produced meetings
    process(pipeline, meeting("u1", datetime(2026, 10, 15, 17, 30)), spider, [])
    process(pipeline, meeting("u2", datetime(2026, 11, 19, 17, 30)), spider, [])
    idle()
    assert outputs == []
    idle()  # quiet and idle: the diff runs now
    assert not pipeline.guard_tripped
    assert {o["_id"]: o["status"] for o in outputs} == {
        "ocd-event/u3": CANCELLED,
        "ocd-event/u4": CANCELLED,
    }


class RecordingStatusExtension(StatusExtension):
    def __init__(self, crawler):
        super().__init__(crawler)
        self.statuses = []

    def create_status_svg(self, spider, status):
        return status

    def update_status_svg(self, spider, svg):
        self.statuses.append(svg)


@freeze_time(NOW)
def test_tripped_guard_marks_status_failing():
    crawler = FakeCrawler(UPCOMING)
    status_ext = RecordingStatusExtension.from_crawler(crawler)
    pipeline = InMemoryDiffPipeline.from_crawler(crawler)
    outputs = []
    crawler.engine.scraper = FakeScraper(pipeline, outputs)
    idle_until_injected(pipeline)
    # Re-emitted items count as scraped, which alone would make the badge "running"
    crawler.stats.set_value("item_scraped_count", len(outputs))
    crawler.signals.send_catch_log(signal=signals.spider_closed)
    assert status_ext.statuses == [FAILING]
    assert RUNNING not in status_ext.statuses


def load_incident_feed():
    path = FILES / "colgo_hood_river_urban_renewal_advisory_2026101406.json"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


INCIDENT_UPCOMING = {
    "ocd-event/ebe1028e-c3ad-11f1-ae67-000d3a60a415": "2026-10-15T17:30:00-07:00",
    "ocd-event/ebe1028f-c3ad-11f1-ae67-000d3a60a415": "2026-11-19T17:30:00-08:00",
    "ocd-event/ebe10290-c3ad-11f1-ae67-000d3a60a415": "2026-12-17T17:30:00-08:00",
}


def replay_incident(settings=None):
    """Replay of the 14 Oct 2026 colgo run 38584006395 for Hood River Urban Renewal
    Advisory: the previous feed is the 06:42 PDT export from that morning, and the
    spider scraped nothing. Time is frozen at the run's time (UTC, as on GitHub
    Actions)."""
    previous_feed = load_incident_feed()
    with freeze_time("2026-10-14 14:50:00"):
        outputs, pipeline, errors = run_pipeline(previous_feed, [], settings)
    return previous_feed, outputs, pipeline, errors


def test_incident_replay_fixture():
    previous_feed = load_incident_feed()
    assert len(previous_feed) == 99
    tentative = {
        item["start_time"] for item in previous_feed if item["status"] == TENTATIVE
    }
    assert tentative == {"2026-11-19T17:30:00-08:00", "2026-12-17T17:30:00-08:00"}


def test_incident_replay_keeps_meetings_tentative():
    previous_feed, outputs, pipeline, errors = replay_incident()
    assert pipeline.guard_tripped
    assert len(errors) == 1
    assert "previous_upcoming=3" in str(errors[0].value)
    # The whole previous feed is re-published as it was
    assert outputs == previous_feed
    statuses = {o["start_time"][:10]: o["status"] for o in outputs}
    assert statuses["2026-11-19"] == TENTATIVE
    assert statuses["2026-12-17"] == TENTATIVE


def test_incident_replay_without_guard_cancels_upcoming_meetings():
    """The incident: with the guard off (as in core before the guard), the empty
    scrape publishes the Nov 19 and Dec 17 meetings as cancelled"""
    _, outputs, pipeline, errors = replay_incident(
        {"CITY_SCRAPERS_DIFF_GUARD_ENABLED": False}
    )
    assert not pipeline.guard_tripped
    assert errors == []
    assert {o["_id"]: (o["start_time"], o["status"]) for o in outputs} == {
        _id: (start, CANCELLED) for _id, start in INCIDENT_UPCOMING.items()
    }
