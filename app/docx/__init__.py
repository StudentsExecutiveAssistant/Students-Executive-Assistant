"""Генерація та валідація документів Word (.docx)."""
from app.docx.builder import PAGE_SIZE, build_docx, new_document, preview_text, with_appendix_num
from app.docx.validator import check, check_docx, format_issues, text_issues

__all__ = [
    "PAGE_SIZE",
    "build_docx",
    "check",
    "check_docx",
    "format_issues",
    "new_document",
    "preview_text",
    "text_issues",
    "with_appendix_num",
]
