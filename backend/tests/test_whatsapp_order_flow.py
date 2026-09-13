"""Backend tests for WhatsApp order flow: event_datetime/utr/payment_method, UPI config, CORS preflight, seed idempotency."""
import os, uuid, requests, pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://navyug-taste-love.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def customer():
    s = requests.Session()
    email = f"test.wa.{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register", json={"name": "TEST WA", "email": email,
        "phone": "9999999999", "password": "NavyugTest123", "address": "TEST Addr"})
    assert r.status_code == 200, r.text
    return s


def test_upi_config_disabled_shape():
    r = requests.get(f"{BASE_URL}/api/payments/upi/config")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False
    assert data["upi_id"] == ""
    assert data["payee_name"]
    assert data["whatsapp_number"] == "919389887970"


def test_menu_is_seeded_and_idempotent():
    r = requests.get(f"{BASE_URL}/api/menu")
    assert r.status_code == 200
    items = r.json()
    # Expect around 57 seeded items; must be >=50 and stable.
    assert len(items) >= 50, f"Menu items unexpectedly low: {len(items)}"


def test_specials_and_most_ordered():
    assert requests.get(f"{BASE_URL}/api/menu/specials").status_code == 200
    assert requests.get(f"{BASE_URL}/api/menu/most-ordered").status_code == 200


def test_cors_preflight_menu():
    r = requests.options(f"{BASE_URL}/api/menu", headers={
        "Origin": "https://navyug-taste-love.preview.emergentagent.com",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "content-type",
    })
    assert r.status_code in (200, 204), r.text
    allow = r.headers.get("access-control-allow-origin") or r.headers.get("Access-Control-Allow-Origin")
    assert allow, f"Missing ACAO header. Headers: {dict(r.headers)}"


def test_order_persists_new_fields(customer):
    menu = requests.get(f"{BASE_URL}/api/menu").json()
    item = menu[0]
    payload = {
        "customer_name": "TEST WA",
        "phone": "9999999999",
        "email": "wa@example.com",
        "address": "TEST Venue",
        "special_instructions": "Extra spicy",
        "event_datetime": "2026-06-20T19:00",
        "utr": "UTR123",
        "payment_method": "UPI",
        "items": [{"menu_id": item["id"], "quantity": 2}],
    }
    r = customer.post(f"{BASE_URL}/api/orders", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["event_datetime"] == "2026-06-20T19:00"
    assert data["utr"] == "UTR123"
    assert data["payment_method"] == "UPI"
    order_id = data["order_id"]

    # Verify GET /api/orders returns new fields too
    listing = customer.get(f"{BASE_URL}/api/orders").json()
    match = next((x for x in listing if x["order_id"] == order_id), None)
    assert match is not None
    assert match["event_datetime"] == "2026-06-20T19:00"
    assert match["utr"] == "UTR123"
    assert match["payment_method"] == "UPI"


def test_order_utr_optional_and_cod_default(customer):
    menu = requests.get(f"{BASE_URL}/api/menu").json()
    item = menu[0]
    r = customer.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST WA", "phone": "9999999999", "address": "Addr",
        "event_datetime": "2026-07-01T20:00",
        "items": [{"menu_id": item["id"], "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["utr"] is None
    assert data["payment_method"] == "COD"
    assert data["event_datetime"] == "2026-07-01T20:00"
