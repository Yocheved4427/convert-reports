"""
HTML renderer – render an ``AttendanceReport`` to an HTML file.

Produces a self-contained, RTL-formatted HTML file that mirrors the PDF layout.
Works for both TYPE_A and TYPE_B reports.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path

from src.exceptions import RenderingError
from src.models.attendance import AttendanceReport
from src.renderers.base_renderer import BaseRenderer

logger = logging.getLogger(__name__)


def _esc(value: object) -> str:
    """HTML-escape a value; return empty string for None."""
    if value is None:
        return ""
    return html.escape(str(value))


class HtmlRenderer(BaseRenderer):
    """Render an ``AttendanceReport`` to a UTF-8 HTML file."""

    def render(self, report: AttendanceReport, output_path: str | Path) -> None:
        """Write an HTML file to *output_path*.

        Args:
            report:      The (transformed) attendance report.
            output_path: Destination file path (will be created/overwritten).

        Raises:
            RenderingError: on any I/O error.
        """
        output_path = Path(output_path)
        try:
            html_content = self._build_html(report)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(html_content, encoding="utf-8")
            logger.info(f"HtmlRenderer: wrote '{output_path}'")
        except OSError as exc:
            raise RenderingError(f"Failed to write HTML to '{output_path}': {exc}") from exc

    # ── Internal builders ─────────────────────────────────────────────────────

    def _build_html(self, report: AttendanceReport) -> str:
        report_type = report.report_type.value if report.report_type else "Unknown"
        title = f"דוח נוכחות – {report.month_year}"

        rows_html = self._build_rows(report)
        summary_html = self._build_summary(report)

        return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<title>{_esc(title)}</title>
<style>
  body {{ font-family: Arial, sans-serif; direction: rtl; margin: 20px; }}
  h1 {{ font-size: 1.4em; text-align: center; }}
  h2 {{ font-size: 1.1em; color: #444; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
  th {{ background: #2b4c7e; color: #fff; padding: 6px 10px; text-align: center; }}
  td {{ border: 1px solid #ccc; padding: 5px 8px; text-align: center; }}
  tr:nth-child(even) {{ background: #f2f6ff; }}
  .summary-table td {{ background: #e8f0e8; font-weight: bold; }}
</style>
</head>
<body>
<h1>{_esc(title)}</h1>
<p>שם עובד: <strong>{_esc(report.employee_name)}</strong> &nbsp; סוג דוח: {_esc(report_type)}</p>
{summary_html}
{rows_html}
</body>
</html>"""

    def _build_rows(self, report: AttendanceReport) -> str:
        rt = report.report_type
        from src.models.report_type import ReportType

        if rt == ReportType.TYPE_A:
            headers = ["תאריך", "יום", "מקום עבודה", "כניסה", "יציאה",
                       "הפסקה", 'סה"כ שעות', "שעות 100%", "שעות 125%", "שעות 150%", "הערות"]
            rows = []
            for r in report.rows:
                rows.append(
                    f"<tr>"
                    f"<td>{_esc(r.date)}</td><td>{_esc(r.day_of_week)}</td>"
                    f"<td>{_esc(r.location)}</td><td>{_esc(r.entry_time)}</td>"
                    f"<td>{_esc(r.exit_time)}</td><td>{_esc(r.break_minutes)}</td>"
                    f"<td>{_esc(r.total_hours)}</td><td>{_esc(r.regular_hours)}</td>"
                    f"<td>{_esc(r.overtime_125_hours)}</td><td>{_esc(r.overtime_150_hours)}</td>"
                    f"<td>{_esc(r.notes)}</td>"
                    f"</tr>"
                )
        else:
            headers = ["תאריך", "יום", "שעת כניסה", "שעת יציאה", 'סה"כ שעות']
            rows = []
            for r in report.rows:
                rows.append(
                    f"<tr>"
                    f"<td>{_esc(r.date)}</td><td>{_esc(r.day_of_week)}</td>"
                    f"<td>{_esc(r.entry_time)}</td><td>{_esc(r.exit_time)}</td>"
                    f"<td>{_esc(r.total_hours)}</td>"
                    f"</tr>"
                )

        header_row = "".join(f"<th>{_esc(h)}</th>" for h in headers)
        data_rows = "\n".join(rows)
        return f"<h2>שורות נוכחות</h2><table><thead><tr>{header_row}</tr></thead><tbody>{data_rows}</tbody></table>"

    def _build_summary(self, report: AttendanceReport) -> str:
        if not report.summary:
            return ""
        s = report.summary
        from src.models.report_type import ReportType
        if report.report_type == ReportType.TYPE_A:
            rows = [
                ("ימי עבודה", s.work_days),
                ('סה"כ שעות', s.total_hours),
                ("שעות 100%", s.regular_hours),
                ("שעות 125%", s.overtime_125_hours),
                ("שעות 150%", s.overtime_150_hours),
            ]
        else:
            rows = [
                ("ימי עבודה", s.work_days),
                ('סה"כ שעות', s.total_hours),
                ("מחיר לשעה", s.hourly_rate),
                ('סה"כ לתשלום', s.total_pay),
            ]
        cells = "".join(f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>" for k, v in rows)
        return f"<h2>סיכום</h2><table class='summary-table'>{cells}</table>"
