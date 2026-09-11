# Navyug Authentication Testing

1. Use the setup key in `/app/memory/test_credentials.md` to create one admin through `POST /api/admin/setup`.
2. Register a customer through `POST /api/auth/register` and verify the response omits `password_hash`.
3. Login with the customer and call `GET /api/auth/me` using the returned cookie.
4. Verify `/api/orders/all` rejects customers and accepts the admin cookie.
5. Verify logout clears the session and `/api/auth/me` returns 401.