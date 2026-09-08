"""
Domain models, data transfer objects, enums, and validation rules.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
import re
from typing import Any, Dict, List, Set, Union
import uuid

from tracker.exceptions import ValidationError


class TransactionType(str, Enum):
    """Supported transaction directions."""

    INCOME = "INCOME"
    EXPENSE = "EXPENSE"

    @classmethod
    def from_str(cls, value: str) -> "TransactionType":
        try:
            return cls[value.strip().upper()]
        except KeyError:
            valid_values = ", ".join([t.value for t in cls])
            raise ValidationError(
                f"Invalid transaction type '{value}'. Must be one of: {valid_values}"
            )


class PaymentMethod(str, Enum):
    """Supported payment channels."""

    CASH = "Cash"
    DEBIT_CARD = "Debit Card"
    CREDIT_CARD = "Credit Card"
    BANK_TRANSFER = "Bank Transfer"

    @classmethod
    def from_str(cls, value: str) -> "PaymentMethod":
        cleaned = value.strip().title()
        for member in cls:
            if member.value.lower() == value.strip().lower():
                return member
        valid_values = ", ".join([m.value for m in cls])
        raise ValidationError(
            f"Invalid payment method '{value}'. Must be one of: {valid_values}"
        )


class DefaultCategories:
    """Predefined categories for Incomes and Expenses."""

    INCOME_CATEGORIES: Set[str] = {
        "Salary",
        "Freelance",
        "Investments",
        "Gift",
        "Other Income",
    }

    EXPENSE_CATEGORIES: Set[str] = {
        "Housing",
        "Food",
        "Transportation",
        "Utilities",
        "Healthcare",
        "Entertainment",
        "Shopping",
        "Other Expense",
    }

    @classmethod
    def get_all_defaults(cls) -> Set[str]:
        return cls.INCOME_CATEGORIES | cls.EXPENSE_CATEGORIES


def quantize_amount(val: Any) -> Decimal:
    """
    Converts input into a Decimal rounded to exactly 2 decimal places.
    Enforces positive monetary values.
    """
    if val is None:
        raise ValidationError("Amount cannot be null or empty.")

    try:
        if isinstance(val, float):
            d = Decimal(str(val))
        elif isinstance(val, Decimal):
            d = val
        else:
            d = Decimal(str(val).strip())
    except Exception as e:
        raise ValidationError(
            f"Invalid monetary amount '{val}'. Must be a valid numeric value."
        ) from e

    quantized = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if quantized <= Decimal("0.00"):
        raise ValidationError(
            f"Monetary amount must be strictly greater than 0.00. Got: ${quantized:.2f}"
        )
    return quantized


def parse_datetime(val: Union[str, datetime]) -> datetime:
    """Validates and parses ISO 8601 datetime strings or returns datetime instance."""
    if isinstance(val, datetime):
        return val
    if not isinstance(val, str) or not val.strip():
        raise ValidationError(
            "Timestamp must be a non-empty ISO 8601 string or datetime object."
        )

    val_str = val.strip()
    try:
        return datetime.fromisoformat(val_str)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            continue

    raise ValidationError(
        f"Invalid datetime format '{val}'. Expected ISO 8601 (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD)."
    )


def validate_month_format(month_str: str) -> str:
    """Validates YYYY-MM month string format."""
    pattern = r"^\d{4}-(0[1-9]|1[0-2])$"
    cleaned = month_str.strip()
    if not re.match(pattern, cleaned):
        raise ValidationError(
            f"Invalid month format '{month_str}'. Must be formatted as YYYY-MM (e.g., '2026-09')."
        )
    return cleaned


@dataclass
class Transaction:
    """Domain model for financial transaction records."""

    transaction_id: str
    timestamp: datetime
    type: TransactionType
    category: str
    amount: Decimal
    payment_method: PaymentMethod
    description: str

    def __post_init__(self) -> None:
        if not self.transaction_id or not str(self.transaction_id).strip():
            self.transaction_id = str(uuid.uuid4())

        self.timestamp = parse_datetime(self.timestamp)

        if isinstance(self.type, str):
            self.type = TransactionType.from_str(self.type)

        if not isinstance(self.category, str) or not self.category.strip():
            raise ValidationError("Transaction category cannot be empty.")
        self.category = self.category.strip().title()

        self.amount = quantize_amount(self.amount)

        if isinstance(self.payment_method, str):
            self.payment_method = PaymentMethod.from_str(self.payment_method)

        if self.description is None:
            self.description = ""
        else:
            self.description = str(self.description).strip()

    def to_dict(self) -> Dict[str, str]:
        return {
            "transaction_id": self.transaction_id,
            "timestamp": self.timestamp.isoformat(),
            "type": self.type.value,
            "category": self.category,
            "amount": f"{self.amount:.2f}",
            "payment_method": self.payment_method.value,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Transaction":
        try:
            return cls(
                transaction_id=data.get("transaction_id", "").strip(),
                timestamp=parse_datetime(data.get("timestamp", "")),
                type=TransactionType.from_str(data.get("type", "")),
                category=data.get("category", "").strip(),
                amount=quantize_amount(data.get("amount", "0")),
                payment_method=PaymentMethod.from_str(data.get("payment_method", "")),
                description=data.get("description", "").strip(),
            )
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise ValidationError(
                f"Failed to parse transaction data from storage: {e}"
            ) from e


@dataclass
class BudgetLimit:
    """Monthly category expense cap constraint."""

    category: str
    month: str
    limit_amount: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValidationError("Budget category cannot be empty.")
        self.category = self.category.strip().title()

        self.month = validate_month_format(self.month)
        self.limit_amount = quantize_amount(self.limit_amount)

    def to_dict(self) -> Dict[str, str]:
        return {
            "category": self.category,
            "month": self.month,
            "limit_amount": f"{self.limit_amount:.2f}",
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "BudgetLimit":
        try:
            return cls(
                category=data.get("category", "").strip(),
                month=data.get("month", "").strip(),
                limit_amount=quantize_amount(data.get("limit_amount", "0")),
            )
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise ValidationError(
                f"Failed to parse budget limit data from storage: {e}"
            ) from e


@dataclass
class CategorySummary:
    """Breakdown of spending or income per category."""

    category: str
    total_amount: Decimal
    percentage: Decimal


@dataclass
class FinancialSummary:
    """Aggregate financial health statistics for a specified timeframe."""

    total_income: Decimal
    total_expense: Decimal
    net_cash_flow: Decimal
    category_breakdown: List[CategorySummary]
    period_label: str


@dataclass
class BudgetAlert:
    """Evaluation result comparing expense spending against budget limit."""

    category: str
    month: str
    limit_amount: Decimal
    current_spent: Decimal
    exceeded_by: Decimal
    is_exceeded: bool
    is_warning: bool
