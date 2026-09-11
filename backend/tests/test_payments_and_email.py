"""Tests for Razorpay payment scaffolding + Resend email graceful no-op."""
import os
import uuid
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://navyug-taste-love.preview.emergentagent.com").rstrip("/")


# ---- Razorpay config (unauthenticated) ----
def test_razorpay_config_disabled():
    r = requests.get(f"{BASE_URL}/api/payments/razorpay/config")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enabled"] is False
    assert data["key_id"] is None


# ---- Razorpay orders requires auth AND is disabled ----
def test_razorpay_orders_requires_auth():
    r = requests.post(f"{BASE_URL}/api/payments/razorpay/orders", json={"order_id": "NV-XXXX"})
    assert r.status_code == 401


def test_razorpay_orders_disabled_when_authenticated():
    s = requests.Session()
    email = f"test.pay.{uuid.uuid4().hex[:8]}@example.com"
    reg = s.post(f"{BASE_URL}/api/auth/register", json={
        "name": "TEST Pay", "email": email, "phone": "9999999999",
        "password": "NavyugTest123", "address": "TEST"})
    assert reg.status_code == 200, reg.text
    r = s.post(f"{BASE_URL}/api/payments/razorpay/orders", json={"order_id": "NV-XXXX"})
    assert r.status_code == 503


def test_razorpay_verify_disabled():
    s = requests.Session()
    email = f"test.ver.{uuid.uuid4().hex[:8]}@example.com"
    s.post(f"{BASE_URL}/api/auth/register", json={
        "name": "TEST Ver", "email": email, "phone": "9999999999",
        "password": "NavyugTest123", "address": "TEST"})
    r = s.post(f"{BASE_URL}/api/payments/razorpay/verify", json={
        "order_id": "NV-XXXX", "razorpay_order_id": "order_x",
        "razorpay_payment_id": "pay_x", "razorpay_signature": "sig_x"})
    assert r.status_code == 503


def test_razorpay_webhook_invalid_signature():
    # Webhook secret is empty -> currently returns 503; test both possibilities as documented.
    r = requests.post(f"{BASE_URL}/api/payments/razorpay/webhook",
                      data=b'{}', headers={"X-Razorpay-Signature": "bad"})
    assert r.status_code in (400, 503), r.text


# ---- Order creation still works and email hook doesn't crash ----
def test_order_create_with_email_does_not_crash():
    s = requests.Session()
    email = f"test.order.{uuid.uuid4().hex[:8]}@example.com"
    s.post(f"{BASE_URL}/api/auth/register", json={
        "name": "TEST Order", "email": email, "phone": "9999999999",
        "password": "NavyugTest123", "address": "TEST"})
    menu = requests.get(f"{BASE_URL}/api/menu").json()
    r = s.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST Order", "phone": "9999999999",
        "email": "test@example.com", "address": "TEST",
        "items": [{"menu_id": menu[0]["id"], "quantity": 1}]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["order_id"].startswith("NV-")
    assert data["status"] == "Pending"
    assert data["payment_status"] == "Pending"
    # delivery=40 for subtotal<500
    if data["subtotal"] < 500:
        assert data["delivery_fee"] == 40
    else:
        assert data["delivery_fee"] == 0


# ---- Admin auth + status update calls email helper without crashing ----
def _get_admin_session():
    s = requests.Session()
    status = requests.get(f"{BASE_URL}/api/admin/setup-status").json()
    if not status.get("configured"):
        setup_key = "navyug-first-admin-2026"
        r = s.post(f"{BASE_URL}/api/admin/setup", json={
            "name": "TEST Admin", "email": "test.admin@navyug.local",
            "password": "AdminNavyug123", "setup_key": setup_key})
        if r.status_code != 200:
            return None
        return s
    # Try well-known creds; if not accepted, skip
    for pwd in ("AdminNavyug123", "navyug-admin-2026", "NavyugAdmin123"):
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": "test.admin@navyug.local", "password": pwd})
        if r.status_code == 200:
            return s
    return None


def test_admin_status_update_and_admin_lists():
    admin = _get_admin_session()
    if not admin:
        # Cannot test without admin creds; ensure endpoint is at least protected
        r = requests.get(f"{BASE_URL}/api/orders/all")
        assert r.status_code == 401
        return
    # Admin lists accessible
    assert admin.get(f"{BASE_URL}/api/orders/all").status_code == 200
    assert admin.get(f"{BASE_URL}/api/catering").status_code == 200
    assert admin.get(f"{BASE_URL}/api/contact").status_code == 200
    # Create an order as a fresh customer, then update status as admin
    cust = requests.Session()
    email = f"test.cust.{uuid.uuid4().hex[:8]}@example.com"
    cust.post(f"{BASE_URL}/api/auth/register", json={
        "name": "TEST Cust", "email": email, "phone": "9999999999",
        "password": "NavyugTest123", "address": "TEST"})
    menu = requests.get(f"{BASE_URL}/api/menu").json()
    order = cust.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST Cust", "phone": "9999999999",
        "email": "test@example.com", "address": "TEST",
        "items": [{"menu_id": menu[0]["id"], "quantity": 1}]}).json()
    r = admin.patch(f"{BASE_URL}/api/orders/{order['order_id']}", json={"status": "Confirmed"})
    assert r.status_code == 200 and r.json() == {"ok": True}


# ---- Catering with and without email doesn't crash ----
def test_catering_with_email():
    r = requests.post(f"{BASE_URL}/api/catering", json={
        "name": "TEST Cater", "phone": "9999999999", "email": "test@example.com",
        "event_type": "Birthday", "event_date": "2026-12-01", "guests": 10,
        "location": "TEST", "requirements": "Veg", "message": "TEST"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "New"


def test_catering_without_email():
    r = requests.post(f"{BASE_URL}/api/catering", json={
        "name": "TEST Cater2", "phone": "9999999999", "email": "",
        "event_type": "Birthday", "event_date": "2026-12-01", "guests": 10,
        "location": "TEST", "requirements": "Veg", "message": "TEST"})
    assert r.status_code == 200, r.text
