"""Standard-library CSV cleaning and validation tool."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


class CleanerError(Exception):
    """Raised when the input or configuration cannot be processed safely."""


@dataclass(frozen=True)
class OutputPaths:
    cleaned: Path
    json_report: Path
    html_report: Path


def _parse_column_list(value: str) -> list[str]:
    columns = [column.strip() for column in value.split(",") if column.strip()]
    if not columns:
        raise argparse.ArgumentTypeError("provide at least one comma-separated column")
    if len(columns) != len(set(columns)):
        raise argparse.ArgumentTypeError("column names must not be repeated")
    return columns


def _validate_columns(header: Sequence[str], columns: Sequence[str], label: str) -> None:
    missing = [column for column in columns if column not in header]
    if missing:
        raise CleanerError(f"{label} not present in the CSV header: {', '.join(missing)}")


def _validate_header(header: Sequence[str]) -> list[str]:
    cleaned = [column.strip() for column in header]
    if not cleaned or not any(cleaned):
        raise CleanerError("CSV header is empty")
    if any(not column for column in cleaned):
        raise CleanerError("CSV header contains an empty column name")
    if len(cleaned) != len(set(cleaned)):
        raise CleanerError("CSV header contains duplicate column names")
    return cleaned


def _safe_output_paths(input_path: Path, output_dir: Path) -> OutputPaths:
    paths = OutputPaths(
        cleaned=output_dir / "cleaned.csv",
        json_report=output_dir / "validation-report.json",
        html_report=output_dir / "validation-report.html",
    )
    source = input_path.resolve()
    if any(path.resolve() == source for path in paths.__dict__.values()):
        raise CleanerError("an output path would overwrite the source CSV")
    return paths


def _atomic_write_text(path: Path, content: str, *, newline: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline=newline,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            temporary_name = handle.name
        os.replace(temporary_name, path)
    except OSError as exc:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
        raise CleanerError(f"could not write {path}: {exc}") from exc


def _csv_text(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def _html_report(report: dict[str, object]) -> str:
    rejected = report["rejected_rows"]
    assert isinstance(rejected, list)
    rows = "".join(
        "<tr>"
        f"<td>{int(item['row_number'])}</td>"
        f"<td>{html.escape(str(item['reason']))}</td>"
        f"<td><code>{html.escape(json.dumps(item['row'], ensure_ascii=False))}</code></td>"
        "</tr>"
        for item in rejected
    )
    summary = report["summary"]
    assert isinstance(summary, dict)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CSV Validation Report</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 1000px; margin: 2rem auto; padding: 0 1rem; color: #172033; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid #ccd3df; padding: .55rem; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f7; }}
    code {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <h1>CSV Validation Report</h1>
  <ul>
    <li>Input records: {int(summary['input_records'])}</li>
    <li>Accepted records: {int(summary['accepted_records'])}</li>
    <li>Rejected records: {int(summary['rejected_records'])}</li>
    <li>Duplicate records: {int(summary['duplicate_records'])}</li>
  </ul>
  <h2>Rejected rows</h2>
  <table>
    <thead><tr><th>Source row</th><th>Reason</th><th>Row data</th></tr></thead>
    <tbody>{rows or '<tr><td colspan="3">No rejected rows.</td></tr>'}</tbody>
  </table>
</body>
</html>
"""


def clean_csv(
    input_path: Path,
    output_dir: Path,
    required_columns: Sequence[str],
    duplicate_columns: Sequence[str] | None = None,
) -> dict[str, object]:
    """Clean *input_path* and return the generated validation report."""

    input_path = Path(input_path)
    output_dir = Path(output_dir)
    if not input_path.is_file():
        raise CleanerError(f"input file does not exist: {input_path}")
    if not required_columns:
        raise CleanerError("at least one required column must be configured")

    outputs = _safe_output_paths(input_path, output_dir)
    accepted: list[list[str]] = []
    rejected: list[dict[str, object]] = []
    seen: set[tuple[str, ...]] = set()
    duplicate_count = 0

    try:
        with input_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            try:
                raw_header = next(reader)
            except StopIteration as exc:
                raise CleanerError("CSV file is empty") from exc
            header = _validate_header(raw_header)
            _validate_columns(header, required_columns, "required columns")
            keys = list(duplicate_columns) if duplicate_columns else list(header)
            _validate_columns(header, keys, "duplicate columns")
            positions = {column: index for index, column in enumerate(header)}

            for row_number, raw_row in enumerate(reader, start=2):
                cleaned_row = [value.strip() for value in raw_row]
                if len(cleaned_row) != len(header):
                    rejected.append(
                        {
                            "row_number": row_number,
                            "reason": f"malformed row: expected {len(header)} columns, got {len(cleaned_row)}",
                            "row": cleaned_row,
                        }
                    )
                    continue

                empty = [column for column in required_columns if not cleaned_row[positions[column]]]
                if empty:
                    rejected.append(
                        {
                            "row_number": row_number,
                            "reason": f"empty required fields: {', '.join(empty)}",
                            "row": dict(zip(header, cleaned_row, strict=True)),
                        }
                    )
                    continue

                duplicate_key = tuple(cleaned_row[positions[column]] for column in keys)
                if duplicate_key in seen:
                    duplicate_count += 1
                    rejected.append(
                        {
                            "row_number": row_number,
                            "reason": f"duplicate key: {', '.join(keys)}",
                            "row": dict(zip(header, cleaned_row, strict=True)),
                        }
                    )
                    continue
                seen.add(duplicate_key)
                accepted.append(cleaned_row)
    except UnicodeDecodeError as exc:
        raise CleanerError("input is not valid UTF-8") from exc
    except csv.Error as exc:
        raise CleanerError(f"malformed CSV syntax: {exc}") from exc
    except OSError as exc:
        raise CleanerError(f"could not read {input_path}: {exc}") from exc

    report: dict[str, object] = {
        "source_file": input_path.name,
        "required_columns": list(required_columns),
        "duplicate_columns": keys,
        "summary": {
            "input_records": len(accepted) + len(rejected),
            "accepted_records": len(accepted),
            "rejected_records": len(rejected),
            "duplicate_records": duplicate_count,
        },
        "rejected_rows": rejected,
    }

    _atomic_write_text(outputs.cleaned, _csv_text(header, accepted), newline="")
    _atomic_write_text(outputs.json_report, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    _atomic_write_text(outputs.html_report, _html_report(report))
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csv-data-cleaner",
        description="Clean and validate a UTF-8 CSV file without modifying the source.",
    )
    parser.add_argument("input", type=Path, help="path to the UTF-8 source CSV")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="directory for cleaned.csv and validation reports",
    )
    parser.add_argument(
        "--required-columns",
        type=_parse_column_list,
        required=True,
        help="comma-separated columns that must exist and contain values",
    )
    parser.add_argument(
        "--duplicate-columns",
        type=_parse_column_list,
        help="comma-separated duplicate key columns; defaults to the entire row",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = clean_csv(
            args.input,
            args.output_dir,
            args.required_columns,
            args.duplicate_columns,
        )
    except CleanerError as exc:
        print(f"error: {exc}", file=__import__("sys").stderr)
        return 2
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

