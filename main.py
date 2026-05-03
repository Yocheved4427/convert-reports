"""
Main entry point – PDF attendance report converter.

Pipeline
--------
PDF → OCR (pytesseract) → Classifier → ParserFactory
    → Parser → AttendanceReport → TransformationService
    → HtmlRenderer → PdfRenderer → Excel (legacy)

CLI usage
---------
Single PDF::

    attendance-report /data/sample.pdf -o /data/

Directory of PDFs::

    attendance-report /data/pdfs/ -o /data/output/ --seed 123

Docker::

    docker run --rm -v $(pwd)/samples:/data attendance-report /data/sample.pdf -o /data/
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src import ocr as ocr_module
from src.detectors.classifier import classify
from src.exceptions import ParsingError, RenderingError, UnsupportedReportTypeError
from src.factory import Container
from src.models.report_type import ReportType
from src.validators.report_validator import ValidationError


def process_single_pdf(
    pdf_path: Path,
    output_dir: Path,
    seed: int = 42,
    location_override: str = "",
) -> list[Path]:
    """Run the full conversion pipeline for a single PDF file.

    Args:
        pdf_path:          Path to the source PDF.
        output_dir:        Directory where output files will be written.
        seed:              Random seed for deterministic transformations.
        location_override: Optional workplace location override for Type-A.

    Returns:
        List of ``Path`` objects pointing to successfully created output files.

    Raises:
        UnsupportedReportTypeError: if the report type cannot be classified.
        ParsingError:               if the PDF cannot be parsed.
        RenderingError:             if rendering fails.
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Processing: %s", pdf_path.name)
    logger.info("=" * 60)

    # Step 1 – OCR: extract raw text for classification
    raw_text = ocr_module.extract_text(pdf_path)

    # Step 2 – Classify: determine report type from OCR text
    report_type_str = classify(raw_text)
    logger.info("  Classified as: %s", report_type_str)

    # Step 3 – Parse: structured OCR + domain model construction
    parser = Container.get_parser_factory().get_parser(report_type_str)
    report = parser.parse_pdf(pdf_path)
    logger.info("  Parsed %d rows", len(report.rows))

    # Step 4 – Transform: apply strategy (validation decorators are pre-wired)
    service = Container.get_transformation_service()
    transformed = service.transform(report, seed=seed, location_override=location_override)

    # Step 5 – Validate (non-fatal; emits a warning on failure)
    try:
        Container.get_report_validator().validate(transformed)
        logger.info("  Validation: PASSED")
    except ValidationError as exc:
        logger.warning("  Validation: FAILED — %s", exc)

    # Step 6 – Render to HTML and PDF
    stem = pdf_path.stem
    outputs: list[Path] = []

    html_path = output_dir / f"{stem}.html"
    Container.get_html_renderer().render(transformed, html_path)
    outputs.append(html_path)

    pdf_out = output_dir / f"{stem}_report.pdf"
    Container.get_pdf_renderer().render(transformed, pdf_out)
    actual_pdf = pdf_out if pdf_out.exists() else pdf_out.with_suffix(".html")
    if actual_pdf.exists():
        outputs.append(actual_pdf)

    # Step 7 – Excel (legacy renderer via Container)
    try:
        rt_enum = ReportType(report_type_str)
        xlsx_path = output_dir / f"{stem}_converted.xlsx"
        Container.get_excel_renderer(rt_enum).render(transformed, xlsx_path)
        outputs.append(xlsx_path)
        logger.info("  Excel: %s", xlsx_path.name)
    except Exception as exc:
        logger.warning("  Excel rendering skipped: %s", exc)

    for p in outputs:
        if p.exists():
            logger.info("  Output: %s", p)

    return outputs


def _build_arg_parser() -> argparse.ArgumentParser:
    """Construct and return the CLI argument parser.

    Returns:
        Fully configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="attendance-report",
        description=(
            "Convert PDF attendance reports to HTML / PDF / Excel.\n\n"
            "Examples:\n"
            "  attendance-report /data/sample.pdf -o /data/\n"
            "  attendance-report /data/pdfs/ -o /data/output/ --seed 99"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        metavar="INPUT",
        help="Path to a PDF file or a directory containing PDF files.",
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        metavar="OUTPUT_DIR",
        help="Directory where output files will be written (created if absent).",
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=42,
        metavar="N",
        help="Random seed for deterministic transformations (default: 42).",
    )
    parser.add_argument(
        "--location", "-l",
        default="",
        metavar="LOCATION",
        help="Workplace location override for Type-A reports (optional).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    return parser


def main() -> None:
    """CLI entry-point registered as ``attendance-report`` in pyproject.toml."""
    arg_parser = _build_arg_parser()
    args = arg_parser.parse_args()

    # ── Logging setup ─────────────────────────────────────────────────────────
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy_logger in ("pdfminer", "PIL", "pytesseract", "pdf2image"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    logger = logging.getLogger(__name__)

    # ── Resolve paths ─────────────────────────────────────────────────────────
    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Collect PDF files ─────────────────────────────────────────────────────
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        pdf_files = [input_path]
    elif input_path.is_dir():
        pdf_files = sorted(input_path.glob("*.pdf"))
    else:
        logger.error("Input path not found or not a PDF: %s", input_path)
        sys.exit(1)

    if not pdf_files:
        logger.error("No PDF files found under: %s", input_path)
        sys.exit(1)

    logger.info("Found %d PDF file(s) to process", len(pdf_files))

    # ── Process each file ─────────────────────────────────────────────────────
    results: list[tuple[str, list[Path] | None, str]] = []
    exit_code = 0
    for pdf_file in pdf_files:
        try:
            outs = process_single_pdf(
                pdf_file,
                output_dir,
                seed=args.seed,
                location_override=args.location,
            )
            results.append((pdf_file.name, outs, "OK"))
        except (UnsupportedReportTypeError, ParsingError) as exc:
            logger.error("FAILED: %s — %s", pdf_file.name, exc)
            results.append((pdf_file.name, None, str(exc)))
            exit_code = 1
        except Exception as exc:
            logger.error("FAILED: %s — %s", pdf_file.name, exc, exc_info=True)
            results.append((pdf_file.name, None, str(exc)))
            exit_code = 1

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    for name, outs, status in results:
        if status == "OK" and outs:
            names = ", ".join(p.name for p in outs)
            logger.info("  OK   %s  →  %s", name, names)
        else:
            logger.info("  ERR  %s  →  %s", name, status)

    ok_count = sum(1 for _, _, s in results if s == "OK")
    logger.info("  Total: %d file(s), %d succeeded", len(results), ok_count)

    if ok_count > 0:
        print(f"Done. Output files are in: {output_dir}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
