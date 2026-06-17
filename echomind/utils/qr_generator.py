"""QR code generator utility for shareable memoir links."""

import os
import logging

import qrcode

logger = logging.getLogger(__name__)


class QRGenerator:
    """Generate a PNG QR code pointing at a given URL."""

    def generate(self, url: str, output_path: str) -> str:
        """Generate and save a QR code image. Returns the output path."""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="#1a1a2e", back_color="white")
            img.save(output_path)
            return output_path
        except Exception as exc:  # pragma: no cover
            logger.error("QR generation failed: %s", exc)
            raise
