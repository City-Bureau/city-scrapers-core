"""
Read the parsed JSON artifact and sync spiders to Airtable.

Runs in the privileged workflow (workflow_run, base-repo context).
The JSON is treated as untrusted input — it was produced by a workflow
running on a fork PR's code. Validate before doing anything with it.
"""

import json
import re
import sys
from pathlib import Path

from decouple import config
from pyairtable import Api
from pyairtable.formulas import match

"""
AirTable field IDs.
Comment annotation: Field name / Table name
"""

# Agency name / Slug table
AGENCY_FIELD_ID = "fldM4p8WnXekL1IhH"
# Slug / Slug table
SLUG_FIELD_ID = "fld7JlLahrbFlmLMk"
# Program / Slug table
PROGRAM_FIELD_ID = "fld83rWaVrVoKBNve"
# Batch / Slug table
BATCH_FIELD_ID = "fldl8dARiHn995dCy"
# Scraper type / Slug table
SCRAPER_TYPE_FIELD_ID = "fld0Ma77mkizVIucu"
# Original Backlog Request / Slug table
BACKLOG_REQUEST_FIELD_ID = "fld8lW7mx696sICmF"

# Agency name / Backlog
BACKLOG_AGENCY_FIELD_ID = "fld30MsEoonhPTP4Z"
# programs (from Active on Docs.org (automated)) (from Agency name (from Site Issues Tracker)) / Backlog  # noqa
BACKLOG_PRIMARY_PROGRAM_LOOKUP_FIELD_ID = "fldvCFqCkYmfDYo0O"
# Program: From "Existing Agencies" / Backlog  # noqa
BACKLOG_SECONDARY_PROGRAM_LOOKUP_FIELD_ID = "fldDJcsvXPlvbK5FY"
# Scraper type / Backlog
BACKLOG_SCRAPER_TYPE_FIELD_ID = "fldGeEh3yoZMDBnC6"
# Batch / Backlog
BACKLOG_BATCH_FIELD_ID = "fldfdd7z3jt1YP3DM"

# Validation limits
MAX_FILES = 10  # PR can't touch more than this many spider files
MAX_SPIDERS_PER_FILE = 200  # spider_configs lists shouldn't go above this

# Airtable record ID format constraint
AIRTABLE_RECORD_ID = re.compile(r"^rec[A-Za-z0-9]{14}$")

# Semantic markers — the code looks for options containing these substrings,
# case-insensitively. Keeps working across cosmetic label edits like
# "Main scraper / scraper to invoice" → "Main scraper (primary)".
MAIN_SCRAPER_MARKER = "main scraper"
SUB_SCRAPER_MARKER = "subscraper"


def resolve_scraper_type_options(slugs_table) -> tuple[str, str]:
    """
    Find the exact scraper-type option values that mean 'main' and 'sub'.

    Reads the Slugs table schema, finds the Scraper Type field's allowed
    options, and matches them against the two semantic markers. Returns
    (main_value, sub_value). Warns if either can't be resolved uniquely.
    """
    schema = slugs_table.schema()
    field = next(
        (f for f in schema.fields if f.id == SCRAPER_TYPE_FIELD_ID),
        None,
    )
    if field is None:
        sys.exit(f"[ERROR] Scraper type field {SCRAPER_TYPE_FIELD_ID} not found")

    # Single-select and multi-select fields expose their options here.
    options = [choice.name for choice in field.options.choices]

    def find_single(marker: str) -> str:
        matches = [opt for opt in options if marker in opt.lower()]
        if not matches:
            print(
                f"[WARN] No Scraper Type option contains {marker!r}. "
                f"Available: {options}"
            )
            return ""
        if len(matches) == 1:
            return matches[0]
        print(
            f"[WARN] Multiple Scraper Type options contain {marker!r}: {matches}. "
            "Scraper type will not be written for affected records to avoid "
            "writing the wrong value. Fix by renaming options or narrowing the marker."
        )
        return ""

    return find_single(MAIN_SCRAPER_MARKER), find_single(SUB_SCRAPER_MARKER)


def is_valid_record_id(value) -> bool:
    return isinstance(value, str) and bool(AIRTABLE_RECORD_ID.match(value))


def required_config(key: str) -> str:
    value = config(key, default="")
    if not value.strip():
        sys.exit(f"[ERROR] Required env var {key} is missing or empty")
    return value


def validate_artifact(data) -> list[dict]:
    """
    Validate the JSON artifact's structure and return the file entries.
    """
    if not isinstance(data, dict) or "files" not in data:
        sys.exit("[ERROR] Invalid artifact: missing 'files' key")

    files = data["files"]
    if not isinstance(files, list):
        sys.exit("[ERROR] Invalid artifact: 'files' is not a list")
    if len(files) > MAX_FILES:
        sys.exit(f"[ERROR] Too many files ({len(files)} > {MAX_FILES})")

    cleaned = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        spiders = entry.get("spiders")
        if not isinstance(spiders, list):
            continue
        if len(spiders) > MAX_SPIDERS_PER_FILE:
            sys.exit(
                f"[ERROR] Too many spiders in artifact ({len(spiders)} > {MAX_SPIDERS_PER_FILE})"  # noqa
            )

        clean_spiders = []
        for s in spiders:
            if not isinstance(s, dict):
                continue
            name = s.get("name")
            agency = s.get("agency")
            agency_name = s.get("agency_name")
            is_main = s.get("is_main", False)
            if not isinstance(name, str) or not name:
                continue
            if agency is not None and not isinstance(agency, str):
                continue
            if agency_name is not None and not isinstance(agency_name, str):
                continue
            if not isinstance(is_main, bool):
                is_main = False
            clean_spiders.append(
                {
                    "name": name,
                    "agency": agency,
                    "agency_name": agency_name,
                    "is_main": is_main,
                }
            )

        cleaned.append(
            {
                "path": entry.get("path", "<unknown>"),
                "spiders": clean_spiders,
            }
        )

    return cleaned


def find_backlog_data_for_agency(
    agency_name: str, backlog_table
) -> dict[str, str | None]:
    """Look up an agency in the Backlog table and return its relevant fields.

    Returns a dict of values from the Backlog record, including the linked
    Program record ID under the key 'program_id'. If the agency isn't in
    Backlog, or the Program link is missing/invalid, 'program_id' is None.
    Other fields are returned with type-appropriate empty defaults so callers
    don't need to None-check each one.
    """
    empty = {
        "original_request": "",
        "scraper_type": "",
        "batch": "",
        "program_id": None,
    }

    backlog_records = backlog_table.all(
        formula=match({BACKLOG_AGENCY_FIELD_ID: agency_name}),
        fields=[
            BACKLOG_PRIMARY_PROGRAM_LOOKUP_FIELD_ID,
            BACKLOG_SECONDARY_PROGRAM_LOOKUP_FIELD_ID,
            BACKLOG_SCRAPER_TYPE_FIELD_ID,
            BACKLOG_BATCH_FIELD_ID,
        ],
        max_records=1,
        use_field_ids=True,
    )

    if not backlog_records:
        print(f"[INFO] No Backlog record found for agency {agency_name!r}")
        return empty

    record = backlog_records[0]
    fields = record["fields"]

    transfer_values = {
        "original_request": record["id"],
        "scraper_type": fields.get(BACKLOG_SCRAPER_TYPE_FIELD_ID, ""),
        "batch": fields.get(BACKLOG_BATCH_FIELD_ID, ""),
        "program_id": None,
    }

    # Lookup fields always return a list, even when the source link is single.
    program_links = (
        fields.get(BACKLOG_PRIMARY_PROGRAM_LOOKUP_FIELD_ID)
        or fields.get(BACKLOG_SECONDARY_PROGRAM_LOOKUP_FIELD_ID)
        or []
    )

    if not program_links:
        print(f"[INFO] Backlog record for {agency_name!r} has no linked Program")
        return transfer_values

    candidate = program_links[0]
    if not is_valid_record_id(candidate):
        print(
            f"[INFO] Backlog returned non-record-ID value for "
            f"{agency_name!r}: {candidate!r}"
        )
        return transfer_values

    transfer_values["program_id"] = candidate
    return transfer_values


def sync_to_airtable(
    spiders: list[dict],
    table,
    table_records,
    transfer_values=None,
    main_scraper_value: str = "",
    sub_scraper_value: str = "",
) -> dict:
    """
    Sync spiders to Airtable. Each spider becomes one record in the Slugs
    table, keyed on agency name (the source of truth for matching).

    For each spider:
    - If its agency already exists in the table: update the record's slug
        and overwrite every extra field (program, batch, scraper type, backlog
        request) with the values from `transfer_values`. Existing extras are
        replaced unconditionally, not merged.
    - If its agency isn't in the table: create a new record with the slug,
        agency, and the same extra fields.

    Scraper type is per-spider: if exactly one spider is marked `is_main`,
    that one gets `main_scraper_value`, the rest get `sub_scraper_value`.
    If zero or multiple spiders are marked, all get `main_scraper_value` as
    a safe default (better to over-label as main than mis-label a real main
    scraper as a sub).

    Note on agency renames:
    Because matching is keyed on agency name, renaming an existing spider's
    agency in the source produces a new record rather than updating the old
    one — the old record stays in the table with its outdated agency until
    cleaned up manually. This is intentional: the alternative (matching on
    slug and overwriting agency) risks silently reassigning a record to the
    wrong agency, which is harder to detect than a duplicate.

    Returns a summary: {'created': [...], 'updated': [...]}.
    """
    transfer_values = transfer_values or {}
    extra_fields: dict[str, str | list[str]] = {}

    program_id = transfer_values.get("program_id")
    if program_id:
        extra_fields[PROGRAM_FIELD_ID] = [program_id]

    batch = transfer_values.get("batch")
    if batch:
        extra_fields[BATCH_FIELD_ID] = batch

    original_request_id = transfer_values.get("original_request")
    if original_request_id:
        extra_fields[BACKLOG_REQUEST_FIELD_ID] = [original_request_id]

    main_scraper_type = transfer_values.get("scraper_type") or main_scraper_value
    main_count = sum(1 for s in spiders if s.get("is_main"))
    single_main = main_count == 1

    if main_scraper_type and not single_main:
        if main_count == 0:
            print(
                "[WARN] No spider marked is_main=True in this batch; "
                "all spiders will be labeled as main scraper."
            )
        else:
            print(
                f"[WARN] {main_count} spiders marked is_main=True in this batch; "
                "all spiders will be labeled as main scraper."
            )

    existing: dict[str, str] = {}
    for r in table_records:
        agency = r["fields"].get(AGENCY_FIELD_ID)
        if agency:
            existing[agency] = r["id"]

    to_create, to_update = [], []

    for spider in spiders:
        slug = spider["name"]
        agency = spider.get("agency")
        if not agency:
            # Can't key on agency if it's missing - log and move on.
            print(f"[INFO] skipping spider '{slug}' - no agency name")
            continue

        per_spider_fields = dict(extra_fields)
        if main_scraper_type:
            is_sub = single_main and not spider.get("is_main")
            value = sub_scraper_value if is_sub else main_scraper_type
            if value:
                per_spider_fields[SCRAPER_TYPE_FIELD_ID] = value

        if agency in existing:
            fields = {SLUG_FIELD_ID: slug, **per_spider_fields}
            to_update.append({"id": existing[agency], "fields": fields})
        else:
            fields = {SLUG_FIELD_ID: slug, AGENCY_FIELD_ID: agency, **per_spider_fields}
            to_create.append(fields)
            existing[agency] = ""

    created = []
    if to_create:
        created = [
            r["fields"].get(AGENCY_FIELD_ID)
            for r in table.batch_create(to_create, use_field_ids=True)
        ]

    updated = []
    if to_update:
        table.batch_update(to_update, use_field_ids=True)
        updated = [u["fields"][SLUG_FIELD_ID] for u in to_update]

    return {"created": created, "updated": updated}


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: sync_from_json.py <artifact_json_path>")

    pat = required_config("CS_AIRTABLE_PAT")
    base_id = required_config("CS_AIRTABLE_BASE_ID")
    slugs_table_name = required_config("CS_SLUGS_TABLE_ID")
    backlog_table_name = required_config("CS_BACKLOG_TABLE_ID")

    artifact_path = Path(sys.argv[1])
    data = json.loads(artifact_path.read_text())
    file_entries = validate_artifact(data)

    api = Api(pat)
    slugs_table = api.table(base_id, slugs_table_name)
    backlog_table = api.table(base_id, backlog_table_name)

    main_scraper_value, sub_scraper_value = resolve_scraper_type_options(slugs_table)

    slugs_table_records = slugs_table.all(
        fields=[SLUG_FIELD_ID, AGENCY_FIELD_ID],
        use_field_ids=True,
    )

    overall = {"created": [], "updated": []}
    for entry in file_entries:
        spiders = entry["spiders"]
        if not spiders:
            continue

        transfer_values = {}
        for spider in spiders:
            lookup_name = spider.get("agency_name") or spider.get("agency")
            if not lookup_name:
                print(
                    f"[INFO] skipping spider {spider.get('name')!r} - "
                    "no agency name for Backlog lookup"
                )
                continue

            candidate_values = find_backlog_data_for_agency(lookup_name, backlog_table)
            if candidate_values.get("original_request"):
                # Prefer a candidate with a program_id; otherwise take
                # the first match we find. Stop searching as soon as we
                # have a program_id.
                if not transfer_values or candidate_values.get("program_id"):
                    transfer_values = candidate_values
                if candidate_values.get("program_id"):
                    break
        """
        A slug record will not be created or updated if none of the spiders in the file
        have an agency that matches a Backlog record. This is a safeguard to prevent
        creating/updating records based on unverified agency names, which could lead to
        incorrect data in Airtable.
        """
        if not transfer_values.get("original_request"):
            print(
                f"[INFO] No Backlog record matched any spider in {entry['path']!r}; "
                "skipping file"
            )
            continue

        result = sync_to_airtable(
            spiders,
            slugs_table,
            slugs_table_records,
            transfer_values,
            main_scraper_value,
            sub_scraper_value,
        )
        for key in overall:
            overall[key].extend(result[key])

    print(f"[INFO] Created {len(overall['created'])}: {overall['created']}")
    print(f"[INFO] Updated {len(overall['updated'])}: {overall['updated']}")


if __name__ == "__main__":
    main()
