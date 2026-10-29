from io import BytesIO
from pathlib import PurePosixPath

from pypdf import PdfReader
from pypdf.errors import PyPdfError


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARACTERS = 1_000_000
MAX_PDF_PAGES = 200


class DocumentReadError(Exception):
    pass


def read_document(filename, content):
    safe_name = PurePosixPath(
        filename.replace("\\", "/")
    ).name

    extension = PurePosixPath(safe_name).suffix.lower()

    if extension not in {".txt", ".md", ".pdf"}:
        raise DocumentReadError(
            "Supported formats: .txt, .md and .pdf."
        )

    if not content:
        raise DocumentReadError("The file is empty.")

    if len(content) > MAX_FILE_BYTES:
        raise DocumentReadError("Maximum file size is 10 MiB.")

    pages = []
    page_count = None

    if extension in {".txt", ".md"}:
        try:
            text = content.decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            raise DocumentReadError(
                "Text and Markdown files must use UTF-8 encoding."
            ) from None

        if "\x00" in text:
            raise DocumentReadError(
                "The file appears to contain binary data."
            )

    else:
        try:
            reader = PdfReader(BytesIO(content))

            if reader.is_encrypted:
                raise DocumentReadError(
                    "Encrypted PDFs are not supported."
                )

            page_count = len(reader.pages)

            if page_count > MAX_PDF_PAGES:
                raise DocumentReadError(
                    "Maximum PDF length is 200 pages."
                )

            parts = []
            character_position = 0

            for page_number, page in enumerate(
                reader.pages, start=1
            ):
                page_text = (page.extract_text() or "").strip()

                if not page_text:
                    continue

                if parts:
                    character_position += 2

                start = character_position
                character_position += len(page_text)

                if character_position > MAX_TEXT_CHARACTERS:
                    raise DocumentReadError(
                        "Extracted text exceeds the character limit."
                    )

                pages.append({
                    "page_number": page_number,
                    "char_start": start,
                    "char_end": character_position
                })

                parts.append(page_text)

            text = "\n\n".join(parts)

        except (PyPdfError, ValueError, OSError):
            raise DocumentReadError(
                "Could not extract text from this PDF."
            ) from None

    if not text.strip():
        raise DocumentReadError(
            "No readable text found. Scanned PDFs may need OCR."
        )

    if len(text) > MAX_TEXT_CHARACTERS:
        raise DocumentReadError(
            "Extracted text exceeds the character limit."
        )

    return {
        "filename": safe_name,
        "format": extension.removeprefix("."),
        "text": text,
        "page_count": page_count,
        "pages": pages
    }