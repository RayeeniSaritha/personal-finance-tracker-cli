# Personal Finance Tracker CLI Application

An enterprise-structured, production-ready Personal Finance Tracker CLI application built entirely with the **Python Standard Library** (zero external package dependencies). Designed for high financial data precision, atomic storage integrity, category budget enforcement, and comprehensive financial analytics.

---

## 🏛️ System Architecture

```
finance_tracker/
├── tracker/
│   ├── __init__.py         # Package metadata and version definition
│   ├── exceptions.py       # Hierarchy of custom domain and storage exceptions
│   ├── models.py           # Enums, Dataclasses, Decimal precision rules & validations
│   ├── storage.py          # CSV engine with schema-versioning and atomic file I/O
│   ├── budget.py           # Monthly category budget registry & alert evaluations
│   ├── service.py          # Core business logic: CRUD, filters, net balance & report exporter
│   └── views.py            # Custom ASCII table views, alert banners, and statement formatters
├── tests/
│   ├── __init__.py         # Unit test package initialization
│   └── test_service.py     # Unittest suite for transactions, Decimal math, and budget alerts
├── main.py                 # Application entry point, interactive loop, and SIGINT shield
└── README.md               # Architecture documentation and quickstart guide
```

---

## 💡 Key Architectural Highlights

1. **Zero External Dependencies**: Implemented using pure Python standard library modules (`decimal`, `pathlib`, `csv`, `datetime`, `dataclasses`, `enum`, `unittest`, `typing`, `logging`, `signal`).
2. **Strict Financial Precision (`decimal.Decimal`)**: Floating-point representation errors are completely eliminated by enforcing `decimal.Decimal` with explicit 2-decimal place quantization (`ROUND_HALF_UP`) across all monetary calculations.
3. **Atomic File Storage & Data Integrity**: Prevents corrupted or partial CSV writes by streaming data to temporary `.tmp` files first, followed by atomic filesystem replacement (`Path.replace`).
4. **Monthly Budget Cap Enforcement & Alerts**: Monitors category spending against user-defined monthly limits. Triggers a `WARNING` banner at 90% threshold and an `EXCEEDED` alert when spending breaks the limit.
5. **Robust CLI UX & Signal Protection**: Includes graceful Ctrl+C (`SIGINT`) shutdown handling, dynamic ASCII tables, non-crashing input validation, and statement exports (Markdown / Plain Text).

---

## 🚀 Quickstart & Usage

### 1. Launch Interactive CLI Application
Navigate to the root directory and run `main.py`:

```bash
cd finance_tracker
python main.py
```

### 2. Interactive Features Overview
- **Option 1 & 2**: Record Income and Expense transactions (Income/Expense, Category, Amount, Payment Method, Description, Timestamp).
- **Option 3**: View transaction history with optional date range, type, or category filters.
- **Option 4**: Display Financial Summary (Total Income, Total Expense, Net Cash Flow, and Category Breakdown with percentage distribution).
- **Option 5**: Set category budget limits and review monthly budget spending status.
- **Option 6**: Register client-defined custom income/expense categories.
- **Option 7**: Delete transactions safely by ID or ID prefix.
- **Option 8**: Export Monthly Statements to clean Markdown (`data/exports/statement_YYYY-MM.md`) or Plain Text (`.txt`).
- **Option 9**: Graceful Exit.

---

## 🧪 Running Unit Tests

Run the comprehensive unit test suite out-of-the-box using standard Python `unittest`:

```bash
cd finance_tracker
python -m unittest discover tests
```

---

## 📄 Storage Schema

Data is stored locally under `data/`:
- **`data/transactions.csv`**: `transaction_id,timestamp,type,category,amount,payment_method,description`
- **`data/budgets.csv`**: `category,month,limit_amount`
- **`data/exports/`**: Exported Markdown and Plain Text monthly financial statements.
