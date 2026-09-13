"""Admin login flow tests for the navyugcatering05@gmail.com account."""
import os
import subprocess
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # frontend/.env fallback (test running server-side)
    from pathlib import Path
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "navyugcatering05@gmail.com"
ADMIN_PASSWORD = "ratika@123"
CUSTOMER_EMAIL = "receipt.tester@example.com"
CUSTOMER_PASSWORD = "test1234"


def _post(path, json):
    return requests.post(f"{BASE_URL}{path}", json=json, timeout=15)


class TestAdminLogin:
    def test_login_success(self):
        r = _post("/api/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        assert "access_token" in r.cookies

    def test_me_and_orders_all(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
        assert r.status_code == 200
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert me.status_code == 200
        assert me.json()["role"] == "admin"
        orders = s.get(f"{BASE_URL}/api/orders/all", timeout=15)
        assert orders.status_code == 200
        assert isinstance(orders.json(), list)

    @pytest.mark.parametrize("email", [
        "Navyugcatering05@gmail.com ",
        " NAVYUGCATERING05@GMAIL.COM",
        "  navyugcatering05@gmail.com  ",
    ])
    def test_login_tolerant_email(self, email):
        r = _post("/api/auth/login", {"email": email, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, f"{email!r} -> {r.status_code} {r.text}"
        assert r.json()["role"] == "admin"

    def test_wrong_password_401(self):
        r = _post("/api/auth/login", {"email": ADMIN_EMAIL, "password": "wrong-pw"})
        assert r.status_code == 401
        detail = r.json().get("detail")
        assert isinstance(detail, str) and detail

    def test_old_admin_rejected(self):
        r = _post("/api/auth/login", {"email": "test-admin@navyug.local", "password": "NavyugAdmin#2026"})
        assert r.status_code == 401

    def test_customer_login_still_works(self):
        r = _post("/api/auth/login", {"email": CUSTOMER_EMAIL, "password": CUSTOMER_PASSWORD})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "customer"


class TestAdminSeedIdempotent:
    def test_only_one_admin_in_db_after_restart(self):
        # Restart backend
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=False)
        # Wait for it to come up
        for _ in range(30):
            time.sleep(1)
            try:
                if requests.get(f"{BASE_URL}/api/", timeout=3).status_code == 200:
                    break
            except Exception:
                pass
        # Verify still exactly one via login working
        r = _post("/api/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200

        # Direct mongo check
        from pymongo import MongoClient
        mongo_url = None
        db_name = None
        for line in open("/app/backend/.env"):
            line = line.strip()
            if line.startswith("MONGO_URL="):
                mongo_url = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("DB_NAME="):
                db_name = line.split("=", 1)[1].strip().strip('"')
        mc = MongoClient(mongo_url)
        count = mc[db_name].users.count_documents({"email": ADMIN_EMAIL})
        assert count == 1, f"Expected 1 admin user, found {count}"
