# Changelog

## Unreleased

- Added an optional `closed_to_public` boolean to `Meeting` for closed or executive sessions. It defaults to `False` and is exported as `extras["cityscrapers/closed_to_public"]` in the Open Civic Data output
- `CityScrapersSpider._get_status` no longer treats `Rescheduled from <date>` in a meeting title or the `text` argument as cancelled, since that phrase marks the new, active meeting. Bare "rescheduled", "postponed" and "cancel" still return `CANCELLED`, as do `Rescheduled from X to Y` and any of these words in the description. Meeting IDs are unchanged

## [v0.10.0](https://github.com/City-Bureau/city-scrapers-core/releases/tag/v0.10.0)

- Added support for Google Cloud Storage

## [v0.9.0](https://github.com/City-Bureau/city-scrapers-core/releases/tag/v0.9.0)

- Replaced Legistar scraper from [`python-legistar-scraper`](https://github.com/opencivicdata/python-legistar-scraper) with scrapy-based implementation
