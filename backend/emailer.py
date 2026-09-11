"""Async, non-blocking transactional email helper using Resend.
Silently no-ops when RESEND_API_KEY is not configured, so orders never fail
because of email delivery.
"""
import os, asyncio, logging
from typing import Optional

logger = logging.getLogger("navyug.email")
_configured = False
try:
    import resend
    if os.environ.get("RESEND_API_KEY"):
        resend.api_key = os.environ["RESEND_API_KEY"]
        _configured = True
except Exception as exc:
    logger.warning("Resend SDK not available: %s", exc)

SENDER = os.environ.get("SENDER_EMAIL", "Navyug <onboarding@resend.dev>")
BUSINESS = os.environ.get("BUSINESS_NAME", "Navyug Catering & Tiffin Services")


def _wrap(inner_html: str, preview: str = "") -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#fbf5ec;font-family:Georgia,serif;color:#2d1a12;">
<span style="display:none;visibility:hidden;opacity:0;color:transparent;height:0;width:0;overflow:hidden">{preview}</span>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fbf5ec;padding:32px 12px;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 6px 24px rgba(80,20,15,0.08);">
<tr><td style="background:#7a1f2b;padding:22px 28px;color:#f6e6c8;">
<div style="font-family:Georgia,serif;font-size:22px;letter-spacing:0.4px;"><b>Navyug</b></div>
<div style="font-size:12px;opacity:0.85;letter-spacing:2px;">THE TASTE OF LOVE……</div>
</td></tr>
<tr><td style="padding:28px;font-size:15px;line-height:1.55;">{inner_html}</td></tr>
<tr><td style="background:#f6ecd8;padding:18px 28px;font-size:12px;color:#6b3b2a;">
{BUSINESS} · Kanpur, Uttar Pradesh · +91 93051 62868
</td></tr>
</table></td></tr></table></body></html>"""


def _rupees(paise: int) -> str:
    return f"₹{paise/100:,.2f}"


async def _send(to: str, subject: str, html: str):
    if not _configured:
        logger.info("Email skipped (RESEND_API_KEY missing): to=%s subject=%s", to, subject)
        return
    if not to:
        return
    try:
        params = {"from": SENDER, "to": [to], "subject": subject, "html": html}
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info("Email sent: id=%s to=%s", (result or {}).get("id"), to)
    except Exception as exc:
        logger.warning("Email send failed to %s: %s", to, exc)


async def send_order_confirmation(order: dict):
    items = "".join(
        f'<tr><td style="padding:6px 0;">{x["quantity"]} × {x["name"]}</td>'
        f'<td align="right" style="padding:6px 0;">₹{x["price"]*x["quantity"]:,}</td></tr>'
        for x in order.get("items", [])
    )
    payment_line = "Cash on delivery" if order.get("payment_status") != "Paid" else "Paid online"
    html = _wrap(f"""
<p>Namaste {order['customer_name'].split(' ')[0]},</p>
<p>Thank you for ordering with Navyug. Your homemade meal is being prepared with care.</p>
<div style="background:#fbf5ec;border-radius:10px;padding:16px 20px;margin:18px 0;">
  <div style="font-size:12px;letter-spacing:2px;color:#7a1f2b;">ORDER</div>
  <div style="font-size:20px;font-weight:700;">{order['order_id']}</div>
</div>
<table width="100%" style="border-top:1px solid #ecd9b8;border-bottom:1px solid #ecd9b8;margin:12px 0;font-size:14px;">
{items}
<tr><td style="padding:8px 0;">Delivery</td><td align="right">₹{order.get('delivery_fee',0):,}</td></tr>
<tr><td style="padding:10px 0;font-weight:700;">Total</td><td align="right" style="font-weight:700;">₹{order.get('total',0):,}</td></tr>
</table>
<p style="font-size:14px;"><b>Deliver to:</b> {order.get('address','')}</p>
<p style="font-size:14px;"><b>Payment:</b> {payment_line}</p>
<p>We'll message you as soon as it leaves our kitchen.</p>
""", preview=f"Order {order['order_id']} received")
    await _send(order.get("email") or "", f"Order {order['order_id']} received · Navyug", html)


async def send_order_status(order: dict, new_status: str):
    subject_map = {
        "Confirmed": "confirmed", "Preparing": "being prepared",
        "Out for Delivery": "on the way", "Delivered": "delivered", "Cancelled": "cancelled",
    }
    label = subject_map.get(new_status, new_status.lower())
    html = _wrap(f"""
<p>Hi {order['customer_name'].split(' ')[0]},</p>
<p>Your Navyug order <b>{order['order_id']}</b> is now <b style="color:#7a1f2b;">{new_status}</b>.</p>
{"<p>We hope every bite tastes like home.</p>" if new_status == "Delivered" else "<p>We'll keep you posted on the next update.</p>"}
""", preview=f"Order {order['order_id']} is {label}")
    await _send(order.get("email") or "", f"Order {order['order_id']} · {new_status} · Navyug", html)


async def send_catering_ack(inquiry: dict):
    html = _wrap(f"""
<p>Namaste {inquiry['name'].split(' ')[0]},</p>
<p>Thank you for reaching out to Navyug for your <b>{inquiry.get('event_type','')}</b> on <b>{inquiry.get('event_date','')}</b>.</p>
<p>Our team will get in touch shortly with a menu curated around your guests.</p>
<div style="background:#fbf5ec;border-radius:10px;padding:16px 20px;margin:18px 0;font-size:14px;">
  <div><b>Guests:</b> {inquiry.get('guests','')}</div>
  <div><b>Location:</b> {inquiry.get('location','')}</div>
</div>
""", preview="Catering inquiry received")
    await _send(inquiry.get("email") or "", "Your catering inquiry with Navyug", html)
