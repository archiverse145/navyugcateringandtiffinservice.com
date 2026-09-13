# Navyug Catering & Tiffin Services — PRD

## Original Problem Statement
Production-quality full-stack web app for Navyug Catering & Tiffin Services (Indian homemade-food/tiffin/catering). Tagline: "The taste of love……". Burgundy/deep red brand identity. Customer site with menu, cart, ordering, catering + contact forms, customer accounts, admin dashboard, custom JWT auth, MongoDB.

## Architecture
- Frontend: React 19 + react-router 7 + shadcn/ui + custom warm Indian food CSS
- Backend: FastAPI + Motor async MongoDB
- Auth: Custom JWT via HttpOnly cookies
- Payments: Razorpay (server-side order creation, HMAC signature verify, webhook)
- Email: Resend for transactional emails (order confirmation + status)

## User Personas
- Customer: Orders daily tiffin, browses menu, tracks order status.
- Event Host: Submits catering inquiry for events.
- Admin: Manages menu, orders, catering inquiries, contact messages.

## What's Implemented (Feb 2026)
- Storefront home with hero, "Most Ordered" section
- Dynamic menu with categories, seed data
- Cart with quantity controls + delivery fee logic
- Checkout with backend price validation
- Customer register/login/logout via JWT
- Order status flow: Pending → Confirmed → Preparing → Out for Delivery → Delivered/Cancelled
- Catering inquiry form + admin management
- Contact inquiry form + admin management
- Admin dashboard: menu CRUD, order status, catering + contact status management
- First-admin one-time setup lock
- **NEW: Razorpay payment integration** — /api/payments/razorpay/config, /orders, /verify, /webhook (all inactive until keys added)
- **NEW: Resend transactional email** — order confirmation, status update, catering ack (silently no-ops until API key added)
- Frontend Checkout conditionally shows "Pay Online" button when Razorpay enabled; COD-only fallback otherwise
- **NEW (Jun 2026): Printable order receipt** — `src/Receipt.js` modal with Print/Save PDF (print-only CSS), Share (Web Share API → clipboard fallback). Opened from confirmation page (`confirmation-receipt-button`) and every row in Account order history (`receipt-button-{order_id}`). Account page styles added.
- **Jun 2026 business details**: main phone 9305162868 (orders/tiffin), catering phone 9389887970, Instagram @navyugcateringandtiffinservice. Real menu seeded (menu_seed version 2 in `settings` collection; 50 items, `section` field = "tiffin" | "snacks"). Default prices: gravy/dal ₹120, dry/snacks/breakfast/sweets ₹80, chapati ₹20, rice bowl ₹50, Plain Idli ₹10 — admin edits via dashboard. New `/just-hungry` page (snacks); `/tiffin` shows grouped tiffin menu with Add-to-cart. Admin menu form has section selector. Dish photos are still Unsplash placeholders — user to send originals.
- **Jun 2026 real photos**: 39 photos extracted from user's PDF, colour-corrected (blue-tint removal, warm WB, crop) → `frontend/public/photos/*.jpg` (24 dish photos + logo-mark.png + tiffin-wide.jpg) with `manifest.json`. Menu seed v3: 57 items, 23 with real photos; new dishes Mix Veg, Aloo Sabzi, Green Salad, Onion Salad, Raita, Veg Pulao, Veg Noodles. Header uses real logo. Home "Everyday Tiffin" band shows real tiffin photo. Admin dish form has a photo picker (gallery + URL) and thumbnails in the list; admin form styled. Admin switched to owner account navyugcatering05@gmail.com (see test_credentials.md).
- **Jun 2026 admin & UX round**: dish cards highlight when in cart and show −/qty/+ inline (`card-qty-{id}`); home "100% vegetarian" is a gold stamp on the tiffin photo; footer shows both phones side by side + Instagram + address "Krishna Nagar, Kanpur" (also on Contact + receipt). Admin: time-based greeting + date + stats (orders today, pending, total sales); **photo upload via camera/file** (`/app/backend/storage.py` → Emergent Object Storage, compressed to 1200px JPEG, served publicly at `/api/photos/file/{id}`, records in `db.photos` with soft delete); **press-and-hold (700ms) on a gallery photo deletes it** (uploaded → soft delete; built-in → hidden via `settings.hidden_photos`). EMERGENT_LLM_KEY added to backend/.env for storage.
- **Jun 2026: Sold-out toggle** in Admin → Menu (`admin-menu-toggle-{id}`) flips `available` via PUT /api/menu/{id}; storefront shows "Sold out" + disabled Add.
- **Jun 2026: Order sound alert** — admin polls /api/orders/all every 15s; new orders trigger Web-Audio chime (toggle `admin-sound-toggle`, persisted in localStorage), a pulsing banner (`new-orders-banner`) and highlighted rows with NEW tag; stats auto-refresh.
- **Jun 2026: Admin order details** — order rows show dish preview + note; tap row or View (`admin-view-{id}`) opens Receipt as printable "Kitchen slip" (Receipt `title` prop). Mobile admin row layout fixed.
- **Jun 2026: Today's Special** — `is_special` on menu items; admin star toggle per row (`admin-menu-special-{id}`); GET /api/menu/specials; home shows burgundy "Aaj ka khaas" band with add-to-cart above Most Ordered when any dish is pinned. User chose Twilio WhatsApp INSTEAD of Resend email (Resend deprioritized).
- **Jun 2026: Twilio WhatsApp alerts** — `/app/backend/whatsapp.py` (httpx → Twilio Messages API). Owner gets WhatsApp on new order, payment captured (verify + webhook), catering inquiry; customer status messages gated by WHATSAPP_CUSTOMER_ALERTS=false. Admin endpoints: GET /api/notifications/whatsapp/config, POST /api/notifications/whatsapp/test; admin header button "send test" with sandbox tip. Env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM=+14155238886 (SANDBOX — account is Trial, no production sender), OWNER_WHATSAPP_TO=+919389887970. STATUS: BLOCKED until owner joins sandbox ("join <code>" to +1 415 523 8886) — Twilio returns 21654 ContentSid Required otherwise. Note: sandbox freeform only within 24h of owner's last message; production needs upgraded account + approved template (add ContentSid support then). Do NOT return HTTP 502 from API — Cloudflare replaces body; use 424.
- **Jun 2026: Order timings banner** on home (`TimingBanner`, `timing-banner`): Breakfast order by 10 PM previous day / delivered 9–10 AM; Lunch by 11 AM / 1–2 PM; Dinner by 5:30 PM / 8–9 PM; live open/closed status computed in IST. WhatsApp PAUSED by user (TWILIO_WHATSAPP_FROM="" → is_enabled false; creds kept). Twilio trial cannot send custom text (only pre-approved ContentSid templates) — requires account upgrade.
- **Jun 2026: WhatsApp click-to-chat checkout (NO Twilio)** — Checkout redesigned: Step 1 details (name, phone, email, event/delivery datetime REQUIRED, venue/address, instructions), Step 2 payment (UPI QR via qrcode.react when UPI_ID env set — currently EMPTY, shows placeholder telling to pay to 93898 87970 — plus optional UTR field; Razorpay "pay online" kept as secondary), Step 3 green "Confirm & Send Order via WhatsApp" (`send-whatsapp-order-button`) → POST /api/orders (payment_method UPI/COD/Razorpay, utr, event_datetime) → opens https://wa.me/{ORDER_WHATSAPP_NUMBER=919389887970}?text=formatted order → cart cleared → Thank-you page with "Open WhatsApp again" (`confirmation-whatsapp-button`). Receipt/admin rows/kitchen slip show event date + payment label. GET /api/payments/upi/config. Twilio paused ("exit the twilio thing").
- **Jun 2026: Deployment fixes** — seed_menu idempotent (only when menu empty; no delete_many); CORS from CORS_ORIGINS env; deployment_agent PASS. Testing iteration_5 PASS (backend+frontend).
- **Jun 2026: Admin login hardening** — seed_admin() at startup from ADMIN_EMAIL/ADMIN_PASSWORD (creates or updates role/password idempotently, so fresh deployments have the owner account); login/register email strip+lowercase; login input autoCapitalize=none. iteration_6 PASS.
- **NEW (Jun 2026): Reorder** — "Order again" on receipt (`receipt-reorder-button`) + "Reorder" per Account row (`reorder-button-{order_id}`) refills cart from live menu (skips unavailable dishes) and navigates to /cart.

## Prioritized Backlog
- **Razorpay ACTIVATED (Jun 2026)** — test keys in backend/.env; `/api/payments/razorpay/config` returns enabled:true; live test order creation verified; checkout popup opens in Test Mode. WEBHOOK_SECRET set (Jun 2026); signed webhook test → order Paid/Confirmed, duplicates ignored, bad signature rejected.
- P2 (deprioritized by user): RESEND_API_KEY for order emails — user prefers Twilio WhatsApp
- P1 (PAUSED by user): WhatsApp — needs Twilio upgrade (trial = templates only); owner already joined trial sandbox (+17372508034, "join twilio-trial"). When production number approved: set TWILIO_WHATSAPP_FROM, add ContentSid template support.
- P0: Google Places API integration for live Google Reviews (needs Places API key + Place ID; user's business CID: 1443852844271025327)
- P1: Twilio WhatsApp notifications (deferred until production WhatsApp Business number is approved)
- P1: Tiffin Subscriptions / Monthly Plans
- P2: Delivery tracking, coupons, in-app reviews
