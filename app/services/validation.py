import pymupdf


def validate_pdf(filename: str, data: bytes, max_bytes: int) -> None:
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are accepted")
    if not data:
        raise ValueError("File is empty")
    if len(data) > max_bytes:
        raise ValueError("File exceeds the size limit")
    if not data.startswith(b"%PDF-"):
        raise ValueError("File is not a valid PDF")
    try:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise ValueError("Password-protected PDFs are not supported")
            if pdf.page_count == 0:
                raise ValueError("PDF has no pages")
    except ValueError:
        raise
    except Exception:
        raise ValueError("PDF could not be read")