from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from csv_data_cleaner import CleanerError, clean_csv


class CsvDataCleanerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "input.csv"
        self.output = self.root / "output"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, content: str | bytes) -> None:
        if isinstance(content, bytes):
            self.source.write_bytes(content)
        else:
            self.source.write_text(content, encoding="utf-8", newline="")

    def clean(self, required=("id", "name"), duplicate=("id",)):
        return clean_csv(self.source, self.output, required, duplicate)

    def test_01_accepts_valid_utf8_csv(self) -> None:
        self.write("id,name\nSYN-001,Alpha\nSYN-002,Béta\n")
        report = self.clean()
        self.assertEqual(report["summary"]["accepted_records"], 2)

    def test_02_trims_surrounding_whitespace(self) -> None:
        self.write("id,name\n  SYN-001  ,  Alpha  \n")
        self.clean()
        self.assertEqual(self.output.joinpath("cleaned.csv").read_text(encoding="utf-8"), "id,name\nSYN-001,Alpha\n")

    def test_03_rejects_empty_required_field(self) -> None:
        self.write("id,name\nSYN-001,\nSYN-002,Beta\n")
        report = self.clean()
        self.assertEqual(report["summary"], {"input_records": 2, "accepted_records": 1, "rejected_records": 1, "duplicate_records": 0})
        self.assertIn("empty required fields: name", report["rejected_rows"][0]["reason"])

    def test_04_rejects_duplicate_key_and_keeps_first(self) -> None:
        self.write("id,name\nSYN-001,First\nSYN-001,Second\n")
        report = self.clean()
        self.assertEqual(report["summary"]["duplicate_records"], 1)
        self.assertNotIn("Second", self.output.joinpath("cleaned.csv").read_text(encoding="utf-8"))

    def test_05_supports_multiple_duplicate_columns(self) -> None:
        self.write("id,name,group\n1,Alpha,A\n1,Alpha,B\n1,Alpha,A\n")
        report = self.clean(required=("id", "name", "group"), duplicate=("id", "group"))
        self.assertEqual(report["summary"]["accepted_records"], 2)
        self.assertEqual(report["summary"]["duplicate_records"], 1)

    def test_06_rejects_wrong_column_count_safely(self) -> None:
        self.write("id,name\nSYN-001,Alpha,EXTRA\nSYN-002,Beta\n")
        report = self.clean()
        self.assertEqual(report["summary"]["rejected_records"], 1)
        self.assertIn("expected 2 columns, got 3", report["rejected_rows"][0]["reason"])

    def test_07_rejects_missing_required_column(self) -> None:
        self.write("id,label\nSYN-001,Alpha\n")
        with self.assertRaisesRegex(CleanerError, "required columns not present"):
            self.clean()
        self.assertFalse(self.output.exists())

    def test_08_rejects_empty_file_without_outputs(self) -> None:
        self.write("")
        with self.assertRaisesRegex(CleanerError, "CSV file is empty"):
            self.clean()
        self.assertFalse(self.output.exists())

    def test_09_rejects_invalid_utf8_without_outputs(self) -> None:
        self.write(b"id,name\n1,\xff\n")
        with self.assertRaisesRegex(CleanerError, "not valid UTF-8"):
            self.clean()
        self.assertFalse(self.output.exists())

    def test_10_generates_valid_json_and_html_reports(self) -> None:
        self.write("id,name\nSYN-001,Alpha\nSYN-002,\n")
        self.clean()
        parsed = json.loads(self.output.joinpath("validation-report.json").read_text(encoding="utf-8"))
        html = self.output.joinpath("validation-report.html").read_text(encoding="utf-8")
        self.assertEqual(parsed["summary"]["rejected_records"], 1)
        self.assertIn("CSV Validation Report", html)
        self.assertIn("empty required fields", html)

    def test_11_preserves_source_bytes(self) -> None:
        self.write("id,name\r\nSYN-001,Alpha\r\n")
        before = self.source.read_bytes()
        self.clean()
        self.assertEqual(self.source.read_bytes(), before)

    def test_12_cli_help_and_success_exit_codes(self) -> None:
        project = Path(__file__).resolve().parents[1]
        help_result = subprocess.run(
            [sys.executable, str(project / "csv_data_cleaner.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("--required-columns", help_result.stdout)

        self.write("id,name\nSYN-001,Alpha\n")
        run_result = subprocess.run(
            [
                sys.executable,
                str(project / "csv_data_cleaner.py"),
                str(self.source),
                "--output-dir",
                str(self.output),
                "--required-columns",
                "id,name",
                "--duplicate-columns",
                "id",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(run_result.returncode, 0, run_result.stderr)
        self.assertTrue(self.output.joinpath("cleaned.csv").is_file())

    def test_13_rejects_malformed_csv_syntax_without_outputs(self) -> None:
        self.write('id,name\nSYN-001,"unterminated\n')
        with self.assertRaisesRegex(CleanerError, "malformed CSV syntax"):
            self.clean()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()

