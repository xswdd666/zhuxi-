"""Local upload storage and deliberately small, traceable document parsing."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.db import UPLOADS_DIR


TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
PDF_EXTENSION = ".pdf"
DOCX_EXTENSION = ".docx"
DOC_EXTENSION = ".doc"
CHUNK_SIZE = 1200


def safe_filename(name: str | None) -> str:
    candidate = Path(name or "upload").name
    candidate = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", candidate)
    return candidate or "upload"


async def save_upload(project_id: str, upload: UploadFile) -> tuple[Path, str, str]:
    """Save a file under its project and return path, normalized type, and display name."""
    display_name = safe_filename(upload.filename)
    extension = Path(display_name).suffix.lower()
    file_type = extension.lstrip(".") or "unknown"
    target_dir = UPLOADS_DIR / project_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid4().hex}_{display_name}"
    content = await upload.read()
    target.write_bytes(content)
    return target, file_type, display_name


def parse_file(path: Path, file_type: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Return parse status and (locator, content, source_type) chunks; never performs OCR."""
    extension = f".{file_type.lower()}"
    if extension in TEXT_EXTENSIONS:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="gb18030")
            except UnicodeDecodeError:
                return "parse_failed: 文本编码不受支持，请使用 UTF-8 保存。", []
        return "parsed", _text_chunks(text, "文本片段")
    if extension == PDF_EXTENSION:
        return _parse_pdf(path)
    if extension == DOCX_EXTENSION:
        return _parse_docx(path)
    if extension == DOC_EXTENSION:
        return _parse_doc(path)
    if extension in IMAGE_EXTENSIONS:
        return "saved_image: 未启用 OCR/视觉模型，已保存待人工观察。", [("图片", "图片已安全保存，内容需人工核实。", "image")]
    return "parse_failed: 仅支持 TXT、MD、PDF、DOCX、DOC、JPG、PNG。", []


def _parse_pdf(path: Path) -> tuple[str, list[tuple[str, str, str]]]:
    try:
        from pypdf import PdfReader  # optional runtime dependency
    except ImportError:
        return "parse_failed: 未安装 pypdf，暂无法提取 PDF 文本。", []
    try:
        reader = PdfReader(str(path))
        chunks: list[tuple[str, str, str]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            chunks.extend(_text_chunks(text, f"第 {page_number} 页"))
        if not chunks:
            return "parse_failed: PDF 未提取到文本（可能是扫描件；本 MVP 不做 OCR）。", []
        return "parsed", chunks
    except Exception as exc:
        return f"parse_failed: PDF 文本提取失败（{type(exc).__name__}）。", []


def _parse_docx(path: Path) -> tuple[str, list[tuple[str, str, str]]]:
    try:
        from docx import Document  # optional runtime dependency
    except ImportError:
        return "parse_failed: 未安装 python-docx，暂无法提取 DOCX 文本。", []
    try:
        document = Document(str(path))
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text and p.text.strip()]
        if not paragraphs:
            return "parse_failed: DOCX 未提取到文本内容。", []
        text = "\n\n".join(paragraphs)
        return "parsed", _text_chunks(text, "DOCX 文本片段")
    except Exception as exc:
        return f"parse_failed: DOCX 文本提取失败（{type(exc).__name__}）。", []


def _parse_doc(path: Path) -> tuple[str, list[tuple[str, str, str]]]:
    """Best-effort parsing of legacy .doc files using Word COM automation on Windows."""
    try:
        import win32com.client as win32
    except ImportError:
        return "parse_failed: 旧版 DOC 需要 Windows + Word 或转换为 DOCX 后上传。", []
    temp_txt = path.with_suffix(".txt")
    word = None
    try:
        word = win32.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(path.resolve()), ReadOnly=True)
        try:
            doc.SaveAs(str(temp_txt.resolve()), FileFormat=7)  # 7 = wdFormatText
        finally:
            doc.Close(SaveChanges=False)
        if not temp_txt.exists():
            return "parse_failed: DOC 未能转换为文本。", []
        text = _read_text_with_fallback(temp_txt)
        if not text.strip():
            return "parse_failed: DOC 未提取到文本内容。", []
        return "parsed", _text_chunks(text, "DOC 文本片段")
    except Exception as exc:
        return f"parse_failed: DOC 文本提取失败（{type(exc).__name__}）；建议转换为 DOCX 后上传。", []
    finally:
        try:
            if temp_txt.exists():
                temp_txt.unlink()
        finally:
            if word is not None:
                try:
                    word.Quit(SaveChanges=-1)
                except Exception:
                    pass


def _read_text_with_fallback(path: Path) -> str:
    """Read text trying UTF-8 first, then system fallback encodings."""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "cp936"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, "could not decode file with any supported encoding")


def _text_chunks(text: str, prefix: str) -> list[tuple[str, str, str]]:
    clean = text.strip()
    if not clean:
        return []
    pieces = [clean[i : i + CHUNK_SIZE].strip() for i in range(0, len(clean), CHUNK_SIZE)]
    return [(f"{prefix} {index}", piece, "text") for index, piece in enumerate(pieces, start=1) if piece]
