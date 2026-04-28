"""
Main entry point – PDF attendance report converter.

Pipeline:  PDF → OCR → Detect type → Parse → Transform → Validate → Render (Excel)

Usage:
    python main.py --input input_pdfs/ --output output_pdfs/
    python main.py --input input_pdfs/a_r_9.pdf --output output_pdfs/
    python main.py --input input_pdfs/ --output output_pdfs/ --seed 123
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ── Layer imports ──────────────────────────────────────────────────────────────
from src.detectors.report_detector import detect_report_type
from src.factory import ReportProcessorFactory
from src.validators.report_validator import ValidationError, validate_report


# ── Pipeline ───────────────────────────────────────────────────────────────────

def process_single_pdf(
    pdf_path: Path,
    output_dir: Path,
    seed: int = 42,
    location_override: str = "",
) -> Path:
    """
    Full pipeline for a single PDF file.
    Returns the path to the generated Excel file.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"{'='*60}")
    logger.info(f"Processing: {pdf_path.name}")
    logger.info(f"{'='*60}")

    # Step 1: Detect report type (OCR runs internally inside detector)
    report_type = detect_report_type(pdf_path)
    logger.info(f"  Detected type: {report_type.value}")

    # Steps 2–5: Resolve pipeline components via factory
    components = ReportProcessorFactory.get(report_type)

    # Step 2: Parse  – OCR runs internally inside parse_pdf; no duplicate I/O
    report = components.parser.parse_pdf(pdf_path)
    logger.info(f"  Parsed {len(report.rows)} data rows")

    # Step 3: Transform
    transformed = components.transformer.transform(
        report, seed=seed, location_override=location_override
    )

    # Step 4: Validate
    try:
        validate_report(transformed)
        logger.info("  Validation: PASSED")
    except ValidationError as e:
        logger.warning(f"  Validation: FAILED — {e}")
        # Continue anyway; the output is still useful for inspection

    # Step 5: Render
    output_name = pdf_path.stem + "_converted.xlsx"
    output_path = output_dir / output_name
    components.renderer.render(transformed, output_path)

    logger.info(f"  Output: {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert PDF attendance reports to Excel with logical variations."
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to a PDF file or directory of PDFs."
    )
    parser.add_argument(
        "--output", "-o", required=True,
        help="Output directory for generated Excel files."
    )
    parser.add_argument(
        "--seed", "-s", type=int, default=42,
        help="Random seed for deterministic transformations (default: 42)."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging."
    )
    parser.add_argument(
        "--location", "-l", default="",
        help="Workplace/location name to use in Type-A reports (overrides garbled OCR text)."
    )
    args = parser.parse_args()

    # ── Logging setup ──────────────────────────────────────────────
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy third-party loggers
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    logging.getLogger("easyocr").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("torch").setLevel(logging.WARNING)
    logger = logging.getLogger(__name__)

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect PDF files
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        pdf_files = [input_path]
    elif input_path.is_dir():
        pdf_files = sorted(input_path.glob("*.pdf"))
    else:
        logger.error(f"Input not found or not a PDF: {input_path}")
        sys.exit(1)

    if not pdf_files:
        logger.error(f"No PDF files found in {input_path}")
        sys.exit(1)

    logger.info(f"Found {len(pdf_files)} PDF file(s) to process")

    # Process each
    results = []
    for pdf_file in pdf_files:
        try:
            out = process_single_pdf(pdf_file, output_dir, seed=args.seed, location_override=args.location)
            results.append((pdf_file.name, out, "OK"))
        except Exception as e:
            logger.error(f"FAILED: {pdf_file.name} — {e}", exc_info=True)
            results.append((pdf_file.name, None, str(e)))

    # ── Summary ────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    for name, out, status in results:
        if out:
            logger.info(f"  ✓ {name}  →  {out.name}")
        else:
            logger.info(f"  ✗ {name}  →  {status}")
    logger.info(f"  Total: {len(results)} files, "
                f"{sum(1 for _, _, s in results if s == 'OK')} succeeded")


if __name__ == "__main__":
    main()
