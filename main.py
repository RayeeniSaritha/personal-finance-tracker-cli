"""
Application entry point, CLI interactive loop, and global exception shield.
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import signal
import sys
from typing import List, Optional

# Ensure project root is in sys.path when main.py is run from any directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tracker.exceptions import FinanceTrackerError, ValidationError
from tracker.models import PaymentMethod, TransactionType
from tracker.service import FinanceTrackerService
import tracker.views as views


def sigint_handler(signum, frame) -> None:
    """Handles SIGINT (Ctrl+C) gracefully."""
    print("\n\n[!] Operation cancelled by user. Exiting Personal Finance Tracker safely. Goodbye!")
    sys.exit(0)


def print_banner() -> None:
    print("""
========================================================================
             PERSONAL FINANCE TRACKER CLI - ENTERPRISE v1.0
========================================================================
""")


def print_menu() -> None:
    print("""
------------------------------------------------------------------------
 MAIN MENU
------------------------------------------------------------------------
 1. Record Income
 2. Record Expense
 3. View Transactions Log (With Filters)
 4. View Financial Summary & Category Breakdown
 5. Manage Monthly Category Budgets & Alerts
 6. Add Custom Category
 7. Delete Transaction
 8. Export Monthly Financial Statement (Markdown / Text)
 9. Exit Application
------------------------------------------------------------------------
""")


def prompt_string(prompt_text: str, default: str = "") -> str:
    default_hint = f" [{default}]" if default else ""
    user_input = input(f"{prompt_text}{default_hint}: ").strip()
    return user_input if user_input else default


def prompt_choice(prompt_text: str, choices: List[str]) -> str:
    print(prompt_text)
    for idx, choice in enumerate(choices, 1):
        print(f"   {idx}. {choice}")
    while True:
        raw = input("Select an option (number): ").strip()
        if raw.isdigit():
            val = int(raw)
            if 1 <= val <= len(choices):
                return choices[val - 1]
        print(f" Invalid choice. Please enter a number between 1 and {len(choices)}.")


def prompt_date(prompt_text: str, allow_blank: bool = True) -> Optional[str]:
    today_str = datetime.now().strftime("%Y-%m-%d")
    default_hint = " (YYYY-MM-DD) [Leave blank for Today]" if allow_blank else " (YYYY-MM-DD)"
    raw = input(f"{prompt_text}{default_hint}: ").strip()
    if not raw:
        return today_str if allow_blank else None
    return raw


def prompt_month(prompt_text: str) -> str:
    current_month = datetime.now().strftime("%Y-%m")
    raw = input(f"{prompt_text} [Default: {current_month}]: ").strip()
    return raw if raw else current_month


def record_transaction_flow(service: FinanceTrackerService, tx_type: TransactionType) -> None:
    type_name = "Income" if tx_type == TransactionType.INCOME else "Expense"
    print(f"\n--- RECORD NEW {type_name.upper()} ---")

    categories = service.get_categories(tx_type)
    categories.append("Other / Add Custom Category...")

    selected_cat = prompt_choice("Select Category:", categories)
    if selected_cat == "Other / Add Custom Category...":
        custom_cat = prompt_string("Enter new category name")
        category = service.add_custom_category(custom_cat, tx_type)
    else:
        category = selected_cat

    amount_str = prompt_string("Enter amount ($)")
    payment_methods = [pm.value for pm in PaymentMethod]
    payment_method = prompt_choice("Select Payment Method:", payment_methods)
    description = prompt_string("Enter description (optional)", default="")
    timestamp = prompt_date("Enter date", allow_blank=True)

    tx, alert = service.add_transaction(
        type_=tx_type,
        category=category,
        amount=amount_str,
        payment_method=payment_method,
        description=description,
        timestamp=timestamp,
    )

    print(f"\n[✓] {type_name} recorded successfully!")
    print(f"    Transaction ID: {tx.transaction_id}")
    print(f"    Amount: ${tx.amount:.2f} | Category: {tx.category}")

    if alert:
        print("\n" + views.format_budget_alerts([alert]))


def view_transactions_flow(service: FinanceTrackerService) -> None:
    print("\n--- TRANSACTIONS LOG ---")
    apply_filter = prompt_string("Apply filters? (y/n)", default="n").lower() == "y"

    start_date = None
    end_date = None
    tx_type = None
    category = None

    if apply_filter:
        use_type = prompt_string("Filter by type? (income/expense/all)", default="all").lower()
        if use_type in ("income", "expense"):
            tx_type = TransactionType.from_str(use_type)

        use_dates = prompt_string("Filter by date range? (y/n)", default="n").lower() == "y"
        if use_dates:
            start_date = prompt_date("Start date", allow_blank=False)
            end_date = prompt_date("End date", allow_blank=False)

        cat_filter = prompt_string("Filter by Category (leave blank for all)", default="")
        category = cat_filter if cat_filter else None

    txs = service.list_transactions(
        start_date=start_date, end_date=end_date, type_=tx_type, category=category
    )
    print("\n" + views.format_transactions_table(txs))


def view_summary_flow(service: FinanceTrackerService) -> None:
    print("\n--- FINANCIAL SUMMARY & ANALYTICS ---")
    choice = prompt_choice(
        "Select Timeframe:", ["Current Month", "Specify Month (YYYY-MM)", "All Time"]
    )

    if choice == "Current Month":
        month_str = datetime.now().strftime("%Y-%m")
        summary = service.get_financial_summary(month=month_str)
    elif choice == "Specify Month (YYYY-MM)":
        month_str = prompt_month("Enter month")
        summary = service.get_financial_summary(month=month_str)
    else:
        summary = service.get_financial_summary()

    print("\n" + views.format_financial_summary(summary))


def manage_budgets_flow(service: FinanceTrackerService) -> None:
    print("\n--- MONTHLY CATEGORY BUDGETS ---")
    action = prompt_choice("Select Action:", ["View Budget Status", "Set/Update Category Budget Cap"])

    month_str = prompt_month("Enter month for budget status")

    if action == "Set/Update Category Budget Cap":
        expense_cats = service.get_categories(TransactionType.EXPENSE)
        category = prompt_choice("Select Category for Budget Limit:", expense_cats)
        limit_str = prompt_string("Enter Monthly Budget Limit ($)")
        b = service.set_category_budget(category, month_str, limit_str)
        print(f"\n[✓] Budget limit of ${b.limit_amount:.2f} set for category '{b.category}' in {b.month}.")

    # Display Budget Status Table & Alerts
    budgets = [b for b in service.get_all_budgets() if b.month == month_str]
    spent_map = service.get_budget_spending_map(month_str)
    print("\n" + views.format_budget_limits_table(budgets, spent_map))

    alerts = service.get_budget_alerts(month_str)
    if alerts:
        print("\n" + views.format_budget_alerts(alerts))


def add_custom_category_flow(service: FinanceTrackerService) -> None:
    print("\n--- ADD CUSTOM CATEGORY ---")
    cat_type = prompt_choice("Select Category Type:", ["EXPENSE", "INCOME"])
    tx_type = TransactionType.from_str(cat_type)
    name = prompt_string("Enter new Category Name")
    added = service.add_custom_category(name, tx_type)
    print(f"\n[✓] Custom category '{added}' added under {tx_type.value}!")


def delete_transaction_flow(service: FinanceTrackerService) -> None:
    print("\n--- DELETE TRANSACTION ---")
    tx_id = prompt_string("Enter Transaction ID (or UUID prefix)")
    if not tx_id:
        print("[!] Deletion cancelled.")
        return

    # Attempt to locate by partial prefix if full ID not entered
    all_txs = service.list_transactions()
    matches = [t for t in all_txs if t.transaction_id.startswith(tx_id)]

    if not matches:
        print(f"[!] No transaction found matching ID '{tx_id}'.")
        return
    elif len(matches) > 1:
        print("[!] Multiple transactions matched prefix. Please enter full ID.")
        return

    target = matches[0]
    confirm = prompt_string(
        f"Delete transaction {target.transaction_id[:8]} (${target.amount:.2f} - {target.category})? (y/n)",
        default="n",
    )
    if confirm.lower() == "y":
        service.delete_transaction(target.transaction_id)
        print("[✓] Transaction deleted successfully.")
    else:
        print("[!] Deletion cancelled.")


def export_statement_flow(service: FinanceTrackerService) -> None:
    print("\n--- EXPORT MONTHLY FINANCIAL STATEMENT ---")
    month_str = prompt_month("Enter month for statement export")
    format_choice = prompt_choice("Select Export Format:", ["Markdown (.md)", "Plain Text (.txt)"])

    fmt = "markdown" if "Markdown" in format_choice else "text"
    file_path = service.export_monthly_statement(month=month_str, format_type=fmt)
    print(f"\n[✓] Statement exported successfully to:\n    {file_path.absolute()}")


def main() -> None:
    signal.signal(signal.SIGINT, sigint_handler)
    print_banner()

    # Initialize finance service
    service = FinanceTrackerService(data_dir=Path("data"))

    while True:
        try:
            print_menu()
            choice = input("Enter option (1-9): ").strip()

            if choice == "1":
                record_transaction_flow(service, TransactionType.INCOME)
            elif choice == "2":
                record_transaction_flow(service, TransactionType.EXPENSE)
            elif choice == "3":
                view_transactions_flow(service)
            elif choice == "4":
                view_summary_flow(service)
            elif choice == "5":
                manage_budgets_flow(service)
            elif choice == "6":
                add_custom_category_flow(service)
            elif choice == "7":
                delete_transaction_flow(service)
            elif choice == "8":
                export_statement_flow(service)
            elif choice == "9":
                print("\nThank you for using Personal Finance Tracker. Goodbye!")
                sys.exit(0)
            else:
                print("\n[!] Invalid selection. Please enter a menu number between 1 and 9.")

        except FinanceTrackerError as e:
            print(f"\n[!] ERROR: {e.message}")
        except Exception as e:
            print(f"\n[!] UNEXPECTED ERROR: {e}")


if __name__ == "__main__":
    main()
