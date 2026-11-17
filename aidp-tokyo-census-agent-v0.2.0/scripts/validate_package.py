#!/usr/bin/env python3
"""Validate the saved execution package locally; no network or AIDP writes."""
import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sqlite3
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compare(actual, expected, location="result"):
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and actual.keys() == expected.keys(),
                f"{location}: column mismatch")
        for key, value in expected.items():
            compare(actual[key], value, f"{location}.{key}")
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected),
                f"{location}: row count mismatch")
        for i, (left, right) in enumerate(zip(actual, expected)):
            compare(left, right, f"{location}[{i}]")
    elif isinstance(expected, float):
        require(isinstance(actual, (int, float)) and math.isclose(
            actual, expected, rel_tol=1e-10, abs_tol=1e-8), f"{location}: {actual} != {expected}")
    else:
        require(actual == expected, f"{location}: {actual!r} != {expected!r}")


def create_table(connection, name, records):
    columns = list(records[0])
    definitions = []
    for column in columns:
        value = next((r[column] for r in records if r[column] is not None), None)
        kind = "INTEGER" if isinstance(value, int) else "REAL" if isinstance(value, float) else "TEXT"
        definitions.append(f'"{column}" {kind}')
    connection.execute(f'CREATE TABLE "{name}" ({", ".join(definitions)})')
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(f'INSERT INTO "{name}" VALUES ({placeholders})',
                           [[r[c] for c in columns] for r in records])


def check_checksums():
    lines = (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    require(bool(lines), "SHA256SUMS is empty")
    seen = set()
    for line in lines:
        digest, relative = line.split("  ", 1)
        require(re.fullmatch(r"[a-f0-9]{64}", digest), "Invalid SHA-256")
        path = (ROOT / relative).resolve()
        require(path.is_relative_to(ROOT) and path.is_file(), f"Invalid checksum path: {relative}")
        require(relative not in seen, f"Duplicate checksum path: {relative}")
        seen.add(relative)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                f"File changed: {relative}")
    required = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
                if p.is_file() and ".git" not in p.relative_to(ROOT).parts
                and "__pycache__" not in p.parts and p.name != "SHA256SUMS"}
    require(required == seen, "SHA256SUMS file list differs from the package")
    return len(seen)


def validate(include_checksums=True):
    require(sys.version_info >= (3, 11), "Python 3.11+ is required")
    for path in [ROOT / "prepare_agent_data.py", Path(__file__)]:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    spec = importlib.util.spec_from_file_location("prepare_agent_data", ROOT / "prepare_agent_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    areas, neighbors, manifest = module.prepare_records([ROOT / "inputs/tokyo_changes.csv"], ROOT / "inputs")
    require(len(areas) == 61 and len(neighbors) == 305, "Unexpected record counts")
    print("PASS: 61 areas, 305 neighbors, clusters 17 / 44, saved input invariants")

    queries = {p.stem: p.read_text(encoding="utf-8").strip() for p in sorted((ROOT / "sql").glob("*.sql"))}
    expected = json.loads((ROOT / "expected_results.json").read_text(encoding="utf-8"))
    require(len(queries) == 5 and queries.keys() == expected.keys(), "Expected five SQL examples")
    counts = {}
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        create_table(connection, "census_agent_areas_v1", areas)
        create_table(connection, "census_agent_neighbors_v1", neighbors)
        for name, query in queries.items():
            sql = query.replace("blog_catalog.opendata.", "").replace("{{area_code}}", "13201")
            result = [dict(r) for r in connection.execute(sql)]
            compare(result, expected[name], name)
            counts[name] = len(result)
        for name in ("02_get_area_metrics", "04_find_similar_areas"):
            sql = queries[name].replace("blog_catalog.opendata.", "").replace("{{area_code}}", "13209")
            require(connection.execute(sql).fetchall() == [], f"{name}: Machida must be absent")
    finally:
        connection.close()
    print("PASS: all five SQL results match expected_results.json; Machida returns zero rows")

    notebook = json.loads((ROOT / "nb05_prepare_agent_tables.ipynb").read_text(encoding="utf-8"))
    cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
    sources = ["".join(c["source"]) for c in cells]
    require(len(cells) == 5, "Expected five notebook code cells")
    embedded_queries = None
    for i, (cell, source) in enumerate(zip(cells, sources)):
        require(cell["outputs"] == [] and cell["execution_count"] is None, "Notebook contains execution output")
        tree = ast.parse(source, filename=f"notebook code cell {i}")
        compile(tree, f"notebook code cell {i}", "exec")
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "QUERIES" for t in node.targets):
                embedded_queries = ast.literal_eval(node.value)
    python_source = (ROOT / "prepare_agent_data.py").read_text(encoding="utf-8").strip()
    require(any(s.strip() == python_source for s in sources), "Notebook Python differs from prepare_agent_data.py")
    require(isinstance(embedded_queries, dict), "Notebook QUERIES not found")
    compare({k: v.strip() for k, v in embedded_queries.items()}, queries, "notebook SQL")
    print("PASS: notebook syntax, clean outputs, embedded Python and five SQL files")

    for path in [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]:
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in link or link.startswith("#"):
                continue
            target = (path.parent / link.split("#", 1)[0]).resolve()
            require(target.is_relative_to(ROOT) and target.exists(), f"Broken local link: {path.name}: {link}")
    print("PASS: README and documentation local links")
    if include_checksums:
        count = check_checksums()
        print(f"PASS: SHA-256 checksums for {count} files")
    manifest["local_checks"] = {
        "python_compile": "PASS",
        "data_invariants": "PASS",
        "sql_engine": "SQLite (this local validation does not execute AIDP or Spark)",
        "five_sql_examples": "PASS",
        "sql_result_row_counts": counts,
        "machida_empty": "PASS",
        "notebook_embedded_code_and_sql": "PASS",
        "notebook_clean_outputs": "PASS",
        "documentation_local_links": "PASS",
    }
    return manifest


if __name__ == "__main__":
    try:
        validate()
    except (ValueError, OSError, KeyError, SyntaxError, sqlite3.Error) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
    print("PASS: local package validation complete; AIDP/Spark was not executed by this script")
