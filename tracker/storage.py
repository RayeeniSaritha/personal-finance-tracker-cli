"""
CSV Storage Engine handling atomic file I/O, schema versioning, and auto-initialization.
"""

import csv
import logging
import os
from pathlib import Path
from typing import List, Optional

from tracker.exceptions import StorageError
from tracker.models import BudgetLimit, Transaction, UserProfile

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"
TRANSACTION_HEADERS = [
    "transaction_id",
    "timestamp",
    "type",
    "category",
    "amount",
    "payment_method",
    "description",
]
BUDGET_HEADERS = ["category", "month", "limit_amount"]
USER_HEADERS = [
    "user_id",
    "email",
    "surname",
    "first_name",
    "date_of_birth",
    "phone_number",
    "category",
    "annual_income",
    "auth_provider",
    "created_at",
]


class CSVStorageManager:
    """Manages persistent CSV storage with atomic writes and schema integrity."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.transactions_file = self.data_dir / "transactions.csv"
        self.budgets_file = self.data_dir / "budgets.csv"
        self.users_file = self.data_dir / "users.csv"
        self.init_storage()

    def init_storage(self) -> None:
        """Ensures the storage directory exists and initializes schema-versioned CSV files."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._ensure_file_with_header(
                self.transactions_file, TRANSACTION_HEADERS
            )
            self._ensure_file_with_header(self.budgets_file, BUDGET_HEADERS)
            self._ensure_file_with_header(self.users_file, USER_HEADERS)
        except Exception as e:
            raise StorageError(f"Failed to initialize storage directory: {e}") from e

    def _ensure_file_with_header(
        self, file_path: Path, expected_headers: List[str]
    ) -> None:
        if not file_path.exists() or file_path.stat().st_size == 0:
            self._atomic_write(file_path, expected_headers, [])

    def _atomic_write(
        self, file_path: Path, headers: List[str], rows: List[dict]
    ) -> None:
        """
        Writes data to a temporary file first and renames it atomically
        to prevent partial writes or data corruption.
        """
        temp_file = file_path.with_suffix(".tmp")
        try:
            with open(temp_file, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
                f.flush()
                os.fsync(f.fileno())

            temp_file.replace(file_path)
        except Exception as e:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise StorageError(
                f"Atomic file write failed for '{file_path.name}': {e}"
            ) from e

    def load_transactions(self) -> List[Transaction]:
        """Loads and parses all transactions from CSV storage."""
        if not self.transactions_file.exists():
            return []

        transactions: List[Transaction] = []
        try:
            with open(
                self.transactions_file, mode="r", newline="", encoding="utf-8"
            ) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row:
                        continue
                    transactions.append(Transaction.from_dict(row))
            return transactions
        except Exception as e:
            raise StorageError(
                f"Failed to read transactions file '{self.transactions_file}': {e}"
            ) from e

    def save_transactions(self, transactions: List[Transaction]) -> None:
        """Persists the complete list of transactions atomically."""
        rows = [t.to_dict() for t in transactions]
        self._atomic_write(self.transactions_file, TRANSACTION_HEADERS, rows)

    def load_budgets(self) -> List[BudgetLimit]:
        """Loads and parses all monthly budget caps from CSV storage."""
        if not self.budgets_file.exists():
            return []

        budgets: List[BudgetLimit] = []
        try:
            with open(self.budgets_file, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row:
                        continue
                    budgets.append(BudgetLimit.from_dict(row))
            return budgets
        except Exception as e:
            raise StorageError(
                f"Failed to read budgets file '{self.budgets_file}': {e}"
            ) from e

    def save_budgets(self, budgets: List[BudgetLimit]) -> None:
        """Persists the complete list of monthly budget caps atomically."""
        rows = [b.to_dict() for b in budgets]
        self._atomic_write(self.budgets_file, BUDGET_HEADERS, rows)

    def load_users(self) -> List[UserProfile]:
        """Loads and parses all registered user profiles from CSV storage."""
        if not self.users_file.exists():
            return []

        users: List[UserProfile] = []
        try:
            with open(self.users_file, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row or not row.get("email"):
                        continue
                    users.append(UserProfile.from_dict(row))
            return users
        except Exception as e:
            raise StorageError(
                f"Failed to read user profiles file '{self.users_file}': {e}"
            ) from e

    def save_users(self, users: List[UserProfile]) -> None:
        """Persists the complete list of user profiles atomically."""
        rows = [u.to_dict() for u in users]
        self._atomic_write(self.users_file, USER_HEADERS, rows)

    def save_user(self, user: UserProfile) -> None:
        """Upserts a single user profile in storage by email/user_id."""
        users = self.load_users()
        updated = [u for u in users if u.email.strip().lower() != user.email.strip().lower() and u.user_id != user.user_id]
        updated.append(user)
        self.save_users(updated)

    def get_user_by_email(self, email: str) -> Optional[UserProfile]:
        """Finds a registered user profile by email address."""
        if not email or not email.strip():
            return None
        clean_email = email.strip().lower()
        users = self.load_users()
        for u in users:
            if u.email.strip().lower() == clean_email:
                return u
        return None
