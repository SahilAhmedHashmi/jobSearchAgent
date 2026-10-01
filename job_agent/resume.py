"""Resume ingestion and transparent, conservative local profiling."""
import hashlib
import re
from pathlib import Path
from datetime import date

SKILLS = ("python", "sql", "excel", "power bi", "tableau", "pandas", "numpy",
          "pytorch", "tensorflow", "aws", "azure", "docker", "kubernetes", "git",
          "javascript", "typescript", "react", "node.js", "java", "c++", "c#",
          "machine learning", "data analysis", "data visualization", "etl",
          "project management", "salesforce", "linux", "html", "css")
ROLE_HINTS = ("data analyst", "business analyst", "software engineer", "software developer",
              "data scientist", "machine learning engineer", "backend developer", "frontend developer",
              "full stack developer", "devops engineer", "cloud engineer", "project manager",
              "product manager", "accountant", "teacher", "research assistant")
RELATED_ROLES = {
    "data analyst": ("reporting analyst", "mis analyst", "business intelligence analyst",
                      "operations analyst", "workforce analyst", "data quality analyst"),
    "reporting analyst": ("mis analyst", "data analyst", "business intelligence analyst"),
    "mis analyst": ("reporting analyst", "operations analyst", "data analyst"),
}


def read_resume(path: str) -> tuple[str, str]:
    p = Path(path)
    if not p.is_file() or p.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Resume missing or larger than 20 MB")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    suffix = p.suffix.lower()
    if suffix == ".txt":
        content = p.read_text(encoding="utf-8-sig")
    elif suffix == ".pdf":
        from pypdf import PdfReader
        content = "\n".join(page.extract_text() or "" for page in PdfReader(str(p)).pages)
    elif suffix == ".docx":
        from docx import Document
        doc = Document(str(p))
        content = "\n".join([x.text for x in doc.paragraphs] +
                            [cell.text for table in doc.tables for row in table.rows for cell in row.cells])
    else:
        raise ValueError("Use a TXT, PDF, or DOCX resume")
    if len(content.strip()) < 20:
        raise ValueError("Resume text is too short; scanned PDFs need OCR before use")
    return content, digest


def profile(text: str, digest: str) -> dict:
    lower = text.lower()
    skills = [s for s in SKILLS if re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", lower)]
    titles = [r for r in ROLE_HINTS if re.search(r"(?<!\w)" + re.escape(r) + r"(?!\w)", lower)]
    years = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:\+\s*)?years?\s+(?:of\s+)?experience\b", lower)
    lines = [s.strip() for s in text.splitlines() if s.strip()]
    experience_entries = []
    for line in lines:
        match = re.search(r"(?P<title>[A-Za-z][A-Za-z /&-]{2,80})\s*[|–—-]\s*[^\n]{0,100}?\b(?P<start>20\d{2})\b[^\n]{0,30}?\b(?P<end>20\d{2}|present|current)\b", line, re.I)
        if match:
            start = int(match.group("start"))
            end_text = match.group("end").lower()
            end = date.today().year if end_text in ("present", "current") else int(end_text)
            if end >= start:
                experience_entries.append({"title": match.group("title").strip(), "start_year": start,
                                           "end_year": end, "years": round(end - start + 0.5, 1), "source": line[:220]})
    inferred_years = max((x["years"] for x in experience_entries), default=None)
    if experience_entries:
        inferred_years = round(sum(x["years"] for x in experience_entries), 1)
    elif years:
        inferred_years = float(years.group(1))
    suggested = list(titles[:12])
    for title in list(suggested):
        suggested.extend(RELATED_ROLES.get(title, ()))
    suggested = list(dict.fromkeys(suggested))[:20]
    return {"resume_sha256": digest, "headline": lines[0][:120] if lines else "",
            "skills": skills, "role_suggestions": suggested,
            "experience_years": inferred_years, "experience_basis": "dated resume roles" if experience_entries else ("explicit resume statement" if years else "unknown"),
            "experience_entries": experience_entries,
            "related_role_suggestions": [x for x in suggested if x not in titles],
            "education_evidence": [s[:220] for s in lines if re.search(r"\b(mca|b\.sc|btech|mtech|mba|bachelor|master|phd)\b", s, re.I)][:12],
            "resume_excerpt": text[:2500], "method": "local keyword detection; user must review"}
