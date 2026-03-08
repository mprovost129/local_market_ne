from __future__ import annotations

import base64
import io


def qr_data_uri(data: str) -> str | None:
    """Return a data: URI PNG QR code for the provided data.

    Used for storefront/off-platform checkout QR codes.
    Safe to call with blank/None.
    """
    data = (data or "").strip()
    if not data:
        return None
    try:
        import qrcode

        img = qrcode.make(data)
        buf = io.BytesIO()
        img.save(buf)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None
