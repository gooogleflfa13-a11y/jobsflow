#!/usr/bin/env python3
"""Parse a resume into plain text (prefer .txt; PDF optional).

Prefer dropping a .txt into 00_Profile/resume_runtime/resume.txt — zero OCR cost.
PDF parse (pypdf) is optional convenience; not used in two-pass scoring.

Grafted from apply-bot's pdf-parse pattern.

apply-bot stores PDF → resume.txt via pdf-parse (Node).
Here we use pypdf (already in the env) and write into JobSearch_2026/00_Profile.

Usage:
  python3 -m tools.job_materials resume parse --pdf path/to/CV.pdf
  python3 -m tools.job_materials resume show
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.job_materials.paths import jobsearch_root


def profile_dir(root: Path | None = None) -> Path:
    return (root or jobsearch_root()) / "00_Profile"


def resume_txt_path(root: Path | None = None) -> Path:
    return profile_dir(root) / "resume_runtime" / "resume.txt"


def resume_meta_path(root: Path | None = None) -> Path:
    return profile_dir(root) / "resume_runtime" / "resume-meta.json"


def parse_pdf_text(pdf_path: Path) -> str:
    """Extract text from PDF using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf is required: pip install pypdf") from e

    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t.strip():
            parts.append(t.strip())
    text = "\n\n".join(parts)
    # light normalize
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def save_parsed_resume(
    pdf_path: Path,
    *,
    root: Path | None = None,
    also_copy_bullets: bool = False,
) -> dict[str, Any]:
    """Parse PDF and write resume_runtime/{resume.txt, resume-meta.json}."""
    root = root or jobsearch_root()
    pdf_path = pdf_path.expanduser().resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(str(pdf_path))
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are supported")

    text = parse_pdf_text(pdf_path)
    out_dir = profile_dir(root) / "resume_runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = resume_txt_path(root)
    meta_path = resume_meta_path(root)
    txt_path.write_text(text + ("\n" if text and not text.endswith("\n") else ""), encoding="utf-8")
    meta = {
        "sourceFile": str(pdf_path),
        "sourceName": pdf_path.name,
        "parsedAt": datetime.now(timezone.utc).isoformat(),
        "textLength": len(text),
        "engine": "pypdf",
        "note": "Grafted from apply-bot resume parse pattern (PDF → plain text).",
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if also_copy_bullets and text:
        # optional: append a pointer file, do not overwrite master_bullets
        pointer = out_dir / "README.md"
        pointer.write_text(
            "# resume_runtime\n\n"
            "Parsed CV text for agent/context use.\n\n"
            f"- Source: `{pdf_path.name}`\n"
            f"- Chars: {len(text)}\n"
            f"- Parsed: {meta['parsedAt']}\n\n"
            "Does **not** replace `master_bullets.md` or A–F bases fact-check.\n",
            encoding="utf-8",
        )
    return meta


def load_resume_meta(root: Path | None = None) -> dict[str, Any] | None:
    p = resume_meta_path(root)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_resume_text(root: Path | None = None) -> str:
    p = resume_txt_path(root)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")
