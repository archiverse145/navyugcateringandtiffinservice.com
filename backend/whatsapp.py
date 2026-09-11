import logging, os
import httpx
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger("navyug.whatsapp")
SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")
OWNER = os.environ.get("OWNER_WHATSAPP_TO", "")
CUSTOMER_ALERTS = os.environ.get("WHATSAPP_CUSTOMER_ALERTS", "false").lower() == "true"


def is_enabled(): return bool(SID and TOKEN and FROM and OWNER)


def wa(number):
    n = number.strip().replace(" ", "").replace("-", "")
    if n.startswith("whatsapp:"): return n
    if not n.startswith("+"): n = "+91" + n.lstrip("0")
    return "whatsapp:" + n


async def send(to, body):
    if not is_enabled(): return {"skipped": True}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json", auth=(SID, TOKEN), data={"From": wa(FROM), "To": wa(to), "Body": body})
    data = r.json()
    if r.status_code >= 300:
        logger.error(f"WhatsApp send failed ({r.status_code}): {data.get('message')}")
        return {"ok": False, "error": data.get("message"), "code": data.get("code")}
    return {"ok": True, "sid": data.get("sid"), "status": data.get("status")}


def money(n): return f"₹{int(n):,}"


async def notify_new_order(order):
    lines = "\n".join(f"• {i['quantity']} × {i['name']}" for i in order["items"])
    note = f"\n📝 Note: {order['special_instructions']}" if order.get("special_instructions") else ""
    pay = "Paid online" if order.get("payment_status") == "Paid" else "Cash on delivery"
    body = f"🍱 *New Navyug order {order['order_id']}*\n\n{lines}\n\n💰 Total: {money(order['total'])} ({pay})\n👤 {order['customer_name']} · {order['phone']}\n📍 {order['address']}{note}"
    await send(OWNER, body)


async def notify_payment_captured(order):
    await send(OWNER, f"✅ *Payment received* for order {order['order_id']} — {money(order['total'])} paid online by {order['customer_name']}.")


async def notify_catering(inq):
    body = f"🎉 *New catering inquiry {inq['inquiry_id']}*\n\n👤 {inq.get('name')} · {inq.get('phone')}\n📅 {inq.get('event_type')} on {inq.get('event_date')} · {inq.get('guests')} guests\n📍 {inq.get('location')}\n📝 {inq.get('requirements') or inq.get('message') or '-'}"
    await send(OWNER, body)


async def notify_customer_status(order, status):
    if not CUSTOMER_ALERTS or not order.get("phone"): return
    msgs = {"Confirmed": "is confirmed and our kitchen has started.", "Preparing": "is being freshly prepared.", "Out for Delivery": "is on its way to you!", "Delivered": "has been delivered. Enjoy your meal!", "Cancelled": "has been cancelled. Call us if this is unexpected."}
    if status in msgs:
        await send(order["phone"], f"Namaste {order['customer_name'].split()[0]}! Your Navyug order *{order['order_id']}* {msgs[status]}\n\n— Navyug Catering & Tiffin, The taste of love……")


def register(ctx):
    admin_user = ctx["admin_user"]
    router = APIRouter(prefix="/api/notifications/whatsapp")

    @router.get("/config")
    async def config(_: dict = Depends(admin_user)):
        return {"enabled": is_enabled(), "sandbox": FROM in ("+14155238886", "+17372508034"), "from": FROM, "owner": OWNER, "customer_alerts": CUSTOMER_ALERTS}

    @router.post("/test")
    async def test(_: dict = Depends(admin_user)):
        if not is_enabled(): raise HTTPException(400, "WhatsApp is not configured")
        result = await send(OWNER, "👋 Namaste from Navyug! WhatsApp order alerts are working. You'll get a message here for every new order.")
        if not result.get("ok"): raise HTTPException(424, f"Twilio: {result.get('error') or 'rejected the message'}")
        return result

    return router
