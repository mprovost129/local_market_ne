from __future__ import annotations

"""
Central throttle policy for Local Market NE.

Use these rules across the app so launch-hardening changes are consistent.
The throttle fingerprint includes (best-effort) client IP, short UA prefix, and user id (if authenticated).
"""

from core.throttle import ThrottleRule

# Auth / account
AUTH_LOGIN = ThrottleRule(key_prefix="auth:login", limit=10, window_seconds=60)
AUTH_REGISTER = ThrottleRule(key_prefix="auth:register", limit=6, window_seconds=60)
AUTH_PASSWORD_RESET = ThrottleRule(key_prefix="auth:pwreset", limit=6, window_seconds=60)

# Cart / checkout
# Cart mutations can be abused (inventory probing, spam). Keep conservative.
CART_MUTATE = ThrottleRule(key_prefix="cart:mutate", limit=20, window_seconds=60)

# Checkout start is high-impact (payment attempts). Keep stricter.
CHECKOUT_START = ThrottleRule(key_prefix="checkout:start", limit=6, window_seconds=60)

# Order fulfillment selection (pickup/delivery/shipping) before payment.
ORDER_SET_FULFILLMENT = ThrottleRule(key_prefix="orders:set_fulfillment", limit=20, window_seconds=60)

# Buyer delivery/pickup confirmation after seller marks ready/shipped.
BUYER_CONFIRM_FULFILLMENT = ThrottleRule(key_prefix="orders:buyer_confirm", limit=10, window_seconds=60)

# Buyer marks off-platform payment as sent (informational)
BUYER_OFFPLATFORM_SENT = ThrottleRule(key_prefix="orders:offplatform_sent", limit=8, window_seconds=60)

# Q&A
QA_THREAD_CREATE = ThrottleRule(key_prefix="qa:thread:create", limit=12, window_seconds=60)
QA_MESSAGE_REPLY = ThrottleRule(key_prefix="qa:reply", limit=20, window_seconds=60)
QA_REPORT = ThrottleRule(key_prefix="qa:report", limit=10, window_seconds=60)
QA_DELETE = ThrottleRule(key_prefix="qa:delete", limit=15, window_seconds=60)

# Reviews
REVIEW_CREATE = ThrottleRule(key_prefix="reviews:create", limit=8, window_seconds=60)
REVIEW_REPLY = ThrottleRule(key_prefix="reviews:reply", limit=20, window_seconds=60)

# Refunds / sensitive actions
REFUND_REQUEST = ThrottleRule(key_prefix="refunds:request", limit=4, window_seconds=60)
REFUND_TRIGGER = ThrottleRule(key_prefix="refunds:trigger", limit=4, window_seconds=60)

# Seller listing mutations (activate/publish/upload)
SELLER_MUTATE = ThrottleRule(key_prefix="seller:mutate", limit=25, window_seconds=60)


# Category dependent dropdown / lookup
CATEGORY_LOOKUP = ThrottleRule(key_prefix="category:lookup", limit=120, window_seconds=60)


# Support / contact
CONTACT_SUBMIT = ThrottleRule(key_prefix="support:contact", limit=6, window_seconds=60)

# Waitlist (Coming Soon / marketing)
WAITLIST_SIGNUP = ThrottleRule(key_prefix="waitlist:signup", limit=6, window_seconds=60)

# Refund decisions (approve/decline)
REFUND_DECIDE = ThrottleRule(key_prefix="refunds:decide", limit=10, window_seconds=60)
