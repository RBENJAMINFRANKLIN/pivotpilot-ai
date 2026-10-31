"""Upload validation for resumes. Files are untrusted: we check magic bytes, size,
structure and decompressed size before any parser touches them."""

import io
import zipfile
from dataclasses import dataclass

from app.config import get_settings


class FileRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ValidatedFile:
    kind: str  # pdf | docx
    data: bytes
    filename: str


DOCX_MAIN = "word/document.xml"


def sanitize_filename(name: str | None) -> str:
    name = (name or "resume").replace("\\", "/").split("/")[-1]
    safe = "".join(c for c in name if c.isalnum() or c in "._- ")[:120].strip()
    return safe or "resume"


def validate_resume_upload(filename: str | None, data: bytes) -> ValidatedFile:
    s = get_settings()
    if not data:
        raise FileRejected("EMPTY_FILE", "The file is empty.")
    if len(data) > s.max_upload_bytes:
        raise FileRejected("FILE_TOO_LARGE", f"Files must be {s.max_upload_bytes // (1024 * 1024)} MB or smaller.")
    fname = sanitize_filename(filename)
    lower = fname.lower()

    if data[:5] == b"%PDF-":
        if not lower.endswith(".pdf"):
            raise FileRejected("EXTENSION_MISMATCH", "The file contents do not match its extension.")
        return ValidatedFile("pdf", data, fname)

    if data[:4] == b"PK\x03\x04":
        if not lower.endswith(".docx"):
            raise FileRejected("UNSUPPORTED_TYPE", "Only PDF and DOCX files are supported.")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
                if DOCX_MAIN not in names or "[Content_Types].xml" not in names:
                    raise FileRejected("MALFORMED_FILE", "This does not look like a valid Word document.")
                if any(n.lower().endswith("vbaproject.bin") for n in names):
                    raise FileRejected("MACROS_NOT_ALLOWED", "Documents containing macros are not accepted.")
                total = sum(i.file_size for i in zf.infolist())
                if total > s.max_docx_uncompressed_bytes:
                    raise FileRejected("FILE_TOO_LARGE", "The document expands to an unsafe size.")
                ctypes = zf.read("[Content_Types].xml").decode("utf-8", "replace")
                if "macroEnabled" in ctypes:
                    raise FileRejected("MACROS_NOT_ALLOWED", "Documents containing macros are not accepted.")
        except zipfile.BadZipFile as e:
            raise FileRejected("MALFORMED_FILE", "The document could not be opened.") from e
        return ValidatedFile("docx", data, fname)

    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise FileRejected("UNSUPPORTED_TYPE", "Old .doc files are not supported. Save as DOCX or PDF.")
    raise FileRejected("UNSUPPORTED_TYPE", "Only PDF and DOCX files are supported.")
