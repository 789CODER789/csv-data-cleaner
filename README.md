# CSV Data Cleaner

An original Python 3.11+ command-line tool for cleaning and validating UTF-8 CSV files. It uses only the Python standard library and is intended as a portfolio demonstration using synthetic data.

## Features

- Validates configurable required columns.
- Detects empty required fields.
- Detects duplicate records using configurable key columns.
- Trims surrounding whitespace while preserving valid values.
- Rejects structurally malformed rows safely.
- Writes `cleaned.csv`, a JSON validation report, and an HTML validation report.
- Preserves the input file and writes outputs atomically.
- Returns a non-zero exit code for invalid input, missing columns, unsafe paths, or malformed CSV syntax.

## Requirements

- Python 3.11 or newer
- No third-party packages

## Installation

1. Clone or download this repository.
2. Open a terminal in the `csv-data-cleaner` directory.
3. Confirm that Python 3.11 or newer is available:

```powershell
python --version
```

No package installation or virtual environment is required.

## Quick start

```powershell
python -m csv_data_cleaner demo\sample_input.csv `
  --output-dir demo\output `
  --required-columns record_id,name,email,status `
  --duplicate-columns record_id
```

Display all command-line options:

```powershell
python -m csv_data_cleaner --help
```

Run the tests:

```powershell
python -m unittest discover -s tests -v -f
```

## Output

- `cleaned.csv`: accepted, whitespace-trimmed records.
- `validation-report.json`: machine-readable summary and rejected-row details.
- `validation-report.html`: escaped, human-readable validation summary.

Rows are evaluated in input order. A row is rejected when it has the wrong number of columns, an empty required field, or a duplicate key. The first valid occurrence of a duplicate key is retained.

## Safety and privacy

The tool never deletes or modifies the source CSV. The included demo uses obviously fictional identifiers and `.invalid` email addresses. Do not commit real customer data, credentials, or secrets.

## Portfolio disclosure

This is an original demonstration project created for portfolio purposes. It is not a completed client order and does not represent paid work.

## License

Released under the [MIT License](LICENSE).


