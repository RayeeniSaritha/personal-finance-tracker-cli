"""
Bank Statement Import Engine with CSV auto-parsing, intelligent category classification, and deduplication.
"""

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import io
import re
from typing import Dict, List, Optional, Tuple

from tracker.exceptions import ValidationError
from tracker.models import PaymentMethod, Transaction, TransactionType, parse_datetime, quantize_amount


@dataclass
class ImportResult:
    """Summary result of a bank statement import batch."""

    imported_count: int
    skipped_duplicates: int
    total_income: Decimal
    total_expense: Decimal
    transactions: List[Transaction]


class BankStatementImporter:
    """Parses bank statement CSV/text content, classifies categories, and removes duplicates."""

    # Keyword rules for intelligent category auto-classification
    CATEGORY_KEYWORDS = {
        "Food": [
            "walmart", "target", "aldi", "lidl", "kroger", "trader joe", "safeway", "whole foods",
            "supermarket", "groceries", "starbucks", "mcdonald", "burger", "pizza", "restaurant",
            "cafe", "coffee", "bakery", "ubereats", "doordash", "grubhub", "food"
        ],
        "Transportation": [
            "uber", "lyft", "taxi", "cab", "shell", "chevron", "exxon", "bp", "gas", "fuel",
            "train", "metro", "transit", "subway", "airline", "flight", "delta", "united", "parking"
        ],
        "Housing": ["rent", "landlord", "mortgage", "apartment", "lease", "housing", "property"],
        "Utilities": [
            "electric", "water", "power", "energy", "comcast", "verizon", "at&t", "t-mobile",
            "internet", "utility", "trash", "waste"
        ],
        "Healthcare": [
            "cvs", "walgreens", "pharmacy", "hospital", "doctor", "dentist", "medical", "clinic", "health"
        ],
        "Shopping": ["amazon", "ebay", "apple", "nike", "zara", "h&m", "store", "shop", "clothing"],
        "Entertainment": [
            "netflix", "spotify", "hulu", "disney", "cinema", "steam", "playstation", "xbox", "ticket", "concert"
        ],
        "Salary": ["salary", "payroll", "direct deposit", "employer", "wages", "paycheck"],
        "Freelance": ["stripe", "upwork", "fiverr", "paypal payout", "client", "consulting", "invoice"],
    }

    @classmethod
    def classify_category(cls, description: str, tx_type: TransactionType) -> str:
        """Auto-classifies description text into a category based on keyword matching."""
        desc_lower = description.lower()
        for cat, keywords in cls.CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in desc_lower:
                    return cat

        return "Other Income" if tx_type == TransactionType.INCOME else "Other Expense"

    @classmethod
    def parse_statement_content(
        self, content: str, existing_transactions: List[Transaction]
    ) -> ImportResult:
        """
        Parses CSV or raw text bank statement content into Transaction models.
        Performs deduplication against existing transactions.
        """
        if not content or not content.strip():
            raise ValidationError("Bank statement content is empty.")

        # Build existing lookup hash for deduplication: (timestamp.strftime('%Y-%m-%d'), amount, description.lower())
        existing_hashes = {
            (
                t.timestamp.strftime("%Y-%m-%d"),
                f"{t.amount:.2f}",
                t.description.lower().strip(),
            )
            for t in existing_transactions
        }

        imported_txs: List[Transaction] = []
        skipped_count = 0
        total_income = Decimal("0.00")
        total_expense = Decimal("0.00")

        # Try parsing as CSV
        lines = [line for line in content.splitlines() if line.strip()]
        reader = csv.reader(lines)
        rows = list(reader)

        if not rows:
            raise ValidationError("No valid data rows found in bank statement.")

        # Header detection
        header = [cell.strip().lower() for cell in rows[0]]
        has_header = any(
            h in header for h in ("date", "timestamp", "description", "payee", "amount", "deposit", "withdrawal")
        )

        data_rows = rows[1:] if has_header else rows

        # Identify column indices
        date_idx = -1
        desc_idx = -1
        amount_idx = -1
        type_idx = -1
        deposit_idx = -1
        withdrawal_idx = -1

        if has_header:
            for idx, h in enumerate(header):
                if "date" in h or "timestamp" in h:
                    date_idx = idx
                elif "desc" in h or "payee" in h or "memo" in h or "narration" in h:
                    desc_idx = idx
                elif "amount" in h:
                    amount_idx = idx
                elif "type" in h or "direction" in h:
                    type_idx = idx
                elif "deposit" in h or "credit" in h or "income" in h:
                    deposit_idx = idx
                elif "withdrawal" in h or "debit" in h or "expense" in h:
                    withdrawal_idx = idx

        for row_num, row in enumerate(data_rows, start=2 if has_header else 1):
            if not row or all(not cell.strip() for cell in row):
                continue

            try:
                # Default heuristics if header not matched
                if date_idx != -1 and date_idx < len(row):
                    raw_date = row[date_idx].strip()
                else:
                    raw_date = row[0].strip()

                if desc_idx != -1 and desc_idx < len(row):
                    description = row[desc_idx].strip()
                elif len(row) > 1:
                    description = row[1].strip()
                else:
                    description = "Bank Statement Transaction"

                # Extract amount and direction
                raw_amount_str = ""
                tx_type = TransactionType.EXPENSE

                if deposit_idx != -1 and deposit_idx < len(row) and row[deposit_idx].strip():
                    raw_amount_str = row[deposit_idx].strip()
                    tx_type = TransactionType.INCOME
                elif withdrawal_idx != -1 and withdrawal_idx < len(row) and row[withdrawal_idx].strip():
                    raw_amount_str = row[withdrawal_idx].strip()
                    tx_type = TransactionType.EXPENSE
                elif amount_idx != -1 and amount_idx < len(row):
                    raw_amount_str = row[amount_idx].strip()
                elif len(row) > 2:
                    raw_amount_str = row[2].strip()

                # Clean amount string ($ or commas)
                cleaned_amount_str = re.sub(r"[^\d.-]", "", raw_amount_str)
                if not cleaned_amount_str:
                    continue

                raw_num = float(cleaned_amount_str)
                if raw_num < 0:
                    tx_type = TransactionType.EXPENSE
                    amt = abs(raw_num)
                else:
                    amt = raw_num
                    if deposit_idx == -1 and withdrawal_idx == -1:
                        if type_idx != -1 and type_idx < len(row):
                            type_str = row[type_idx].strip().upper()
                            if "EXP" in type_str or "DR" in type_str or "DEBIT" in type_str:
                                tx_type = TransactionType.EXPENSE
                            else:
                                tx_type = TransactionType.INCOME
                        else:
                            # Positive amount in single amount column defaults to INCOME
                            tx_type = TransactionType.INCOME

                # Parse date
                dt = parse_datetime(raw_date)

                # Classify category
                category = self.classify_category(description, tx_type)

                # Quantize amount
                quant_amount = quantize_amount(amt)

                # Check deduplication
                dedup_key = (
                    dt.strftime("%Y-%m-%d"),
                    f"{quant_amount:.2f}",
                    description.lower().strip(),
                )
                if dedup_key in existing_hashes:
                    skipped_count += 1
                    continue

                tx = Transaction(
                    transaction_id="",
                    timestamp=dt,
                    type=tx_type,
                    category=category,
                    amount=quant_amount,
                    payment_method=PaymentMethod.BANK_TRANSFER,
                    description=description,
                )

                imported_txs.append(tx)
                existing_hashes.add(dedup_key)

                if tx_type == TransactionType.INCOME:
                    total_income += quant_amount
                else:
                    total_expense += quant_amount

            except Exception:
                # Ignore malformed row and continue parsing statement
                continue

        return ImportResult(
            imported_count=len(imported_txs),
            skipped_duplicates=skipped_count,
            total_income=total_income,
            total_expense=total_expense,
            transactions=imported_txs,
        )
