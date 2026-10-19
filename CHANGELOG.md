# Changelog

## Unreleased

- Added an optional `closed_to_public` boolean to `Meeting` for closed or executive sessions. It defaults to `False` and is exported as `extras["cityscrapers/closed_to_public"]` in the Open Civic Data output
- `CityScrapersSpider._get_status` no longer treats `Rescheduled from <date>` in a meeting title or the `text` argument as cancelled, since that phrase marks the new, active meeting. Bare "rescheduled", "postponed" and "cancel" still return `CANCELLED`, as do `Rescheduled from X to Y` and any of these words in the description. Meeting IDs are unchanged
- `DiffPipeline` (and so `AzureDiffPipeline`, `S3DiffPipeline` and `GCSDiffPipeline`) now has a guard against broken scrapes. When a run scrapes zero meetings, zero upcoming meetings, or under `CITY_SCRAPERS_DIFF_GUARD_MIN_RATIO` (0.5) times the previous feed's upcoming meetings (once it had at least `CITY_SCRAPERS_DIFF_GUARD_MIN_PREVIOUS`, 3), it re-emits the previous feed unchanged instead of marking its upcoming meetings cancelled, logs an error and sends `spider_error`, so the status badge shows failing. Set `CITY_SCRAPERS_DIFF_GUARD_ENABLED = False` to turn it off. The guard is sticky: a tripped run's output is the next run's baseline, so a real mass removal keeps being held back until the guard is turned off for that spider. Healthy runs diff as before
- `DiffPipeline` now injects the previous feed only on a quiet `spider_idle` pass (engine idle, nothing scheduled or scraped since the previous idle call), so requests another `spider_idle` receiver schedules are diffed first. This adds about 5 seconds to each crawl
- `DiffPipeline` re-injects previous items with the `Scraper._process_spidermw_output` signature of newer Scrapy releases too. With Scrapy 2.19 it raised `TypeError` on idle and dropped the previous feed

## [v0.10.0](https://github.com/City-Bureau/city-scrapers-core/releases/tag/v0.10.0)

- Added support for Google Cloud Storage

## [v0.9.0](https://github.com/City-Bureau/city-scrapers-core/releases/tag/v0.9.0)

- Replaced Legistar scraper from [`python-legistar-scraper`](https://github.com/opencivicdata/python-legistar-scraper) with scrapy-based implementation
