# Personal Finance Tracker Pro (CLI & Web Application)

An enterprise-structured, client-ready Personal Finance Tracker application built entirely with the **Python Standard Library** (zero external package dependencies). Supports both an interactive **CLI Interface** and a modern **Web Dashboard** with dark-mode glassmorphism design, real-time metrics, SVG spending charts, budget cap enforcement, and report exporting.

---

## 🏛️ Project Architecture

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
├── web/
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css   # Dark-mode glassmorphism design system & animations
│   │   └── js/
│   │       └── app.js      # Client SPA engine, REST API client, and SVG charts
│   ├── templates/
│   │   └── index.html      # Responsive HTML5 Web Dashboard
│   └── server.py           # Zero-dependency Python HTTP Server & REST API endpoints
├── tests/
│   ├── __init__.py         # Unit test package initialization
│   └── test_service.py     # Unittest suite for transactions, Decimal math, and budget alerts
├── app.py                  # Web application launcher (`python app.py`)
├── main.py                 # Application entry point (CLI & Web server)
├── README.md               # Architecture documentation and quickstart guide
└── .gitignore
```

---

## 💡 Key Highlights

1. **Zero External Dependencies**: Standard library Python 3.9+ (`decimal`, `pathlib`, `csv`, `datetime`, `dataclasses`, `http.server`, `json`, `signal`).
2. **Modern Glassmorphism Web Dashboard**: Features executive metric cards, SVG spending distribution donut charts, budget cap progress bars, real-time alert notifications, search & multi-filter transaction logs, and modal forms.
3. **Decimal Monetary Precision (`decimal.Decimal`)**: Guarantees exact currency calculations rounded to 2 decimal places with `ROUND_HALF_UP` quantization.
4. **Atomic Data Persistence**: Temporary file write-and-replace strategy prevents CSV file corruption during unexpected interruptions.
5. **Dual Interface**: Run as an interactive command-line app OR launch the Web Dashboard server.

---

## 🚀 Quickstart & Usage

### 1. Run the Web Application
Launch the web server with `python app.py` (or `python main.py web`):

```bash
cd finance_tracker
python app.py
```
Open your browser and navigate to: **`http://127.0.0.1:8000/`**

### 2. Run the Interactive CLI Application
```bash
cd finance_tracker
python main.py
```

---

## 🧪 Running Unit Tests

Run the comprehensive unit test suite out-of-the-box using standard Python `unittest`:

```bash
cd finance_tracker
python -m unittest discover tests
```

---

## 🛰️ REST API Endpoints

The built-in Python HTTP server exposes JSON REST endpoints:

- `GET /api/summary?month=YYYY-MM`: Executive metrics & category expense breakdown.
- `GET /api/transactions?month=YYYY-MM`: Filtered transaction logs.
- `POST /api/transactions`: Record income or expense transactions.
- `DELETE /api/transactions/<id>`: Delete transaction by ID.
- `GET /api/budgets?month=YYYY-MM`: Budget status, spending progress, and active alerts.
- `POST /api/budgets`: Configure category monthly budget caps.
- `GET /api/export?month=YYYY-MM&format=markdown`: Generate monthly statement file download.
