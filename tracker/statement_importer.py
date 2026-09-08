"""
Bank Statement Import Engine with CSV auto-parsing, Revolut/PDF statement stream extraction,
intelligent category classification, and deduplication.
"""

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import io
import re
from typing import Dict, List, Optional, Tuple
import zlib

from tracker.exceptions import ValidationError
from tracker.models import PaymentMethod, Transaction, TransactionType, parse_datetime, quantize_amount


class PDFTextExtractor:
    """Extracts text content from PDF document streams using Python standard library zlib and CMap maps."""

    @classmethod
    def extract_text_from_bytes(cls, pdf_bytes: bytes) -> str:
        """Parses stream objects from unencrypted PDF bytes and extracts text elements with CMap support."""
        extracted: List[str] = []
        cmap: Dict[int, str] = {}
        stream_pattern = re.compile(b"stream[\r\n]+(.*?)[\r\n]+endstream", re.DOTALL)

        # Step 1: Parse CMap maps for custom encoded PDF fonts
        for match in stream_pattern.finditer(pdf_bytes):
            try:
                decomp = zlib.decompress(match.group(1))
            except Exception:
                continue

            txt = decomp.decode("latin1", errors="ignore")
            if "beginbfrange" in txt or "beginbfchar" in txt:
                for line in txt.splitlines():
                    line_clean = line.strip()
                    m1 = re.match(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", line_clean)
                    if m1:
                        s_code = int(m1.group(1), 16)
                        e_code = int(m1.group(2), 16)
                        d_code = int(m1.group(3), 16)
                        for code in range(s_code, e_code + 1):
                            cmap[code] = chr(d_code + (code - s_code))
                        continue

                    m2 = re.match(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", line_clean)
                    if m2:
                        c_code = int(m2.group(1), 16)
                        d_code = int(m2.group(2), 16)
                        cmap[c_code] = chr(d_code)

        # Step 2: Extract text elements
        for match in stream_pattern.finditer(pdf_bytes):
            stream_data = match.group(1)
            try:
                decompressed = zlib.decompress(stream_data)
            except Exception:
                decompressed = stream_data

            if not decompressed:
                continue

            tj_pattern = re.compile(b"\\((.*?)\\)\\s*Tj|\\[(.*?)\\]\\s*TJ", re.DOTALL)
            for tj_match in tj_pattern.finditer(decompressed):
                str1 = tj_match.group(1)
                str2 = tj_match.group(2)
                raw_bytes = str1 if str1 is not None else str2
                if raw_bytes:
                    clean_b = bytes([b for b in raw_bytes if b != 0])
                    if not clean_b:
                        continue
                    if cmap:
                        translated = [cmap.get(b, chr(b)) for b in clean_b]
                        clean = "".join(translated).replace("\x00", "").strip()
                    else:
                        clean = clean_b.decode("latin1", errors="ignore").replace("\x00", "").strip()

                    # Clean CID prefix artifacts
                    clean = re.sub(r"x[D-F]\s*", "", clean)
                    if clean:
                        extracted.append(clean)

        if not extracted:
            latin_str = pdf_bytes.decode("latin1", errors="ignore")
            matches = re.findall(r"\(([^()]{3,100})\)\s*Tj", latin_str)
            if matches:
                return "\n".join(matches)

        return "\n".join(extracted)


@dataclass
class ImportResult:
    """Summary result of a bank statement import batch."""

    imported_count: int
    skipped_duplicates: int
    total_income: Decimal
    total_expense: Decimal
    transactions: List[Transaction]


class BankStatementImporter:
    """Parses bank statement CSV/PDF/unstructured text, classifies categories, and removes duplicates."""

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
    def _parse_unstructured_text(
        cls, lines: List[str], existing_hashes: set
    ) -> List[Transaction]:
        """
        Parses unstructured bank statement text (e.g., Revolut, Wise, N26 PDF exports).
        Supports line stitching for PDF multi-line text streams and auto-direction classifier.
        """
        date_pattern = re.compile(
            r"(\d{1,2}-[A-Za-z]{3,9}-\d{4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})"
        )
        currency_amt_pattern = re.compile(r"([€$£₹]?\s*[\d,]+\.\d{2}|[\d,]+\.\d{2}\s*[€$£₹]?)")

        # Line stitching for PDF text streams where date and details are on split lines
        stitched_lines: List[str] = []
        current_block: List[str] = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            if date_pattern.search(line_str):
                if current_block:
                    stitched_lines.append(" ".join(current_block))
                    current_block = []
            current_block.append(line_str)

        if current_block:
            stitched_lines.append(" ".join(current_block))

        parsed_txs: List[Transaction] = []

        for line_str in stitched_lines:
            date_match = date_pattern.search(line_str)
            if not date_match:
                continue

            raw_date = date_match.group(1)
            rest_of_line = line_str[date_match.end() :].strip()

            # Find currency amounts in line
            amounts = currency_amt_pattern.findall(rest_of_line)
            if not amounts:
                continue

            first_amt = amounts[0]
            first_amt_pos = rest_of_line.find(first_amt)
            if first_amt_pos != -1:
                description = rest_of_line[:first_amt_pos].strip()
            else:
                description = rest_of_line

            if not description:
                description = "Bank Statement Transaction"

            # Clean amount figure
            cleaned_amt = re.sub(r"[^\d.-]", "", first_amt.replace(",", "."))
            if not cleaned_amt:
                continue

            try:
                amt_val = float(cleaned_amt)
            except ValueError:
                continue

            if amt_val <= 0:
                continue

            # Determine direction (Income vs Expense)
            desc_lower = description.lower()
            if any(
                kw in desc_lower
                for kw in (
                    "top-up",
                    "from ",
                    "from:",
                    "payment from",
                    "credit",
                    "deposit",
                    "refund",
                    "reverted",
                    "received",
                )
            ):
                tx_type = TransactionType.INCOME
            elif any(
                kw in desc_lower
                for kw in (
                    "to ",
                    "to:",
                    "transfer to",
                    "debit",
                    "withdrawal",
                    "payment to",
                    "fee",
                    "sent",
                )
            ):
                tx_type = TransactionType.EXPENSE
            else:
                tx_type = TransactionType.EXPENSE

            try:
                dt = parse_datetime(raw_date)
                category = cls.classify_category(description, tx_type)
                quant_amount = quantize_amount(amt_val)

                dedup_key = (
                    dt.strftime("%Y-%m-%d"),
                    f"{quant_amount:.2f}",
                    description.lower().strip(),
                )
                if dedup_key in existing_hashes:
                    continue

                existing_hashes.add(dedup_key)
                parsed_txs.append(
                    Transaction(
                        transaction_id="",
                        timestamp=dt,
                        type=tx_type,
                        category=category,
                        amount=quant_amount,
                        payment_method=PaymentMethod.BANK_TRANSFER,
                        description=description,
                    )
                )
            except Exception:
                continue

        return parsed_txs

    @classmethod
    def parse_statement_content(
        cls, content: str, existing_transactions: List[Transaction]
    ) -> ImportResult:
        """
        Parses CSV, PDF, or text bank statement content into Transaction models.
        Performs deduplication against existing transactions.
        """
        if not content or not content.strip():
            raise ValidationError("Bank statement content is empty.")

        # Unpack PDF binary or Base64 data URI if present
        if (
            content.startswith("%PDF-")
            or "data:application/pdf;base64," in content
            or content.startswith("JVBERi0")
        ):
            import base64

            try:
                if "base64," in content:
                    raw_bytes = base64.b64decode(content.split("base64,")[1])
                elif content.startswith("JVBERi0"):
                    raw_bytes = base64.b64decode(content.strip())
                else:
                    raw_bytes = content.encode("latin1")
                content = PDFTextExtractor.extract_text_from_bytes(raw_bytes)
            except Exception as e:
                raise ValidationError(f"Failed to extract text from PDF document: {e}") from e

        # Build deduplication lookup set
        existing_hashes = {
            (
                t.timestamp.strftime("%Y-%m-%d"),
                f"{t.amount:.2f}",
                t.description.lower().strip(),
            )
            for t in existing_transactions
        }

        lines = [line.strip() for line in content.splitlines() if line.strip()]

        imported_txs: List[Transaction] = []
        skipped_count = 0
        total_income = Decimal("0.00")
        total_expense = Decimal("0.00")

        # Check for multi-column structured CSV header
        reader = csv.reader(lines)
        rows = list(reader)

        has_structured_csv = False
        header_row_index = 0
        if rows:
            for r_idx, row in enumerate(rows[:5]):
                if len(row) >= 2:
                    cell_tokens = [cell.strip().lower() for cell in row]
                    if any(
                        h in ("date", "timestamp", "description", "payee", "amount", "deposit", "withdrawal", "credit", "debit")
                        for h in cell_tokens
                    ):
                        has_structured_csv = True
                        header_row_index = r_idx
                        break

        if has_structured_csv:
            header = [cell.strip().lower() for cell in rows[header_row_index]]
            data_rows = rows[header_row_index + 1:]
            date_idx, desc_idx, amount_idx, type_idx, deposit_idx, withdrawal_idx = (
                -1,
                -1,
                -1,
                -1,
                -1,
                -1,
            )

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

            for row in data_rows:
                if not row or all(not cell.strip() for cell in row):
                    continue

                try:
                    raw_date = (
                        row[date_idx].strip()
                        if date_idx != -1 and date_idx < len(row)
                        else row[0].strip()
                    )
                    description = (
                        row[desc_idx].strip()
                        if desc_idx != -1 and desc_idx < len(row)
                        else (row[1].strip() if len(row) > 1 else "Bank Statement Transaction")
                    )

                    raw_amount_str = ""
                    tx_type = TransactionType.EXPENSE

                    if (
                        deposit_idx != -1
                        and deposit_idx < len(row)
                        and row[deposit_idx].strip()
                    ):
                        raw_amount_str = row[deposit_idx].strip()
                        tx_type = TransactionType.INCOME
                    elif (
                        withdrawal_idx != -1
                        and withdrawal_idx < len(row)
                        and row[withdrawal_idx].strip()
                    ):
                        raw_amount_str = row[withdrawal_idx].strip()
                        tx_type = TransactionType.EXPENSE
                    elif amount_idx != -1 and amount_idx < len(row):
                        raw_amount_str = row[amount_idx].strip()
                    elif len(row) > 2:
                        raw_amount_str = row[2].strip()

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
                                if (
                                    "EXP" in type_str
                                    or "DR" in type_str
                                    or "DEBIT" in type_str
                                ):
                                    tx_type = TransactionType.EXPENSE
                                else:
                                    tx_type = TransactionType.INCOME
                            else:
                                tx_type = TransactionType.INCOME

                    dt = parse_datetime(raw_date)
                    category = cls.classify_category(description, tx_type)
                    quant_amount = quantize_amount(amt)

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
                    continue

        # If CSV parsing produced no records and skipped no duplicates, fallback to unstructured text statement parser
        if not imported_txs and skipped_count == 0:
            imported_txs = cls._parse_unstructured_text(lines, existing_hashes)
            for tx in imported_txs:
                if tx.type == TransactionType.INCOME:
                    total_income += tx.amount
                else:
                    total_expense += tx.amount

        if not imported_txs and skipped_count == 0:
            raise ValidationError("Could not extract valid bank statement transactions from the provided document.")

        return ImportResult(
            imported_count=len(imported_txs),
            skipped_duplicates=skipped_count,
            total_income=total_income,
            total_expense=total_expense,
            transactions=imported_txs,
        )
