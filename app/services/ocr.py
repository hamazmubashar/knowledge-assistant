import io
from typing import Protocol

from app.core.config import settings


class OcrProvider(Protocol):
    def extract_text(self, png: bytes) -> str: ...


class TesseractOcr:
    """Local fallback for development."""

    def extract_text(self, png: bytes) -> str:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(io.BytesIO(png)))


class TextractOcr:
    """Production provider. Implemented, NOT yet verified: needs AWS access."""

    def __init__(self):
        import boto3
        self.client = boto3.client("textract", region_name="us-east-1")

    def extract_text(self, png: bytes) -> str:
        resp = self.client.detect_document_text(Document={"Bytes": png})
        return "\n".join(b["Text"] for b in resp["Blocks"] if b["BlockType"] == "LINE")


def get_ocr_provider() -> OcrProvider:
    if settings.ocr_provider == "tesseract":
        return TesseractOcr()
    if settings.ocr_provider == "textract":
        return TextractOcr()
    raise ValueError(f"Unknown OCR provider: {settings.ocr_provider}")