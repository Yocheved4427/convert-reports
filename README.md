# PDF Attendance Report Converter

Reads Israeli-format PDF attendance reports, applies deterministic rule-based
transformations, validates every row, and writes output as **Excel (`.xlsx`)**,
HTML, and PDF.

---

## Architecture

```
src/
├── ocr/                  OCR layer — pytesseract (text) + pdfplumber (words)
│   ├── pytesseract_ocr.py   PDF → Tesseract → raw text (used by classifier)
│   └── pdfplumber_ocr.py    PDF → pdfplumber → OCRRow list (used by parsers)
├── detectors/            Report-type detection
│   └── classifier.py        Keyword scoring → "TYPE_A" / "TYPE_B"
├── parsers/              Structured extraction (Template Method)
│   ├── base_parser.py       Abstract skeleton: parse() calls 4 hooks
│   ├── parser_factory.py    ParserFactory — maps type string → parser class
│   ├── type_a_parser.py     Concrete parser for Type-A (overtime) reports
│   └── type_b_parser.py     Concrete parser for Type-B (simple) reports
├── models/               Shared domain model
│   ├── attendance.py        AttendanceRow, AttendanceSummary, AttendanceReport
│   └── report_type.py       ReportType enum
├── strategies/           Transformation strategies (Strategy + Decorator)
│   ├── base_strategy.py     Abstract BaseTransformationStrategy
│   ├── type_a_strategy.py   Type-A: overtime buckets, location, date fix
│   ├── type_b_strategy.py   Type-B: hours, pay recalculation
│   └── validating_strategy_decorator.py  Decorator — validates every row
├── services/
│   └── transformation_service.py  Orchestrator — strategy-registry dispatch
├── validators/
│   └── report_validator.py  Post-transform sanity checks
├── renderers/            Output rendering
│   ├── html_renderer.py     HTML output (RTL, Hebrew)
│   ├── pdf_renderer.py      PDF output via WeasyPrint
│   └── type_a_renderer.py   Excel (xlsx) renderer for Type-A
├── transformers/         Backward-compatible thin wrappers (legacy factory path)
├── factory.py            ReportProcessorFactory (Open/Closed)
├── config.py             Pydantic-settings configuration per report type
├── exceptions.py         TransformationError, ParsingError, …
└── location_registry.py  Hebrew location alias resolution
main.py                   CLI entry point (`attendance-report` console script)
```

### Report Types

| Type | File prefix | Columns |
|------|------------|---------|
| **Type A** | `a_r_*` | Date, Day, Location, Entry, Exit, Break, Total, 100 %, 125 %, 150 % |
| **Type B / N** | `n_r_*` | Date, Day, Entry, Exit, Total — Summary: days, hours, rate, pay |

---

## Design Patterns

| Pattern | Where | Description |
|---------|-------|-------------|
| **Template Method** | `parsers/base_parser.py` | `parse()` is the fixed algorithm skeleton; subclasses implement `_is_header_line`, `_parse_row`, `_parse_summary`, `_build_report` |
| **Strategy** | `strategies/` | `BaseTransformationStrategy` defines the interface; `TypeATransformationStrategy` and `TypeBTransformationStrategy` are concrete strategies |
| **Decorator** | `strategies/validating_strategy_decorator.py` | Wraps any strategy; intercepts `transform_row()` and raises `TransformationError` on validation failure without modifying the inner strategy |
| **Factory** | `parsers/parser_factory.py`, `factory.py` | `ParserFactory` maps report-type strings to parser classes; `ReportProcessorFactory` wires parser + transformer + renderer |

---

## Transformation Rules

**Type A (Overtime)**
- Entry shifted ±30 min (clamped 06:00–10:00)
- Exit shifted ±30 min (clamped 13:00–22:00)
- Minimum gap between entry and exit enforced
- Break randomly adjusted (0–2 hr)
- Total hours recalculated: (exit − entry) − break
- Overtime buckets per Israeli labour law: ≤8 h → 100 %, 8–10 h → 125 %, >10 h → 150 %
- Day-of-week and date month/year corrected via majority-vote inference
- Location resolved through `LocationRegistry` (Hebrew alias normalisation)

**Type B / N (Simple)**
- Entry shifted ±20 min (clamped 06:00–10:00)
- Exit shifted ±20 min (clamped 10:00–18:00)
- Total hours recalculated: (exit − entry)
- Summary pay = total hours × hourly rate

---

## Prerequisites

| Dependency | Purpose |
|-----------|---------|
| **Python 3.11+** | Minimum required interpreter |
| **Tesseract OCR** | System-level OCR engine |
| **tesseract-ocr-heb** | Hebrew language data pack |
| **Poppler** (`poppler-utils`) | PDF-to-image conversion (`pdf2image`) |

### Linux / Docker
```bash
apt-get install tesseract-ocr tesseract-ocr-heb poppler-utils
```

### macOS
```bash
brew install tesseract tesseract-lang poppler
```

### Windows
Install [Tesseract for Windows](https://github.com/UB-Mannheim/tesseract/wiki) and
[Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases),
then add both to `PATH`.

---

## Setup

```bash
pip install -r requirements.txt
pip install -e .          # registers the attendance-report console script
```

---

## Usage

```bash
# Convert all PDFs in a directory
python main.py input_pdfs/ -o output_pdfs/

# Convert a single PDF
python main.py input_pdfs/a_r_9.pdf -o output_pdfs/

# Custom seed (different deterministic variation)
python main.py input_pdfs/ -o output_pdfs/ --seed 123

# Override location for Type-A reports
python main.py input_pdfs/a_r_9.pdf -o output_pdfs/ --location "גליליון"

# Verbose logging
python main.py input_pdfs/ -o output_pdfs/ -v
```

Or via the registered console script (after `pip install -e .`):

```bash
attendance-report input_pdfs/ -o output_pdfs/
attendance-report input_pdfs/a_r_9.pdf -o output_pdfs/ --seed 99 -v
```

### CLI Reference

| Argument | Short | Description |
|----------|-------|-------------|
| `INPUT` | | Path to a PDF file or directory of PDFs (positional) |
| `--output OUTPUT_DIR` | `-o` | Output directory (created if absent) |
| `--seed N` | `-s` | Random seed for reproducible transformations (default: 42) |
| `--location LOCATION` | `-l` | Workplace location override for Type-A reports |
| `--verbose` | `-v` | Enable DEBUG-level logging |

---

## Output

Each input `filename.pdf` produces up to three output files:

| File | Format | Description |
|------|--------|-------------|
| `filename.html` | HTML | RTL Hebrew table, inline CSS |
| `filename_report.pdf` | PDF | Rendered via WeasyPrint |
| `filename_converted.xlsx` | **Excel** | Primary output — RTL, styled, Hebrew headers |

Excel is the primary output format and is fully supported by the assignment.
HTML and PDF are additional output formats produced in the same pass.

---

## Docker

```bash
# Build
docker build -t attendance-report .

# Run (Linux/macOS — mount a directory from C:)
docker run --rm \
  -v /path/to/input:/data/input \
  -v /path/to/output:/data/output \
  attendance-report /data/input/a_r_9.pdf -o /data/output/
```

**Windows (PowerShell)** — Docker Desktop cannot mount non-`C:` drives directly.
Use the provided wrapper script which copies files to `C:\Temp` first:

```powershell
.\run-docker.ps1 -File a_r_9.pdf
.\run-docker.ps1                   # process all PDFs
.\run-docker.ps1 -Seed 99 -Location "אשדוד"
```

---

## Tests

```bash
pytest tests/ -v
```

164 tests covering: classifier, parsers (Template Method), validating decorator,
transformation service dispatch, strategy transforms, location registry, and OCR
dataclass clustering.

---

## Extending

To add a new report type:

1. Add a value to `ReportType` in `src/models/report_type.py`
2. Create `src/parsers/type_x_parser.py` inheriting `BaseParser` (implement 4 hooks)
3. Create `src/strategies/type_x_strategy.py` inheriting `BaseTransformationStrategy`
4. Register the strategy string in `main.py → _build_strategy_registry()`
5. Register the parser in `src/parsers/parser_factory.py`
6. Optionally add renderer and wire into `src/factory.py`

