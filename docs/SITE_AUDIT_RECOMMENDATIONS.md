# Local Market NE - Site Audit & Recommendations (Feb 5, 2026)

## Scope
High‑level UX, content, and technical review across major user flows (buyer, seller, admin, legal, payments).

---
## Global UI/UX
- Establish a single primary CTA per page (avoid competing actions).
- Normalize heading hierarchy (one H1 per page; section headers H2/H3).
- Reduce card metadata density (seller + category + badges + ratings is heavy).
- Ensure consistent button hierarchy (primary/danger/secondary usage).

## Home Page
- Hero: one primary CTA (Browse All or Start Selling) and a smaller secondary.
- Add short value proposition under hero (“products & service files from vetted makers”).
- Trending/Just Added/Featured: add category filter chips for quick discovery.
- Top Sellers: replace generic link with seller cards (avatar, rating, sales count).
- Ensure above‑the‑fold content shows 1–2 real products with ratings to build trust.

## Product Listing Pages (All Products / Models / Files)
- Add “Ships from” for physical models (if data exists) and lead time.
- Add sort rationale tooltips (Trending vs Top Rated).

## Product Detail Page
- Include a sticky purchase panel for desktop.
- Surface seller response time or fulfillment expectations.
- Add a mini FAQ accordion under specs.
- Show related items by same seller and same category.

## Cart
- Show a summary of service license type and file formats inline.
- Show fee breakdown (platform fee visible to seller only).

## Checkout
- Add order preview with thumbnails.
- Clarify that orders are delivered instantly post‑payment.

## Seller Dashboard / Listings
- Add a progress checklist per listing (Images ✓, Specs ✓, Assets ✓, Active ✓).
- Add bulk actions for activate/deactivate.

## Seller Orders / Fulfillment
## Payments / Stripe Payouts
- Add a plain‑language summary: “You can sell when all three are green.”
- Display last payout date if available.

## Legal
- Add plain‑language TL;DR at top of Terms and Refund.

---
## Priority (Next 2–4 weeks)
1) Home hero CTA clarity + Top Sellers real cards
2) Product detail “What you get” + license clarity
3) Seller listing checklist
4) Cart/checkout clarity for service delivery

---
## Optional Enhancements
- Add “Collections” and “Bundles” browsing.
- Seller storefront customization (banner + featured items).
- Reviews: highlight photo reviews or “verified purchase” badges.

---

## Seller + Consumer UX Improvements (Post-Pack CA)

### Seller flow (highest ROI)
1. **Seller onboarding checklist widget** (always visible in seller dashboard)
   - Email verified ✅
   - Stripe connected ✅
   - Payouts ready ✅
   - Profile/storefront completed ✅ (location/radius, shop bio, banner)
   - First listing published ✅
   - First order fulfilled ✅

2. **Listing creation as a 3-step wizard**
   - Step 1: Type (Product/Service), Category/Subcategory (dynamic), Title/Price, Quantity vs Made-to-order
   - Step 2: Fulfillment (pickup/delivery/shipping) + fees + lead time
   - Step 3: Photos + description + publish toggle

3. **Pre-publish validation panel**
   - Show blocking issues (missing image, missing fulfillment options, not Stripe-ready)
   - Show warnings (no description, no pickup instructions)

4. **Seller Orders “Fulfillment Queue” defaults**
   - Default filter = Unfulfilled
   - One-click actions: Mark Ready / Mark Shipped / Add Tracking / Mark Delivered
   - Inline customer shipping snapshot display (no extra click)

### Consumer flow
1. **Better browse primitives**
   - Sticky filter summary (“3 filters active”) + one-click clear
   - Sort pill buttons (Near me / New / Top / Trending)

2. **Trust + conversion**
   - Clear fulfillment badges (Pickup / Delivery / Shipping) + “From <city>” on cards
   - “Verified seller” badge when Stripe-ready + email-verified
   - Add “ETA” line for made-to-order lead times

3. **Checkout UX**
   - Single review page with a clear breakdown:
     - Subtotal, delivery/shipping, tax, marketplace fee note, tip
   - Strong success page with next actions:
     - Track order, message seller, leave review later

### Visual / UI polish
1. **Design tokens**
   - Add CSS variables for spacing, border radius, shadow tiers, and brand color.

2. **Cards + tables consistency**
   - `lm-card` for all card surfaces (padding, border, hover)
   - `lm-table` wrapper everywhere (already started)

3. **Empty states**
   - Keep current component but add:
     - icon support
     - “what to do next” bullet list

4. **Mobile improvements**
   - Collapse long sidebar category lists into searchable modal
   - Sticky bottom bar for Cart + Messages on mobile
