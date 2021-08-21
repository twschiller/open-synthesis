"""Analysis of Competing Hypotheses donation utility methods."""
from io import BytesIO

import qrcode
from django.utils.http import urlencode
from qrcode.image.svg import SvgPathImage


def bitcoin_donation_url(site_name, address):
    """Return a Bitcoin donation URL for DONATE_BITCOIN_ADDRESS or None."""
    if address:
        msg = "Donate to {}".format(site_name)
        url = "bitcoin:{}?{}".format(address, urlencode({"message": msg}))
        return url
    else:
        return None


def make_qr_code(
    message, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4
):
    """Return an in-memory SVG QR code containing the given message."""
    # https://pypi.python.org/pypi/qrcode/5.3
    # qrcode.constants.ERROR_CORRECT_M means about 15% or less errors can be corrected.
    code = qrcode.QRCode(
        version=1,
        error_correction=error_correction,
        box_size=box_size,
        border=border,
    )
    code.add_data(message)
    code.make(fit=True)
    img = code.make_image(image_factory=SvgPathImage)
    raw = BytesIO()
    img.save(raw)
    raw.flush()
    return raw
