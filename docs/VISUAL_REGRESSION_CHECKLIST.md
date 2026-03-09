# Visual Regression Checklist

Use this checklist before deploys that include UI/theme/template changes.

## Setup
- Run with latest code and collected static assets.
- Test in desktop and mobile widths.
- Test in both light and dark themes.
- Test as anonymous, consumer, seller, and owner/admin users.

## Flow 1: Buyer Path
- Home page loads with correct brand colors, spacing, and readable contrast.
- Product/service cards show consistent button styles and hover states.
- Product detail page renders gallery, pricing, quantity, and add-to-cart controls correctly.
- Cart page keeps per-seller grouping, tip updates, and totals visually consistent.
- Checkout review page reflects quantities and seller grouping correctly.
- Checkout status/messages are readable and use the correct button hierarchy.

## Flow 2: Seller Path
- Seller dashboard cards, tables, and empty states use consistent spacing and button variants.
- Listings page bulk actions and row actions are aligned and readable.
- New listing form stepper is usable on mobile and desktop.
- Validation errors return to the correct section and are easy to locate.
- Image management page follows theme classes (no legacy dark/black badges/buttons).
- Storefront preview shows listing cards and seller identity data correctly.

## Flow 3: Admin/Ops Path
- Admin dashboard KPI cards and tables are visually consistent.
- Ops pages (health, reconciliation, webhooks, refunds, support) keep consistent table/card styling.
- Filters, pagination, and action buttons are visible and aligned on mobile and desktop.
- Empty/loading/error states always include a clear next action.

## Accessibility Spot Checks
- Keyboard tab order is logical on top flows.
- Focus outlines are visible on interactive controls.
- Contrast is acceptable for body text, muted text, badges, and buttons in both themes.
- Form fields have visible labels and error cues.

## Sign-off
- No clipped/overlapping text in navbar/footer.
- No broken images/icons/logos in primary surfaces.
- No stale/garbled copy on high-traffic pages.
- Capture screenshots for:
  - Home
  - Product detail
  - Cart
  - Checkout review
  - Seller dashboard
  - Seller listings
  - Admin dashboard
  - Ops reconciliation
