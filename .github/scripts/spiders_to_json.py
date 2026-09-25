"""
Parse spider files into a JSON artifact for the downstream Airtable sync.

Runs in an unprivileged workflow (pull_request from forks is allowed).
Reads spider files as data only — never executes them. The output is
written to a fixed path so a separate, privileged workflow can pick it
up and do the actual Airtable writes.

Usage:
    CHANGED_FILES="path/to/spider1.py path/to/spider2.py" \\
        python spiders_to_json.py <output_path>

Reads the list of spider files from the CHANGED_FILES environment variable
(space-separated paths, as emitted by tj-actions/changed-files) rather than
argv, to avoid shell interpolation of PR-controlled filenames.

Output JSON shape:
    {
        "files": [
            {
                "path": "city_scrapers/spiders/foo.py",
                "spiders": [
                    {"name": "factory_spider", "agency": "...", "agency_name": "...", "is_main": false},  # noqa
                    ...
                ]
            },
            ...
        ]
    }
"""

import ast
import json
import os
import sys
from pathlib import Path


def extract_spiders(source: str) -> list[dict]:
    tree = ast.parse(source)
    spiders: list[dict] = []

    def get_str_assign(body, key):
        for stmt in body:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == key
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                return stmt.value.value
        return None

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            name = get_str_assign(node.body, "name")
            agency = get_str_assign(node.body, "agency")
            if name:
                spiders.append({"name": name, "agency": agency, "is_main": True})

        elif (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "spider_configs"
                for t in node.targets
            )
            and isinstance(node.value, (ast.List, ast.Tuple))
        ):
            for element in node.value.elts:
                if not isinstance(element, ast.Dict):
                    continue
                entry = {
                    "name": None,
                    "agency": None,
                    "agency_name": None,
                    "is_main": False,
                }
                for k, v in zip(element.keys, element.values):
                    if not (
                        isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
                    ):
                        continue
                    if k.value in ("name", "agency", "agency_name") and isinstance(
                        v.value, str
                    ):
                        entry[k.value] = v.value
                    elif k.value == "is_main" and isinstance(v.value, bool):
                        entry["is_main"] = v.value
                if entry["name"]:
                    spiders.append(entry)

    return spiders


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: extract_spiders_to_json.py <output_path>")

    output_path = Path(sys.argv[1])
    changed_files = os.environ.get("CHANGED_FILES", "").split()
    file_paths = [
        Path(p) for p in changed_files if Path(p).suffix == ".py" and Path(p).exists()
    ]

    result = {"files": []}
    for path in file_paths:
        try:
            spiders = extract_spiders(path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            print(f"[ERROR] skipping {path} - syntax error: {e}")
            continue
        print(f"[INFO] {path}: {len(spiders)} spider(s)")
        result["files"].append(
            {
                "path": str(path),
                "spiders": spiders,
            }
        )

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2))
        print(f"[INFO] Wrote {output_path}")
    except Exception as e:
        print(f"[ERROR] Failed to write output: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
