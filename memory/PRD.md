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
- **NEW (Jun 2026): Reorder** — "Order again" on receipt (`receipt-reorder-button`) + "Reorder" per Account row (`reorder-button-{order_id}`) refills cart from live menu (skips unavailable dishes) and navigates to /cart.

## Prioritized Backlog
- **Razorpay ACTIVATED (Jun 2026)** — test keys in backend/.env; `/api/payments/razorpay/config` returns enabled:true; live test order creation verified; checkout popup opens in Test Mode. WEBHOOK_SECRET still empty (optional).
- P0: Add RESEND_API_KEY to activate order emails
- P0: Google Places API integration for live Google Reviews (needs Places API key + Place ID; user's business CID: 1443852844271025327)
- P1: Twilio WhatsApp notifications (deferred until production WhatsApp Business number is approved)
- P1: Tiffin Subscriptions / Monthly Plans
- P2: Delivery tracking, coupons, in-app reviews
