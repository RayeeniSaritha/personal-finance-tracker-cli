"""
Comprehensive unit test suite for Personal Finance Tracker Service.
Validates transactions, Decimal balance calculations, category breakdowns, budget limits, and storage persistence.
"""

from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest

# Ensure project root is in sys.path when script is executed directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracker.exceptions import NotFoundError, ValidationError
from tracker.models import PaymentMethod, TransactionType
from tracker.service import FinanceTrackerService


class TestFinanceTrackerService(unittest.TestCase):
    """Test suite covering end-to-end business logic in FinanceTrackerService."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_path = Path(self.temp_dir.name)
        self.service = FinanceTrackerService(data_dir=self.data_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_income_transaction(self) -> None:
        tx, alert = self.service.add_transaction(
            type_=TransactionType.INCOME,
            category="Salary",
            amount="5000.50",
            payment_method=PaymentMethod.BANK_TRANSFER,
            description="Monthly salary payment",
            timestamp="2026-09-01T10:00:00",
        )

        self.assertIsNotNone(tx.transaction_id)
        self.assertEqual(tx.type, TransactionType.INCOME)
        self.assertEqual(tx.category, "Salary")
        self.assertEqual(tx.amount, Decimal("5000.50"))
        self.assertEqual(tx.payment_method, PaymentMethod.BANK_TRANSFER)
        self.assertIsNone(alert)

        # Verify storage reload
        loaded_txs = self.service.list_transactions()
        self.assertEqual(len(loaded_txs), 1)
        self.assertEqual(loaded_txs[0].amount, Decimal("5000.50"))

    def test_add_expense_transaction(self) -> None:
        tx, alert = self.service.add_transaction(
            type_="EXPENSE",
            category="Food",
            amount=150.75,
            payment_method="Debit Card",
            description="Grocery run",
            timestamp="2026-09-02T14:30:00",
        )

        self.assertEqual(tx.type, TransactionType.EXPENSE)
        self.assertEqual(tx.category, "Food")
        self.assertEqual(tx.amount, Decimal("150.75"))
        self.assertEqual(tx.payment_method, PaymentMethod.DEBIT_CARD)
        self.assertIsNone(alert)

    def test_invalid_amount_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.add_transaction(
                type_=TransactionType.INCOME,
                category="Salary",
                amount="-100.00",
                payment_method=PaymentMethod.CASH,
            )

        with self.assertRaises(ValidationError):
            self.service.add_transaction(
                type_=TransactionType.INCOME,
                category="Salary",
                amount="invalid_number",
                payment_method=PaymentMethod.CASH,
            )

        with self.assertRaises(ValidationError):
            self.service.add_transaction(
                type_=TransactionType.INCOME,
                category="Salary",
                amount=0,
                payment_method=PaymentMethod.CASH,
            )

    def test_invalid_date_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.add_transaction(
                type_=TransactionType.INCOME,
                category="Salary",
                amount="1000.00",
                payment_method=PaymentMethod.CASH,
                timestamp="invalid-date-string",
            )

    def test_timezone_aware_and_naive_datetimes(self) -> None:
        tx1, _ = self.service.add_transaction(
            type_=TransactionType.INCOME,
            category="Salary",
            amount="1000.00",
            payment_method=PaymentMethod.BANK_TRANSFER,
            timestamp="2026-09-08T18:00:00Z",
        )
        tx2, _ = self.service.add_transaction(
            type_=TransactionType.EXPENSE,
            category="Food",
            amount="50.00",
            payment_method=PaymentMethod.CASH,
            timestamp="2026-09-08T19:00:00",
        )
        txs = self.service.list_transactions()
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].transaction_id, tx1.transaction_id)
        self.assertEqual(txs[1].transaction_id, tx2.transaction_id)

    def test_invalid_category_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.add_transaction(
                type_=TransactionType.INCOME,
                category="   ",
                amount="1000.00",
                payment_method=PaymentMethod.CASH,
            )

    def test_net_cash_flow_calculation(self) -> None:
        # Add incomes: 3000.00 + 500.25 = 3500.25
        self.service.add_transaction(
            TransactionType.INCOME, "Salary", "3000.00", PaymentMethod.BANK_TRANSFER, timestamp="2026-09-01"
        )
        self.service.add_transaction(
            TransactionType.INCOME, "Freelance", "500.25", PaymentMethod.BANK_TRANSFER, timestamp="2026-09-05"
        )

        # Add expenses: 1200.00 + 300.10 = 1500.10
        self.service.add_transaction(
            TransactionType.EXPENSE, "Housing", "1200.00", PaymentMethod.BANK_TRANSFER, timestamp="2026-09-02"
        )
        self.service.add_transaction(
            TransactionType.EXPENSE, "Food", "300.10", PaymentMethod.CREDIT_CARD, timestamp="2026-09-06"
        )

        summary = self.service.get_financial_summary(month="2026-09")
        self.assertEqual(summary.total_income, Decimal("3500.25"))
        self.assertEqual(summary.total_expense, Decimal("1500.10"))
        # Net Cash Flow = 3500.25 - 1500.10 = 2000.15
        self.assertEqual(summary.net_cash_flow, Decimal("2000.15"))

    def test_date_range_filtering(self) -> None:
        self.service.add_transaction(
            TransactionType.INCOME, "Salary", "1000.00", PaymentMethod.CASH, timestamp="2026-08-15"
        )
        self.service.add_transaction(
            TransactionType.INCOME, "Salary", "2000.00", PaymentMethod.CASH, timestamp="2026-09-10"
        )
        self.service.add_transaction(
            TransactionType.INCOME, "Salary", "3000.00", PaymentMethod.CASH, timestamp="2026-10-05"
        )

        september_txs = self.service.list_transactions(
            start_date="2026-09-01", end_date="2026-09-30"
        )
        self.assertEqual(len(september_txs), 1)
        self.assertEqual(september_txs[0].amount, Decimal("2000.00"))

    def test_category_breakdown_percentages(self) -> None:
        # Total expense = 1000.00
        self.service.add_transaction(
            TransactionType.EXPENSE, "Housing", "500.00", PaymentMethod.BANK_TRANSFER, timestamp="2026-09-01"
        )
        self.service.add_transaction(
            TransactionType.EXPENSE, "Food", "300.00", PaymentMethod.DEBIT_CARD, timestamp="2026-09-02"
        )
        self.service.add_transaction(
            TransactionType.EXPENSE, "Shopping", "200.00", PaymentMethod.CREDIT_CARD, timestamp="2026-09-03"
        )

        summary = self.service.get_financial_summary(month="2026-09")
        breakdown = {item.category: item for item in summary.category_breakdown}

        self.assertEqual(breakdown["Housing"].total_amount, Decimal("500.00"))
        self.assertEqual(breakdown["Housing"].percentage, Decimal("50.00"))

        self.assertEqual(breakdown["Food"].total_amount, Decimal("300.00"))
        self.assertEqual(breakdown["Food"].percentage, Decimal("30.00"))

        self.assertEqual(breakdown["Shopping"].total_amount, Decimal("200.00"))
        self.assertEqual(breakdown["Shopping"].percentage, Decimal("20.00"))

    def test_budget_setting_and_alert_triggering(self) -> None:
        # Set budget limit of 400.00 for Food in 2026-09
        self.service.set_category_budget("Food", "2026-09", "400.00")

        # Add expense of 300.00 (under 90% threshold, limit is 400.00) -> no alert
        _, alert1 = self.service.add_transaction(
            TransactionType.EXPENSE, "Food", "300.00", PaymentMethod.DEBIT_CARD, timestamp="2026-09-01"
        )
        self.assertIsNone(alert1)

        # Add expense of 70.00 (total = 370.00 >= 360.00 (90%)) -> warning alert
        _, alert2 = self.service.add_transaction(
            TransactionType.EXPENSE, "Food", "70.00", PaymentMethod.DEBIT_CARD, timestamp="2026-09-02"
        )
        self.assertIsNotNone(alert2)
        self.assertTrue(alert2.is_warning)
        self.assertFalse(alert2.is_exceeded)

        # Add expense of 50.00 (total = 420.00 > 400.00 limit) -> exceeded alert
        _, alert3 = self.service.add_transaction(
            TransactionType.EXPENSE, "Food", "50.00", PaymentMethod.DEBIT_CARD, timestamp="2026-09-03"
        )
        self.assertIsNotNone(alert3)
        self.assertTrue(alert3.is_exceeded)
        self.assertEqual(alert3.exceeded_by, Decimal("20.00"))

    def test_delete_transaction(self) -> None:
        tx, _ = self.service.add_transaction(
            TransactionType.INCOME, "Salary", "1500.00", PaymentMethod.BANK_TRANSFER
        )
        self.assertEqual(len(self.service.list_transactions()), 1)

        result = self.service.delete_transaction(tx.transaction_id)
        self.assertTrue(result)
        self.assertEqual(len(self.service.list_transactions()), 0)

    def test_delete_nonexistent_transaction_raises_not_found(self) -> None:
        with self.assertRaises(NotFoundError):
            self.service.delete_transaction("non-existent-uuid")

    def test_custom_category_addition(self) -> None:
        cat_name = self.service.add_custom_category("Crypto Staking", TransactionType.INCOME)
        self.assertEqual(cat_name, "Crypto Staking")

        tx, _ = self.service.add_transaction(
            TransactionType.INCOME, "Crypto Staking", "250.00", PaymentMethod.BANK_TRANSFER
        )
        self.assertEqual(tx.category, "Crypto Staking")

    def test_export_monthly_statement_markdown(self) -> None:
        self.service.add_transaction(
            TransactionType.INCOME, "Salary", "4000.00", PaymentMethod.BANK_TRANSFER, timestamp="2026-09-01"
        )
        self.service.add_transaction(
            TransactionType.EXPENSE, "Housing", "1500.00", PaymentMethod.BANK_TRANSFER, timestamp="2026-09-02"
        )

        export_path = self.service.export_monthly_statement(month="2026-09", format_type="markdown")
        self.assertTrue(export_path.exists())
        content = export_path.read_text(encoding="utf-8")
        self.assertIn("# Financial Statement - 2026-09", content)
        self.assertIn("Total Incomes:** `$4000.00`", content)
        self.assertIn("Total Expenses:** `$1500.00`", content)
        self.assertIn("Net Cash Flow:** `$2500.00`", content)

    def test_storage_reinitialization(self) -> None:
        # Create transaction and budget using first service instance
        self.service.add_transaction(
            TransactionType.INCOME, "Salary", "2000.00", PaymentMethod.BANK_TRANSFER, timestamp="2026-09-01"
        )
        self.service.set_category_budget("Food", "2026-09", "500.00")

        # Instantiate second service pointing to same directory
        new_service = FinanceTrackerService(data_dir=self.data_path)
        txs = new_service.list_transactions()
        budgets = new_service.get_all_budgets()

        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].amount, Decimal("2000.00"))
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].limit_amount, Decimal("500.00"))


if __name__ == "__main__":
    unittest.main()
