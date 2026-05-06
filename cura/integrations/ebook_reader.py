"""E-book reader integration — EPUB and PDF parsing for read-aloud.

pip install EbookLib PyMuPDF

Extracts text from EPUB and PDF files, chunks into readable passages
for TTS delivery during check-ins.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class EbookParser:
    """Parse e-books into text chunks for the BookReader enrichment.

    Supports EPUB (via EbookLib) and PDF (via PyMuPDF).
    Falls back gracefully if dependencies aren't installed.
    """

    @staticmethod
    def parse_epub(path: str | Path) -> tuple[str, str]:
        """Extract title and full text from an EPUB file.

        Returns (title, text).
        """
        try:
            import ebooklib
            from ebooklib import epub
            from html.parser import HTMLParser
        except ImportError:
            logger.warning("ebooklib not installed — pip install EbookLib")
            return ("", "")

        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts: list[str] = []

            def handle_data(self, data: str):
                self.parts.append(data)

        book = epub.read_epub(str(path))
        title = book.get_metadata("DC", "title")
        title_str = title[0][0] if title else Path(path).stem

        extractor = _TextExtractor()
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            extractor.feed(item.get_content().decode("utf-8", errors="replace"))

        return (title_str, " ".join(extractor.parts))

    @staticmethod
    def parse_pdf(path: str | Path) -> tuple[str, str]:
        """Extract title and full text from a PDF file.

        Returns (title, text).
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF not installed — pip install PyMuPDF")
            return ("", "")

        doc = fitz.open(str(path))
        title = doc.metadata.get("title", "") or Path(path).stem
        pages = [page.get_text() for page in doc]
        doc.close()
        return (title, " ".join(pages))

    @staticmethod
    def parse(path: str | Path) -> tuple[str, str]:
        """Auto-detect format and parse."""
        p = Path(path)
        if p.suffix.lower() == ".epub":
            return EbookParser.parse_epub(p)
        elif p.suffix.lower() == ".pdf":
            return EbookParser.parse_pdf(p)
        elif p.suffix.lower() == ".txt":
            text = p.read_text(encoding="utf-8", errors="replace")
            return (p.stem, text)
        else:
            logger.warning("Unsupported format: %s", p.suffix)
            return ("", "")
