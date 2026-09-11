"""Razorpay payment endpoints.
Backend creates the Razorpay order, verifies the checkout signature and
handles webhooks. Order total is calculated from MongoDB, never from client.
"""
import os, hmac, hashlib, json, logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger("navyug.pay")
router = APIRouter(prefix="/api/payments/razorpay", tags=["payments"])

KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

_client = None
if KEY_ID and KEY_SECRET:
    try:
        import razorpay
        _client = razorpay.Client(auth=(KEY_ID, KEY_SECRET))
        logger.info("Razorpay client initialised (test mode: %s)", KEY_ID.startswith("rzp_test_"))
    except Exception as exc:
        logger.error("Razorpay init failed: %s", exc)


def is_enabled() -> bool:
    return _client is not None


class CreatePaymentIn(BaseModel):
    order_id: str


class VerifyPaymentIn(BaseModel):
    order_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


def register(app_state):
    """Wire up dependencies from server.py (db handle + current_user dependency)."""
    db = app_state["db"]
    current_user = app_state["current_user"]

    @router.get("/config")
    async def config():
        return {"enabled": is_enabled(), "key_id": KEY_ID if is_enabled() else None}

    @router.post("/orders")
    async def create_payment(body: CreatePaymentIn, user=Depends(current_user)):
        if not is_enabled():
            raise HTTPException(503, "Online payments are not configured yet")
        order = await db.orders.find_one({"order_id": body.order_id, "user_id": str(user["_id"])})
        if not order:
            raise HTTPException(404, "Order not found")
        if order.get("payment_status") == "Paid":
            raise HTTPException(409, "Order is already paid")
        amount_paise = int(round(float(order["total"]) * 100))
        try:
            rzp_order = _client.order.create({
                "amount": amount_paise, "currency": "INR",
                "receipt": order["order_id"][:40],
                "notes": {"navyug_order_id": order["order_id"]},
                "payment_capture": 1,
            })
        except Exception as exc:
            logger.error("Razorpay order create failed: %s", exc)
            raise HTTPException(502, "Could not start payment. Please try again.")
        await db.orders.update_one(
            {"order_id": order["order_id"]},
            {"$set": {"razorpay_order_id": rzp_order["id"], "razorpay_amount": amount_paise,
                      "payment_updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        return {"key_id": KEY_ID, "razorpay_order_id": rzp_order["id"],
                "amount": amount_paise, "currency": "INR",
                "order_id": order["order_id"], "customer_name": order.get("customer_name"),
                "email": order.get("email"), "phone": order.get("phone")}

    @router.post("/verify")
    async def verify_payment(body: VerifyPaymentIn, user=Depends(current_user)):
        if not is_enabled():
            raise HTTPException(503, "Online payments are not configured yet")
        order = await db.orders.find_one({"order_id": body.order_id, "user_id": str(user["_id"])})
        if not order:
            raise HTTPException(404, "Order not found")
        expected_rzp_order = order.get("razorpay_order_id")
        if not expected_rzp_order or expected_rzp_order != body.razorpay_order_id:
            raise HTTPException(400, "Order mismatch")
        message = f"{expected_rzp_order}|{body.razorpay_payment_id}".encode()
        expected_sig = hmac.new(KEY_SECRET.encode(), message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, body.razorpay_signature):
            raise HTTPException(400, "Invalid payment signature")
        if order.get("payment_status") != "Paid":
            await db.orders.update_one(
                {"order_id": order["order_id"], "razorpay_order_id": expected_rzp_order,
                 "payment_status": {"$ne": "Paid"}},
                {"$set": {"payment_status": "Paid", "status": "Confirmed",
                          "razorpay_payment_id": body.razorpay_payment_id,
                          "payment_verified_at": datetime.now(timezone.utc).isoformat()}}
            )
        return {"ok": True, "payment_status": "Paid"}

    @router.post("/webhook")
    async def webhook(request: Request,
                      x_razorpay_signature: str = Header(default=""),
                      x_razorpay_event_id: str | None = Header(default=None)):
        raw = await request.body()
        if not WEBHOOK_SECRET:
            raise HTTPException(503, "Webhook secret not configured")
        expected = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not x_razorpay_signature or not hmac.compare_digest(expected, x_razorpay_signature):
            raise HTTPException(400, "Invalid webhook signature")
        event = json.loads(raw or "{}")
        event_id = x_razorpay_event_id or event.get("id")
        if event_id:
            try:
                await db.razorpay_webhook_events.insert_one(
                    {"event_id": event_id, "received_at": datetime.now(timezone.utc).isoformat()}
                )
            except Exception as exc:
                if getattr(exc, "code", None) == 11000:
                    return {"ok": True, "duplicate": True}
                raise
        payment = (event.get("payload", {}) or {}).get("payment", {}).get("entity", {}) or {}
        rzp_order_id = payment.get("order_id")
        payment_id = payment.get("id")
        name = event.get("event")
        if name in ("payment.captured", "order.paid") and rzp_order_id:
            await db.orders.update_one(
                {"razorpay_order_id": rzp_order_id, "payment_status": {"$ne": "Paid"}},
                {"$set": {"payment_status": "Paid", "status": "Confirmed",
                          "razorpay_payment_id": payment_id,
                          "payment_updated_at": datetime.now(timezone.utc).isoformat()}}
            )
        elif name == "payment.failed" and rzp_order_id:
            await db.orders.update_one(
                {"razorpay_order_id": rzp_order_id, "payment_status": {"$nin": ["Paid", "Refunded"]}},
                {"$set": {"payment_status": "Failed",
                          "razorpay_payment_id": payment_id,
                          "payment_updated_at": datetime.now(timezone.utc).isoformat()}}
            )
        return {"ok": True}

    return router
