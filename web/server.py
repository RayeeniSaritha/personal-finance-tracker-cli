"""
Zero-dependency Python HTTP Web Server exposing REST APIs and static web assets.
"""

from datetime import datetime
from decimal import Decimal
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import urllib.parse

from tracker.exceptions import FinanceTrackerError, NotFoundError, ValidationError
from tracker.models import PaymentMethod, TransactionType
from tracker.service import FinanceTrackerService

logger = logging.getLogger(__name__)

# Base directory for web templates and static assets
WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


class DecimalEncoder(json.JSONEncoder):
    """JSON Encoder handling Decimal and datetime objects."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return f"{obj:.2f}"
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return super().default(obj)


class FinanceTrackerRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler routing REST API requests and static web files."""

    service: FinanceTrackerService = None

    def log_message(self, format, *args):
        # Professional minimal logging
        logger.info("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)

    def _send_json(self, data, status=200):
        body = json.dumps(data, cls=DecimalEncoder).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message, status=400):
        self._send_json({"error": message, "status": status}, status=status)

    def _send_file(self, file_path: Path, content_type: str):
        if not file_path.exists() or not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return

        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Route static web application files
        if path == "/" or path == "/index.html":
            self._send_file(TEMPLATES_DIR / "index.html", "text/html; charset=utf-8")
            return
        elif path.startswith("/static/"):
            relative_path = path[len("/static/") :]
            file_path = STATIC_DIR / relative_path
            if path.endswith(".css"):
                ct = "text/css; charset=utf-8"
            elif path.endswith(".js"):
                ct = "application/javascript; charset=utf-8"
            elif path.endswith(".json"):
                ct = "application/json"
            elif path.endswith(".png"):
                ct = "image/png"
            elif path.endswith(".svg"):
                ct = "image/svg+xml"
            else:
                ct = "text/plain"
            self._send_file(file_path, ct)
            return

        # Route REST API endpoints
        try:
            if path == "/api/summary":
                raw_month = query.get("month", [None])[0]
                month = None if (raw_month and raw_month.strip().upper() == "ALL") else raw_month
                start_date = query.get("start_date", [None])[0]
                end_date = query.get("end_date", [None])[0]

                summary = self.service.get_financial_summary(
                    start_date=start_date, end_date=end_date, month=month
                )

                breakdown_list = [
                    {
                        "category": b.category,
                        "total_amount": f"{b.total_amount:.2f}",
                        "percentage": f"{b.percentage:.2f}",
                    }
                    for b in summary.category_breakdown
                ]

                self._send_json(
                    {
                        "period_label": summary.period_label,
                        "total_income": f"{summary.total_income:.2f}",
                        "total_expense": f"{summary.total_expense:.2f}",
                        "net_cash_flow": f"{summary.net_cash_flow:.2f}",
                        "category_breakdown": breakdown_list,
                    }
                )

            elif path == "/api/transactions":
                raw_month = query.get("month", [None])[0]
                month = None if (raw_month and raw_month.strip().upper() == "ALL") else raw_month
                start_date = query.get("start_date", [None])[0]
                end_date = query.get("end_date", [None])[0]
                tx_type = query.get("type", [None])[0]
                category = query.get("category", [None])[0]

                if month and not start_date:
                    start_date = f"{month}-01"

                txs = self.service.list_transactions(
                    start_date=start_date,
                    end_date=end_date,
                    type_=tx_type,
                    category=category,
                )

                if month:
                    txs = [t for t in txs if t.timestamp.strftime("%Y-%m") == month]

                self._send_json([t.to_dict() for t in txs])

            elif path == "/api/categories":
                tx_type = query.get("type", [None])[0]
                categories = self.service.get_categories(type_=tx_type)
                self._send_json(categories)

            elif path == "/api/budgets":
                raw_month = query.get("month", [None])[0]
                month = datetime.now().strftime("%Y-%m") if (not raw_month or raw_month.upper() == "ALL") else raw_month
                all_budgets = [b for b in self.service.get_all_budgets() if b.month == month]
                spent_map = self.service.get_budget_spending_map(month)
                alerts = self.service.get_budget_alerts(month)

                budgets_payload = []
                for b in all_budgets:
                    spent = spent_map.get((b.category.lower(), month), Decimal("0.00"))
                    remaining = b.limit_amount - spent
                    pct = (spent / b.limit_amount * Decimal("100.00")) if b.limit_amount > 0 else Decimal("0")
                    budgets_payload.append(
                        {
                            "category": b.category,
                            "month": b.month,
                            "limit_amount": f"{b.limit_amount:.2f}",
                            "current_spent": f"{spent:.2f}",
                            "remaining": f"{remaining:.2f}",
                            "percentage": f"{pct:.1f}",
                            "status": "EXCEEDED" if spent > b.limit_amount else ("WARNING" if pct >= Decimal("90.0") else "NORMAL"),
                        }
                    )

                alerts_payload = [
                    {
                        "category": a.category,
                        "month": a.month,
                        "limit_amount": f"{a.limit_amount:.2f}",
                        "current_spent": f"{a.current_spent:.2f}",
                        "exceeded_by": f"{a.exceeded_by:.2f}",
                        "is_exceeded": a.is_exceeded,
                        "is_warning": a.is_warning,
                    }
                    for a in alerts
                ]

                self._send_json({"budgets": budgets_payload, "alerts": alerts_payload})

            elif path == "/api/export":
                raw_month = query.get("month", [None])[0]
                month = datetime.now().strftime("%Y-%m") if (not raw_month or raw_month.upper() == "ALL") else raw_month
                fmt = query.get("format", ["markdown"])[0]
                file_path = self.service.export_monthly_statement(month=month, format_type=fmt)
                content = file_path.read_text(encoding="utf-8")
                self._send_json(
                    {
                        "month": month,
                        "format": fmt,
                        "filename": file_path.name,
                        "content": content,
                    }
                )

            elif path == "/api/auth/me":
                email = query.get("email", [""])[0]
                profile = self.service.get_user_profile_by_email(email)
                if not profile:
                    self._send_error("User not found or not registered.", status=404)
                else:
                    self._send_json({"user": profile.to_dict()})

            elif path == "/api/auth/categories":
                from tracker.models import UserCategory
                self._send_json([c.value for c in UserCategory])

            else:
                self._send_error(f"API Endpoint '{path}' not found.", status=404)

        except FinanceTrackerError as e:
            self._send_error(e.message, status=400)
        except Exception as e:
            self._send_error(f"Internal server error: {e}", status=500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_length)
            payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}

            if path == "/api/transactions":
                tx_type = payload.get("type")
                category = payload.get("category")
                amount = payload.get("amount")
                payment_method = payload.get("payment_method")
                description = payload.get("description", "")
                timestamp = payload.get("timestamp")

                tx, alert = self.service.add_transaction(
                    type_=tx_type,
                    category=category,
                    amount=amount,
                    payment_method=payment_method,
                    description=description,
                    timestamp=timestamp,
                )

                alert_dict = None
                if alert:
                    alert_dict = {
                        "category": alert.category,
                        "month": alert.month,
                        "limit_amount": f"{alert.limit_amount:.2f}",
                        "current_spent": f"{alert.current_spent:.2f}",
                        "exceeded_by": f"{alert.exceeded_by:.2f}",
                        "is_exceeded": alert.is_exceeded,
                        "is_warning": alert.is_warning,
                    }

                self._send_json({"transaction": tx.to_dict(), "alert": alert_dict}, status=201)

            elif path == "/api/budgets":
                category = payload.get("category")
                month = payload.get("month")
                limit_amount = payload.get("limit_amount")

                budget = self.service.set_category_budget(category, month, limit_amount)
                self._send_json({"budget": budget.to_dict()}, status=200)

            elif path == "/api/categories":
                category_name = payload.get("category_name")
                tx_type = payload.get("type")
                added = self.service.add_custom_category(category_name, tx_type)
                self._send_json({"category": added}, status=200)

            elif path == "/api/import-statement":
                content = payload.get("content", "")
                result = self.service.import_bank_statement(content)

                latest_m = ""
                if result.transactions:
                    latest_tx = max(result.transactions, key=lambda t: t.timestamp)
                    latest_m = latest_tx.timestamp.strftime("%Y-%m")

                self._send_json(
                    {
                        "imported_count": result.imported_count,
                        "skipped_duplicates": result.skipped_duplicates,
                        "total_income": f"{result.total_income:.2f}",
                        "total_expense": f"{result.total_expense:.2f}",
                        "latest_month": latest_m,
                    },
                    status=200,
                )

            elif path == "/api/auth/login":
                email = payload.get("email", "")
                provider = payload.get("provider", "GOOGLE")
                profile, is_registered = self.service.authenticate_user(email, provider=provider)
                self._send_json(
                    {
                        "is_registered": is_registered,
                        "user": profile.to_dict() if profile else None,
                        "email": email,
                        "provider": provider,
                    }
                )

            elif path == "/api/auth/register":
                email = payload.get("email", "")
                surname = payload.get("surname", "")
                first_name = payload.get("first_name", "")
                date_of_birth = payload.get("date_of_birth", "")
                phone_number = payload.get("phone_number", "")
                category = payload.get("category", "")
                annual_income = payload.get("annual_income", "0")
                auth_provider = payload.get("auth_provider", "EMAIL")

                profile = self.service.register_user(
                    email=email,
                    surname=surname,
                    first_name=first_name,
                    date_of_birth=date_of_birth,
                    phone_number=phone_number,
                    category=category,
                    annual_income=annual_income,
                    auth_provider=auth_provider,
                )
                self._send_json({"user": profile.to_dict()}, status=201)

            else:
                self._send_error(f"Endpoint '{path}' not found.", status=404)

        except FinanceTrackerError as e:
            self._send_error(e.message, status=400)
        except Exception as e:
            self._send_error(f"Failed to process request: {e}", status=500)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/transactions/"):
            raw_id = path[len("/api/transactions/") :]
            tx_id = urllib.parse.unquote(raw_id).strip()
            try:
                result = self.service.delete_transaction(tx_id)
                self._send_json({"success": result, "deleted_id": tx_id}, status=200)
            except FinanceTrackerError as e:
                self._send_error(e.message, status=404)
            except Exception as e:
                self._send_error(str(e), status=500)
        else:
            self._send_error("Method Not Allowed", status=405)


def run_web_server(port: int = 8000, host: str = "127.0.0.1", data_dir: Path = None):
    """Starts the Python HTTP Web Server."""
    service = FinanceTrackerService(data_dir=data_dir)
    FinanceTrackerRequestHandler.service = service

    server_address = (host, port)
    httpd = HTTPServer(server_address, FinanceTrackerRequestHandler)
    print(f"\n============================================================")
    print(f"  [+] Personal Finance Tracker Web Server Running!")
    print(f"  [+] URL: http://{host}:{port}/")
    print(f"============================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Web server stopped by user. Goodbye!")
        httpd.server_close()
