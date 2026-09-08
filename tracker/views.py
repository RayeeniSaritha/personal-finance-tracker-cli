"""
CLI visual formatters, ASCII tables, alert views, and statement report generators.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from tracker.models import BudgetAlert, BudgetLimit, FinancialSummary, Transaction, TransactionType


class ASCIITable:
    """Utility class to format tabular data into visual ASCII tables."""

    @staticmethod
    def render(
        headers: List[str],
        rows: List[List[Any]],
        alignments: Optional[List[str]] = None,
    ) -> str:
        """
        Renders headers and rows into an ASCII formatted table.
        alignments: list of 'L' (Left) or 'R' (Right) alignment for each column.
        """
        if not headers:
            return ""

        num_cols = len(headers)
        if alignments is None:
            alignments = ["L"] * num_cols

        # Convert all cell values to strings
        string_rows: List[List[str]] = []
        for row in rows:
            string_rows.append([str(cell) for cell in row])

        # Compute column widths
        col_widths = [len(h) for h in headers]
        for row in string_rows:
            for i, cell in enumerate(row):
                if i < num_cols:
                    col_widths[i] = max(col_widths[i], len(cell))

        # Build separator line
        separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

        # Format row line
        def format_row(cells: List[str]) -> str:
            line_parts = []
            for i, cell in enumerate(cells):
                w = col_widths[i]
                align = alignments[i] if i < len(alignments) else "L"
                if align.upper() == "R":
                    formatted_cell = cell.rjust(w)
                else:
                    formatted_cell = cell.ljust(w)
                line_parts.append(f" {formatted_cell} ")
            return "|" + "|".join(line_parts) + "|"

        lines = [separator, format_row(headers), separator]
        if not string_rows:
            lines.append(
                "|"
                + " No records found ".center(sum(col_widths) + 3 * num_cols - 1)
                + "|"
            )
        else:
            for row in string_rows:
                lines.append(format_row(row))
        lines.append(separator)

        return "\n".join(lines)


def format_transactions_table(transactions: List[Transaction]) -> str:
    """Formats a list of transactions into an ASCII table."""
    headers = [
        "Transaction ID",
        "Timestamp",
        "Type",
        "Category",
        "Amount ($)",
        "Method",
        "Description",
    ]
    alignments = ["L", "L", "L", "L", "R", "L", "L"]

    rows = []
    for t in transactions:
        short_id = t.transaction_id[:8] + "..." if len(t.transaction_id) > 8 else t.transaction_id
        timestamp_str = t.timestamp.strftime("%Y-%m-%d %H:%M")
        amount_str = f"{t.amount:.2f}"
        rows.append(
            [
                short_id,
                timestamp_str,
                t.type.value,
                t.category,
                amount_str,
                t.payment_method.value,
                t.description,
            ]
        )

    return ASCIITable.render(headers, rows, alignments)


def format_financial_summary(summary: FinancialSummary) -> str:
    """Formats a financial summary and category breakdown into visual CLI components."""
    output = []
    output.append(f"============================================================")
    output.append(f"            FINANCIAL SUMMARY - {summary.period_label.upper()}")
    output.append(f"============================================================")
    output.append(f"  Total Incomes:     ${summary.total_income:>12.2f}")
    output.append(f"  Total Expenses:    ${summary.total_expense:>12.2f}")
    output.append(f"  ----------------------------------------------------------")
    output.append(f"  Net Cash Flow:     ${summary.net_cash_flow:>12.2f}")
    output.append(f"============================================================")
    output.append("")
    output.append("--- CATEGORY SPENDING BREAKDOWN ---")

    headers = ["Category", "Total Spent ($)", "Percentage (%)"]
    alignments = ["L", "R", "R"]
    rows = []
    for cat_sum in summary.category_breakdown:
        rows.append(
            [
                cat_sum.category,
                f"{cat_sum.total_amount:.2f}",
                f"{cat_sum.percentage:.2f}%",
            ]
        )

    output.append(ASCIITable.render(headers, rows, alignments))
    return "\n".join(output)


def format_budget_alerts(alerts: List[BudgetAlert]) -> str:
    """Renders visual warning boxes for budget cap alerts."""
    if not alerts:
        return ""

    lines = []
    for alert in alerts:
        if alert.is_exceeded:
            lines.append("┌──────────────────────────────────────────────────────────┐")
            lines.append("│ [!] BUDGET EXCEEDED ALERT                                │")
            lines.append(f"│ Category: {alert.category:<46} │")
            lines.append(f"│ Month:    {alert.month:<46} │")
            lines.append(f"│ Limit:    ${alert.limit_amount:<12.2f}  Spent: ${alert.current_spent:<12.2f} │")
            lines.append(f"│ OVER BY:  ${alert.exceeded_by:<44.2f} │")
            lines.append("└──────────────────────────────────────────────────────────┘")
        elif alert.is_warning:
            lines.append("┌──────────────────────────────────────────────────────────┐")
            lines.append("│ [?] BUDGET WARNING (>= 90% Threshold Reached)            │")
            lines.append(f"│ Category: {alert.category:<46} │")
            lines.append(f"│ Month:    {alert.month:<46} │")
            lines.append(f"│ Limit:    ${alert.limit_amount:<12.2f}  Spent: ${alert.current_spent:<12.2f} │")
            lines.append("└──────────────────────────────────────────────────────────┘")

    return "\n".join(lines)


def format_budget_limits_table(
    budgets: List[BudgetLimit], spent_map: Dict[Tuple[str, str], Decimal]
) -> str:
    """Renders configured monthly budget limits alongside current spending."""
    headers = ["Category", "Month", "Limit ($)", "Spent ($)", "Remaining ($)", "Status"]
    alignments = ["L", "L", "R", "R", "R", "L"]

    rows = []
    for b in budgets:
        spent = spent_map.get((b.category.lower(), b.month), Decimal("0.00"))
        remaining = b.limit_amount - spent
        if spent > b.limit_amount:
            status = "EXCEEDED"
        elif spent >= b.limit_amount * Decimal("0.90"):
            status = "WARNING"
        else:
            status = "OK"

        rows.append(
            [
                b.category,
                b.month,
                f"{b.limit_amount:.2f}",
                f"{spent:.2f}",
                f"{remaining:.2f}",
                status,
            ]
        )

    return ASCIITable.render(headers, rows, alignments)


def generate_markdown_statement(
    month: str,
    summary: FinancialSummary,
    transactions: List[Transaction],
    alerts: List[BudgetAlert],
) -> str:
    """Generates a clean Markdown monthly financial statement report."""
    md = []
    md.append(f"# Financial Statement - {month}")
    md.append("")
    md.append(f"**Generated Period:** `{summary.period_label}`")
    md.append("")
    md.append("## Executive Summary")
    md.append("")
    md.append(f"- **Total Incomes:** `${summary.total_income:.2f}`")
    md.append(f"- **Total Expenses:** `${summary.total_expense:.2f}`")
    md.append(f"- **Net Cash Flow:** `${summary.net_cash_flow:.2f}`")
    md.append("")

    if alerts:
        md.append("## Budget Cap Notifications")
        md.append("")
        for alert in alerts:
            if alert.is_exceeded:
                md.append(
                    f"- 🔴 **EXCEEDED:** Category **{alert.category}** exceeded budget limit of `${alert.limit_amount:.2f}` (Spent: `${alert.current_spent:.2f}`, Over: `${alert.exceeded_by:.2f}`)."
                )
            elif alert.is_warning:
                md.append(
                    f"- ⚠️ **WARNING:** Category **{alert.category}** reached 90% of budget limit `${alert.limit_amount:.2f}` (Spent: `${alert.current_spent:.2f}`)."
                )
        md.append("")

    md.append("## Category Expense Breakdown")
    md.append("")
    md.append("| Category | Total Spent ($) | Share (%) |")
    md.append("|:---|---:|---:|")
    for cat in summary.category_breakdown:
        md.append(f"| {cat.category} | ${cat.total_amount:.2f} | {cat.percentage:.2f}% |")
    md.append("")

    md.append("## Detailed Transaction Log")
    md.append("")
    md.append("| Date & Time | Type | Category | Amount ($) | Method | Description |")
    md.append("|:---|:---|:---|---:|:---|:---|")
    for t in sorted(transactions, key=lambda x: x.timestamp):
        date_str = t.timestamp.strftime("%Y-%m-%d %H:%M")
        md.append(
            f"| {date_str} | {t.type.value} | {t.category} | ${t.amount:.2f} | {t.payment_method.value} | {t.description} |"
        )
    md.append("")

    return "\n".join(md)


def generate_plain_text_statement(
    month: str,
    summary: FinancialSummary,
    transactions: List[Transaction],
    alerts: List[BudgetAlert],
) -> str:
    """Generates a plain text monthly financial statement report."""
    txt = []
    txt.append("=========================================================================")
    txt.append(f"                 MONTHLY FINANCIAL STATEMENT - {month}")
    txt.append("=========================================================================")
    txt.append(f"Period: {summary.period_label}")
    txt.append(f"Total Incomes:  ${summary.total_income:.2f}")
    txt.append(f"Total Expenses: ${summary.total_expense:.2f}")
    txt.append(f"Net Cash Flow:  ${summary.net_cash_flow:.2f}")
    txt.append("-------------------------------------------------------------------------")
    txt.append("")

    if alerts:
        txt.append("BUDGET NOTIFICATIONS:")
        for alert in alerts:
            if alert.is_exceeded:
                txt.append(
                    f" [EXCEEDED] {alert.category}: Limit ${alert.limit_amount:.2f}, Spent ${alert.current_spent:.2f} (Over ${alert.exceeded_by:.2f})"
                )
            elif alert.is_warning:
                txt.append(
                    f" [WARNING]  {alert.category}: Limit ${alert.limit_amount:.2f}, Spent ${alert.current_spent:.2f}"
                )
        txt.append("")

    txt.append("CATEGORY BREAKDOWN:")
    txt.append(format_financial_summary(summary))
    txt.append("")
    txt.append("TRANSACTION LOG:")
    txt.append(format_transactions_table(transactions))
    txt.append("=========================================================================")

    return "\n".join(txt)
