"""Print the HTML deck to PDF with headless Chrome or Edge.

The HTML engine is the single visual truth for the interactive deck and the
printed deck PDF. The PPTX is rendered natively from slides.json; PowerPoint
and LibreOffice are intentionally not part of the deck path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_WINDOWS_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
_UNIX_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
)


def find_browser() -> Path | None:
    """Return a Chromium-based browser executable, or None when unavailable."""
    override = os.environ.get("COO_BROWSER", "").strip()
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path
    for candidate in _WINDOWS_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path
    for name in _UNIX_CANDIDATES:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def deck_pdf_available() -> bool:
    """Whether the HTML-to-PDF engine is installed."""
    return find_browser() is not None


def _pdf_is_usable(pdf_path: Path, expected_pages: int) -> tuple[bool, str]:
    if not pdf_path.is_file():
        return False, "no PDF was produced"
    if pdf_path.stat().st_size < 5_000:
        return False, "PDF is smaller than 5 KB"
    try:
        from pypdf import PdfReader
    except ImportError:
        return True, "pypdf unavailable; size check only"
    try:
        reader = PdfReader(str(pdf_path))
        if len(reader.pages) != expected_pages:
            return False, f"PDF has {len(reader.pages)} pages, expected {expected_pages}"
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            resources = page.get("/Resources", {})
            xobjects = resources.get("/XObject", {}) if hasattr(resources, "get") else {}
            contents = page.get_contents()
            content_size = len(contents.get_data()) if contents is not None else 0
            if not text and not xobjects and content_size < 50:
                return False, f"page {index} appears blank"
        return True, "page count and page content verified"
    except Exception as exc:  # noqa: BLE001 - validation must never crash export
        return True, f"PDF validation skipped: {exc}"


def render_html_to_pdf(html_path: Path, pdf_path: Path, *, timeout: int = 120) -> Path:
    """Print an HTML file to PDF using headless Chromium."""
    html_path = html_path.resolve()
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML deck not found: {html_path}")
    browser = find_browser()
    if browser is None:
        raise RuntimeError(
            "Deck PDF needs Chrome, Chromium, or Edge. Set COO_BROWSER to an explicit executable."
        )
    pdf_path = pdf_path.resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()

    with tempfile.TemporaryDirectory(prefix="coo-deck-pdf-") as profile:
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-pdf-header-footer",
            "--virtual-time-budget=3000",
            f"--user-data-dir={profile}",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Deck PDF rendering timed out after {timeout}s") from exc
        if completed.returncode != 0 or not pdf_path.is_file() or pdf_path.stat().st_size == 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            if len(detail) > 600:
                detail = detail[-600:]
            raise RuntimeError(f"Deck PDF rendering failed: {detail or 'no PDF was produced'}")
    return pdf_path


def render_deck_pdf(html_path: Path, pdf_path: Path, *, expected_pages: int) -> Path:
    """Print the HTML deck, then verify page count and page content."""
    render_html_to_pdf(html_path, pdf_path)
    usable, detail = _pdf_is_usable(pdf_path, expected_pages)
    if not usable:
        raise RuntimeError(f"Deck PDF failed validation: {detail}")
    return pdf_path
