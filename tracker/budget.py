"""
Monthly budget limit registry and alert evaluations.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from tracker.models import BudgetAlert, BudgetLimit, quantize_amount, validate_month_format


class BudgetManager:
    """Registry for monthly category budget limits and alert evaluations."""

    def __init__(self) -> None:
        # Key: (category.lower(), month) -> BudgetLimit
        self._budgets: Dict[Tuple[str, str], BudgetLimit] = {}

    def load_budgets(self, budgets: List[BudgetLimit]) -> None:
        """Loads budget limits into the in-memory registry."""
        self._budgets.clear()
        for budget in budgets:
            key = (budget.category.lower(), budget.month)
            self._budgets[key] = budget

    def set_budget(self, category: str, month: str, limit_amount: Decimal) -> BudgetLimit:
        """Registers or updates a monthly budget cap for a category."""
        month_clean = validate_month_format(month)
        quantized_limit = quantize_amount(limit_amount)
        budget = BudgetLimit(
            category=category, month=month_clean, limit_amount=quantized_limit
        )
        key = (budget.category.lower(), budget.month)
        self._budgets[key] = budget
        return budget

    def get_budget(self, category: str, month: str) -> Optional[BudgetLimit]:
        """Retrieves budget limit for a specific category and month if exists."""
        key = (category.strip().lower(), month.strip())
        return self._budgets.get(key)

    def get_all_budgets(self) -> List[BudgetLimit]:
        """Returns all configured budget limits."""
        return list(self._budgets.values())

    def evaluate_budget(
        self, category: str, month: str, total_spent: Decimal
    ) -> Optional[BudgetAlert]:
        """
        Evaluates current category spending against configured monthly cap.
        Returns a BudgetAlert if spent amount reaches warning (>=90%) or exceeds (>=100%) limit.
        """
        budget = self.get_budget(category, month)
        if not budget:
            return None

        spent_quantized = quantize_amount(total_spent) if total_spent > Decimal("0") else Decimal("0.00")
        limit = budget.limit_amount

        is_exceeded = spent_quantized > limit
        warning_threshold = limit * Decimal("0.90")
        is_warning = spent_quantized >= warning_threshold and not is_exceeded

        if is_exceeded or is_warning:
            exceeded_by = (spent_quantized - limit) if is_exceeded else Decimal("0.00")
            return BudgetAlert(
                category=budget.category,
                month=budget.month,
                limit_amount=limit,
                current_spent=spent_quantized,
                exceeded_by=exceeded_by,
                is_exceeded=is_exceeded,
                is_warning=is_warning,
            )

        return None
