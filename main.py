"""
Main entry point – PDF attendance report converter.

Pipeline:
  PDF  →  OCR (pytesseract)  →  Classifier  →  ParserFactory
       →  Parser  →  AttendanceReport  →  TransformationService
       →  HtmlRenderer  →  PdfRenderer  →  Excel (legacy)

CLI usage (positional input):
    python main.py /path/to/input.pdf -o /path/to/output_dir
    python main.py /path/to/input_dir/ -o /path/to/output_dir --seed 123

Docker grader usage:
    docker run --rm -v $(pwd)/samples:/data attendance-report /data/sample.pdf -o /data/
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ── New architecture imports ───────────────────────────────────────────────────
from src import ocr as ocr_module
from src.detectors.classifier import classify
from src.parsers.parser_factory import ParserFactory
from src.services.transformation_service import TransformationService
from src.strategies.type_a_strategy import TypeATransformationStrategy
from src.strategies.type_b_strategy import TypeBTransformationStrategy
from src.strategies.validating_strategy_decorator import ValidatingStrategyDecorator
from src.renderers.html_renderer import HtmlRenderer
from src.renderers.pdf_renderer import PdfRenderer

# ── Legacy renderer kept for Excel output ─────────────────────────────────────
from src.factory import ReportProcessorFactory

from src.exceptions import (
    TransformationError,
    UnsupportedReportTypeError,
    ParsingError,
    RenderingError,
)
from src.validators.report_validator import ValidationError, validate_report


# ── Wired singleton registry ──────────────────────────────────────────────────

def _build_registry() -> dict:
    return {
        "TYPE_A": ValidatingStrategyDecorator(TypeATransformationStrategy()),
        "TYPE_B": ValidatingStrategyDecorator(TypeBTransformationStrategy()),
    }


# ── Pipeline ───────────────────────────────────────────────────────────────────

def process_single_pdf(
    pdf_path: Path,
    output_dir: Path,
    seed: int = 42,
    location_override: str = "",
) -> list[Path]:
    """Full pipeline for a single PDF file.  Returns list of output paths."""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info(f"Processing: {pdf_path.name}")
    logger.info("=" * 60)

    # Step 1 – OCR
    raw_text = ocr_module.extract_text(pdf_path)

    # Step 2 – Classify
    report_type_str = classify(raw_text)
    logger.info(f"  Classified as: {report_type_str}")

    # Step 3 – Parse (parser does its own structured OCR internally)
    parser_factory = ParserFactory()
    parser = parser_factory.get_parser(report_type_str)
    report = parser.parse_pdf(pdf_path)
    logger.info(f"  Parsed {len(report.rows)} rows")

    # Step 4 – Transform
    registry = _build_registry()
    transformation_service = TransformationService(strategy_registry=registry)
    transformed = transformation_service.transform(
        report, seed=seed, location_override=location_override
    )

    # Step 5 – Validate (non-fatal warning)
    try:
        validate_report(transformed)
        logger.info("  Validation: PASSED")
    except ValidationError as exc:
        logger.warning(f"  Validation: FAILED — {exc}")

    # Step 6 – Render to HTML, PDF, and Excel
    stem = pdf_path.stem
    outputs: list[Path] = []

    html_path = output_dir / f"{stem}.html"
    HtmlRenderer().render(transformed, html_path)
    outputs.append(html_path)

    pdf_out = output_dir / f"{stem}_report.pdf"
    PdfRenderer().render(transformed, pdf_out)
    actual_pdf = pdf_out if pdf_out.exists() else pdf_out.with_suffix(".html")
    if actual_pdf.exists():
        outputs.append(actual_pdf)

    # Excel (legacy renderer via ReportProcessorFactory)
    try:
        from src.models.report_type import ReportType
        rt_enum = ReportType(report_type_str)
        components = ReportProcessorFactory.get(rt_enum)
        xlsx_path = output_dir / f"{stem}_converted.xlsx"
        components.renderer.render(transformed, xlsx_path)
        outputs.append(xlsx_path)
        logger.info(f"  Excel: {xlsx_path.name}")
    except Exception as exc:
        logger.warning(f"  Excel rendering skipped: {exc}")

    for p in outputs:
        if p.exists():
            logger.info(f"  Output: {p}")

    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert PDF attendance reports to HTML/PDF/Excel."
    )
    # Positional input – required by Docker grader:
    #   docker run … attendance-report /data/sample.pdf -o /data/
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        metavar="INPUT",
        help="Path to a PDF file or directory of PDFs.",
    )
    # Legacy --input flag for backward compat
    parser.add_argument(
        "--input", "-i",
        dest="input_flag",
        default=None,
        help="Path to a PDF file or directory (alternative to positional).",
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output directory for generated files.",
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=42,
        help="Random seed for deterministic transformations (default: 42).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    parser.add_argument(
        "--location", "-l",
        default="",
        help="Workplace location override for Type-A reports.",
    )
    args = parser.parse_args()

    # ── Logging setup ────────────────────────────────────────────────
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("pytesseract").setLevel(logging.WARNING)
    logging.getLogger("pdf2image").setLevel(logging.WARNING)
    logger = logging.getLogger(__name__)

    # Resolve input path: positional takes precedence over --input flag
    raw_input = args.input or args.input_flag
    if not raw_input:
        parser.error(
            "Input path is required: supply it as a positional argument or via --input / -i"
        )
    input_path = Path(raw_input)
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

    # Process each file
    results: list[tuple[str, list[Path] | None, str]] = []
    exit_code = 0
    for pdf_file in pdf_files:
        try:
            outs = process_single_pdf(
                pdf_file, output_dir,
                seed=args.seed,
                location_override=args.location,
            )
            results.append((pdf_file.name, outs, "OK"))
        except (UnsupportedReportTypeError, ParsingError) as exc:
            logger.error(f"FAILED: {pdf_file.name} — {exc}")
            results.append((pdf_file.name, None, str(exc)))
            exit_code = 1
        except Exception as exc:
            logger.error(f"FAILED: {pdf_file.name} — {exc}", exc_info=True)
            results.append((pdf_file.name, None, str(exc)))
            exit_code = 1

    # ── Summary ──────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    for name, outs, status in results:
        if status == "OK" and outs:
            names = ", ".join(p.name for p in outs)
            logger.info(f"  OK  {name}  →  {names}")
        else:
            logger.info(f"  ERR {name}  →  {status}")
    ok_count = sum(1 for _, _, s in results if s == "OK")
    logger.info(f"  Total: {len(results)} file(s), {ok_count} succeeded")

    if ok_count > 0:
        print(f"Done. Output files are in: {output_dir}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
