"""Live regression checks for Navyug health, auth, menu, orders, and inquiries."""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://navyug-taste-love.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def customer():
    s = requests.Session()
    email = f"test.customer.{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register", json={"name": "TEST Customer", "email": email,
                  "phone": "9999999999", "password": "NavyugTest123", "address": "TEST Address"})
    assert r.status_code in (200, 409), r.text
    if r.status_code == 409:
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "NavyugTest123"})
    assert r.status_code == 200, r.text
    return s


def test_health_and_menu():
    r = requests.get(f"{BASE_URL}/api/")
    assert r.status_code == 200 and r.json()["message"] == "Navyug Catering API"
    r = requests.get(f"{BASE_URL}/api/menu")
    assert r.status_code == 200 and len(r.json()) >= 1
    assert {"id", "name", "price", "category", "available", "is_vegetarian"}.issubset(r.json()[0])


def test_unauthenticated_order_rejected():
    menu = requests.get(f"{BASE_URL}/api/menu").json()
    r = requests.post(f"{BASE_URL}/api/orders", json={"customer_name": "x", "phone": "1", "address": "x",
                   "items": [{"menu_id": menu[0]["id"], "quantity": 1}]})
    assert r.status_code == 401


def test_customer_order_backend_total_and_cookie(customer):
    menu = requests.get(f"{BASE_URL}/api/menu").json()
    item = menu[0]
    r = customer.post(f"{BASE_URL}/api/orders", json={"customer_name": "TEST Customer", "phone": "9999999999",
                   "email": "test@example.com", "address": "TEST Address",
                   "items": [{"menu_id": item["id"], "quantity": 2}]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["items"][0]["price"] == item["price"]
    assert data["subtotal"] == item["price"] * 2
    assert data["total"] == data["subtotal"] + (40 if data["subtotal"] < 500 else 0)
    assert customer.get(f"{BASE_URL}/api/orders").status_code == 200


def test_customer_cannot_access_admin(customer):
    r = customer.get(f"{BASE_URL}/api/orders/all")
    assert r.status_code == 403


def test_inquiries_persist():
    catering = requests.post(f"{BASE_URL}/api/catering", json={"name": "TEST Event", "phone": "9999999999",
        "email": None, "event_type": "Birthday", "event_date": "2026-12-01", "guests": 10,
        "location": "TEST Hall", "requirements": "Veg", "message": "TEST"})
    assert catering.status_code == 200, catering.text
    assert catering.json()["status"] == "New"
    contact = requests.post(f"{BASE_URL}/api/contact", json={"name": "TEST Contact", "contact": "9999999999",
        "message": "TEST message"})
    assert contact.status_code == 200, contact.text
    assert contact.json()["status"] == "New"
