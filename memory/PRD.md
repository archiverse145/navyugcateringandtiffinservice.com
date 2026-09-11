# Navyug Catering & Tiffin Services — Product Requirements

## Original problem statement
Build a complete, production-quality full-stack web application for Navyug Catering & Tiffin Services with a customer website, menu, cart, ordering, accounts, catering, contact, REST backend, MongoDB, authentication, and admin dashboard. The brand is warm Indian homemade food with the tagline “The taste of love……”.

## Architecture decisions
- React frontend with React Router and Axios, FastAPI REST API, MongoDB via Motor.
- JWT stored in an httpOnly cookie; bcrypt password hashing and role checks for admins.
- Backend recalculates order prices from current available menu items and stores item snapshots.
- Menu and inquiries are database-backed; payment remains a future-ready pending status.

## Personas
- Local customer ordering fresh vegetarian meals or recurring tiffin.
- Host planning catering for a gathering.
- Navyug administrator managing dishes, orders, and inquiries.

## Core requirements
- Responsive branded storefront, database menu, category filters, cart, checkout, customer auth/order history, catering/contact forms, protected admin workflows.

## Implemented — 2026-02-18
- Replaced starter API with menu seed data, auth, admin setup, orders, catering, contact, and status endpoints.
- Built responsive customer experience with Navyug brand system, selected food photography, menu/cart/checkout, confirmation, tiffin, catering, and contact screens.
- Built authenticated admin operations for orders, catering, and contact inquiry status management.

## Prioritized backlog
- P0: customer order history/profile screen; menu CRUD form in admin; refresh-token rotation and rate limiting.
- P1: payment provider, tiffin subscription plans, notifications, image upload.
- P2: coupons, reviews, delivery tracking, WhatsApp integration.

## Next tasks
- Add protected customer account route showing profile and past orders.
- Add admin menu editor and inquiry internal notes.
- Add automated API and browser regression coverage.