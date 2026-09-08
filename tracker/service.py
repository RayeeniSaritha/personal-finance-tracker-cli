"""
Core Business Logic Coordinator implementing financial CRUD, aggregations, net balance calculations, and report exports.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import calendar
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from tracker.budget import BudgetManager
from tracker.exceptions import NotFoundError, ValidationError
from tracker.models import (
    BudgetAlert,
    BudgetLimit,
    CategorySummary,
    DefaultCategories,
    FinancialSummary,
    PaymentMethod,
    Transaction,
    TransactionType,
    parse_datetime,
    quantize_amount,
    validate_month_format,
)
from tracker.statement_importer import BankStatementImporter, ImportResult
from tracker.storage import CSVStorageManager
import tracker.views as views


class FinanceTrackerService:
    """Core domain service for managing finance tracking operations."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is None:
            data_dir = Path("data")
        self.storage = CSVStorageManager(data_dir)
        self.budget_manager = BudgetManager()

        # Load persisted budgets
        loaded_budgets = self.storage.load_budgets()
        self.budget_manager.load_budgets(loaded_budgets)

        # Registry for user-defined custom categories: category_name.lower() -> TransactionType
        self._custom_categories: Dict[str, Tuple[str, TransactionType]] = {}

    def add_custom_category(
        self, category_name: str, type_: Union[str, TransactionType]
    ) -> str:
        """Registers a new client-defined custom category."""
        if not isinstance(category_name, str) or not category_name.strip():
            raise ValidationError("Category name cannot be empty.")

        clean_name = category_name.strip().title()
        if isinstance(type_, str):
            tx_type = TransactionType.from_str(type_)
        else:
            tx_type = type_

        self._custom_categories[clean_name.lower()] = (clean_name, tx_type)
        return clean_name

    def get_categories(
        self, type_: Optional[Union[str, TransactionType]] = None
    ) -> List[str]:
        """Returns list of all default and custom categories, optionally filtered by type."""
        tx_type = TransactionType.from_str(type_) if isinstance(type_, str) else type_

        categories = set()
        if tx_type is None or tx_type == TransactionType.INCOME:
            categories.update(DefaultCategories.INCOME_CATEGORIES)
            for _, (c_name, c_type) in self._custom_categories.items():
                if c_type == TransactionType.INCOME:
                    categories.add(c_name)

        if tx_type is None or tx_type == TransactionType.EXPENSE:
            categories.update(DefaultCategories.EXPENSE_CATEGORIES)
            for _, (c_name, c_type) in self._custom_categories.items():
                if c_type == TransactionType.EXPENSE:
                    categories.add(c_name)

        return sorted(list(categories))

    def validate_category(
        self, category: str, type_: TransactionType
    ) -> str:
        """Validates category against allowed default and custom sets. Registers dynamic category if valid format."""
        if not isinstance(category, str) or not category.strip():
            raise ValidationError("Category name cannot be empty.")

        clean_name = category.strip().title()
        allowed = self.get_categories(type_)
        if clean_name not in allowed:
            # Auto-register dynamic category for client flexibility
            self.add_custom_category(clean_name, type_)

        return clean_name

    def add_transaction(
        self,
        type_: Union[str, TransactionType],
        category: str,
        amount: Union[str, float, int, Decimal],
        payment_method: Union[str, PaymentMethod],
        description: str = "",
        timestamp: Optional[Union[str, datetime]] = None,
    ) -> Tuple[Transaction, Optional[BudgetAlert]]:
        """
        Records a new income or expense transaction.
        Checks monthly category budget limits and returns alert if threshold is triggered.
        """
        if isinstance(type_, str):
            tx_type = TransactionType.from_str(type_)
        else:
            tx_type = type_

        validated_category = self.validate_category(category, tx_type)

        if timestamp is None:
            tx_timestamp = datetime.now()
        else:
            tx_timestamp = parse_datetime(timestamp)

        transaction = Transaction(
            transaction_id="",
            timestamp=tx_timestamp,
            type=tx_type,
            category=validated_category,
            amount=quantize_amount(amount),
            payment_method=payment_method,
            description=description,
        )

        transactions = self.storage.load_transactions()
        transactions.append(transaction)
        self.storage.save_transactions(transactions)

        # Check budget alert if expense
        alert: Optional[BudgetAlert] = None
        if tx_type == TransactionType.EXPENSE:
            month_str = transaction.timestamp.strftime("%Y-%m")
            # Calculate total expense for this category and month
            category_total = Decimal("0.00")
            for t in transactions:
                if (
                    t.type == TransactionType.EXPENSE
                    and t.category.lower() == validated_category.lower()
                    and t.timestamp.strftime("%Y-%m") == month_str
                ):
                    category_total += t.amount

            alert = self.budget_manager.evaluate_budget(
                validated_category, month_str, category_total
            )

        return transaction, alert

    def get_transaction(self, transaction_id: str) -> Transaction:
        """Retrieves a single transaction by ID."""
        transactions = self.storage.load_transactions()
        for t in transactions:
            if t.transaction_id == transaction_id:
                return t
        raise NotFoundError(f"Transaction with ID '{transaction_id}' not found.")

    def list_transactions(
        self,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        type_: Optional[Union[str, TransactionType]] = None,
        category: Optional[str] = None,
    ) -> List[Transaction]:
        """Filters and lists recorded transactions sorted chronologically."""
        transactions = self.storage.load_transactions()

        start_dt = parse_datetime(start_date) if start_date else None
        end_dt = parse_datetime(end_date) if end_date else None
        filter_type = TransactionType.from_str(type_) if isinstance(type_, str) else type_
        filter_cat = category.strip().lower() if category and category.strip() else None

        filtered = []
        for t in transactions:
            if start_dt and t.timestamp < start_dt:
                continue
            if end_dt and t.timestamp > end_dt:
                continue
            if filter_type and t.type != filter_type:
                continue
            if filter_cat and t.category.lower() != filter_cat:
                continue
            filtered.append(t)

        return sorted(filtered, key=lambda x: x.timestamp)

    def delete_transaction(self, transaction_id: str) -> bool:
        """Deletes a transaction by exact ID or ID prefix."""
        clean_id = str(transaction_id).strip().lower()
        if not clean_id:
            raise ValidationError("Transaction ID for deletion cannot be empty.")

        transactions = self.storage.load_transactions()
        initial_count = len(transactions)

        filtered = [
            t for t in transactions
            if t.transaction_id.strip().lower() != clean_id
            and not t.transaction_id.strip().lower().startswith(clean_id)
        ]

        if len(filtered) == initial_count:
            raise NotFoundError(f"Transaction with ID '{transaction_id}' not found.")

        self.storage.save_transactions(filtered)
        return True

    def get_financial_summary(
        self,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        month: Optional[str] = None,
    ) -> FinancialSummary:
        """
        Computes Net Cash Flow, monthly/range aggregations, and category breakdown.
        """
        if month and month.strip().upper() != "ALL":
            clean_month = validate_month_format(month)
            year, m = map(int, clean_month.split("-"))
            _, last_day = calendar.monthrange(year, m)
            start_dt = datetime(year, m, 1, 0, 0, 0)
            end_dt = datetime(year, m, last_day, 23, 59, 59)
            period_label = f"Month: {clean_month}"
        else:
            start_dt = parse_datetime(start_date) if start_date else None
            end_dt = parse_datetime(end_date) if end_date else None
            if start_dt and end_dt:
                period_label = f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}"
            elif start_dt:
                period_label = f"From {start_dt.strftime('%Y-%m-%d')}"
            elif end_dt:
                period_label = f"Until {end_dt.strftime('%Y-%m-%d')}"
            else:
                period_label = "All Time"

        transactions = self.list_transactions(start_date=start_dt, end_date=end_dt)

        total_income = Decimal("0.00")
        total_expense = Decimal("0.00")
        category_expenses: Dict[str, Decimal] = {}

        for t in transactions:
            if t.type == TransactionType.INCOME:
                total_income += t.amount
            elif t.type == TransactionType.EXPENSE:
                total_expense += t.amount
                category_expenses[t.category] = (
                    category_expenses.get(t.category, Decimal("0.00")) + t.amount
                )

        net_cash_flow = total_income - total_expense

        # Build category breakdown sorted by amount descending
        breakdown: List[CategorySummary] = []
        for cat, cat_amount in sorted(
            category_expenses.items(), key=lambda item: item[1], reverse=True
        ):
            if total_expense > Decimal("0.00"):
                percentage = (cat_amount / total_expense) * Decimal("100.00")
                percentage = percentage.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                percentage = Decimal("0.00")

            breakdown.append(
                CategorySummary(
                    category=cat,
                    total_amount=cat_amount,
                    percentage=percentage,
                )
            )

        return FinancialSummary(
            total_income=total_income,
            total_expense=total_expense,
            net_cash_flow=net_cash_flow,
            category_breakdown=breakdown,
            period_label=period_label,
        )

    def set_category_budget(
        self, category: str, month: str, limit_amount: Union[str, float, Decimal]
    ) -> BudgetLimit:
        """Sets a monthly budget cap for a category and persists it."""
        clean_cat = self.validate_category(category, TransactionType.EXPENSE)
        budget = self.budget_manager.set_budget(clean_cat, month, Decimal(str(limit_amount)))
        all_budgets = self.budget_manager.get_all_budgets()
        self.storage.save_budgets(all_budgets)
        return budget

    def get_all_budgets(self) -> List[BudgetLimit]:
        """Returns all configured budget limits."""
        return self.budget_manager.get_all_budgets()

    def get_budget_alerts(self, month: str) -> List[BudgetAlert]:
        """Evaluates all registered budget limits for a month against recorded expenses."""
        if not month or month.strip().upper() == "ALL":
            month = datetime.now().strftime("%Y-%m")
        clean_month = validate_month_format(month)
        all_budgets = [b for b in self.get_all_budgets() if b.month == clean_month]
        if not all_budgets:
            return []

        # Get monthly expenses per category
        summary = self.get_financial_summary(month=clean_month)
        spent_map = {cat.category.lower(): cat.total_amount for cat in summary.category_breakdown}

        alerts: List[BudgetAlert] = []
        for b in all_budgets:
            spent = spent_map.get(b.category.lower(), Decimal("0.00"))
            alert = self.budget_manager.evaluate_budget(b.category, b.month, spent)
            if alert:
                alerts.append(alert)

        return alerts

    def get_budget_spending_map(self, month: str) -> Dict[Tuple[str, str], Decimal]:
        """Returns mapping of (category_lower, month) -> spent Decimal for display in tables."""
        if not month or month.strip().upper() == "ALL":
            month = datetime.now().strftime("%Y-%m")
        clean_month = validate_month_format(month)
        summary = self.get_financial_summary(month=clean_month)
        return {
            (cat.category.lower(), clean_month): cat.total_amount
            for cat in summary.category_breakdown
        }

    def export_monthly_statement(
        self,
        month: str,
        output_dir: Optional[Path] = None,
        format_type: str = "markdown",
    ) -> Path:
        """Exports a formatted monthly financial statement report file."""
        if not month or month.strip().upper() == "ALL":
            month = datetime.now().strftime("%Y-%m")
        clean_month = validate_month_format(month)
        summary = self.get_financial_summary(month=clean_month)
        transactions = self.list_transactions(start_date=f"{clean_month}-01")
        # Filter transactions matching month strictly
        monthly_txs = [t for t in transactions if t.timestamp.strftime("%Y-%m") == clean_month]
        alerts = self.get_budget_alerts(clean_month)

        if output_dir is None:
            output_dir = self.storage.data_dir / "exports"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if format_type.strip().lower() == "markdown":
            content = views.generate_markdown_statement(clean_month, summary, monthly_txs, alerts)
            file_path = output_dir / f"statement_{clean_month}.md"
        else:
            content = views.generate_plain_text_statement(clean_month, summary, monthly_txs, alerts)
            file_path = output_dir / f"statement_{clean_month}.txt"

        # Atomic write for statement export
        temp_file = file_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(content)
        temp_file.replace(file_path)

        return file_path

    def import_bank_statement(self, statement_content: str) -> ImportResult:
        """Parses and imports bank statement CSV/text content into persistent storage."""
        existing_txs = self.storage.load_transactions()
        result = BankStatementImporter.parse_statement_content(statement_content, existing_txs)

        if result.transactions:
            updated_list = existing_txs + result.transactions
            self.storage.save_transactions(updated_list)

        return result
