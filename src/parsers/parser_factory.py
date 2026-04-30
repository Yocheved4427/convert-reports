"""
ParserFactory – maps report type tokens to concrete parser instances.

Usage::

    factory = ParserFactory()
    parser = factory.get_parser("TYPE_A")
    report = parser.parse_pdf(pdf_path)

Adding a new report type requires only:
  1. Implementing a concrete ``BaseParser`` subclass.
  2. Adding one entry to ``PARSER_REGISTRY``.
  3. Zero changes to ``ParserFactory`` or any calling code.
"""

from __future__ import annotations

from src.exceptions import UnsupportedReportTypeError
from src.parsers.base_parser import BaseParser
from src.parsers.type_a_parser import TypeAParser
from src.parsers.type_b_parser import TypeBParser

# Default registry – maps string keys to parser instances.
PARSER_REGISTRY: dict[str, BaseParser] = {
    "TYPE_A": TypeAParser(),
    "TYPE_B": TypeBParser(),
}


class ParserFactory:
    """Return the concrete parser for a given report type token.

    Args:
        registry: Optional custom registry (uses ``PARSER_REGISTRY`` by default).
    """

    def __init__(self, registry: dict[str, BaseParser] | None = None) -> None:
        self.registry = registry or PARSER_REGISTRY

    def get_parser(self, report_type: object) -> BaseParser:
        """Return the parser registered for *report_type*.

        Args:
            report_type: A ``ReportType`` enum value or a plain string such as
                         ``"TYPE_A"`` or ``"TYPE_B"``.

        Returns:
            The registered ``BaseParser`` instance.

        Raises:
            UnsupportedReportTypeError: if the type is not in the registry.
        """
        key = report_type.value if hasattr(report_type, "value") else str(report_type)
        try:
            return self.registry[key]
        except KeyError:
            raise UnsupportedReportTypeError(
                f"Unsupported report type: {key!r}.  "
                f"Known types: {list(self.registry)}"
            )
