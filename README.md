# PDF Attendance Report Converter

Converts PDF attendance reports into Excel (`.xlsx`) files with **logical variations**, preserving the original structure.

---

## Architecture — 5-Layer Design

```
src/
├── detectors/          Layer 1 – Report type detection (Type A vs Type N)
├── parsers/            Layer 2 – OCR + structured extraction
├── transformers/       Layer 3 – Deterministic rule-based variations
├── validators/         Layer 4 – Post-transform sanity checks
├── renderers/          Layer 5 – Excel output generation
├── models.py           Shared data models (dataclasses)
└── ocr_utils.py        OCR pipeline (PDF → image → text → rows)
main.py                 CLI entry point
```

### Report Types

| Type | Files | Characteristics |
|------|-------|-----------------|
| **Type A** (`a_r_*`) | Detailed attendance with overtime | 10 columns: Date, Day, Location, Entry, Exit, Break, Total, 100%, 125%, 150% |
| **Type N** (`n_r_*`) | Simple monthly attendance | 5 columns: Date, Day, Entry, Exit, Total. Summary: days, hours, rate, pay |

### Transformation Rules

**Type A (Overtime):**
- Entry shifted ±30 min (clamped 06:00–10:00)
- Exit shifted ±30 min (clamped 13:00–22:00)
- Break randomly adjusted (0–1 hr)
- Total hours recalculated: (exit − entry) − break
- Overtime buckets split per Israeli labour law: ≤8h→100%, 8–10h→125%, >10h→150%
- Summary totals recomputed

**Type N (Simple):**
- Entry shifted ±20 min (clamped 06:00–10:00)
- Exit shifted ±20 min (clamped 10:00–18:00)
- Total hours recalculated: (exit − entry)
- Summary: pay = hours × rate

### Validation Checks
- `exit > entry` for every row
- Daily hours in range [0.5, 14]
- Overtime bucket sum = total hours (Type A)
- Summary totals match row sums
- Pay = hours × rate (Type N)

---

## Setup

**Prerequisites:** Python 3.10+

```bash
# Install dependencies
pip install -r requirements.txt
```

> Note: EasyOCR will download model files (~100 MB) on first run.

---

## Usage

```bash
# Convert all PDFs in input_pdfs/ → output in output_pdfs/
python main.py --input input_pdfs/ --output output_pdfs/

# Convert a single PDF
python main.py --input input_pdfs/a_r_9.pdf --output output_pdfs/

# Use a custom seed for different variations
python main.py --input input_pdfs/ --output output_pdfs/ --seed 123

# Verbose logging
python main.py --input input_pdfs/ --output output_pdfs/ -v
```

### CLI Arguments

| Argument | Description |
|----------|-------------|
| `--input`, `-i` | Path to a PDF file or directory of PDFs |
| `--output`, `-o` | Output directory for Excel files |
| `--seed`, `-s` | Random seed for reproducible transformations (default: 42) |
| `--verbose`, `-v` | Enable debug-level logging |

---

## Output

Each input PDF `filename.pdf` produces `filename_converted.xlsx` in the output directory.

Excel files preserve:
- RTL sheet direction (Hebrew)
- Original column order and headers
- Styled headers, alternating row colors, borders
- Summary blocks matching original layout
- Recalculated totals reflecting the variations

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| EasyOCR (not Tesseract) | No system-level install needed; works on image-based PDFs |
| Per-type classes (not config) | Clearer logic per report format; easy to extend |
| Seeded randomness | Same seed → same output (deterministic & reproducible) |
| Coordinate-band parsing | Robust to minor OCR position variations |
| Validation as separate layer | Can run independently; catches transformer bugs |
| Excel output (not PDF) | Easier to verify correctness; requested by user |

---

## Extending

To add a new report type:

1. Add a new `ReportType` enum value in `src/models.py`
2. Add a dataclass for its rows/summary in `src/models.py`
3. Create `src/parsers/type_x_parser.py` inheriting `BaseParser`
4. Create `src/transformers/type_x_transformer.py` inheriting `BaseTransformer`
5. Create `src/renderers/type_x_renderer.py` inheriting `BaseRenderer`
6. Update detection logic in `src/detectors/report_detector.py`
7. Wire it up in `main.py`
