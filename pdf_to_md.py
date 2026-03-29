#!/usr/bin/env python3
"""Convert PDF to Markdown using MinerU Cloud API. Caches results for repeat reads.

Usage:
    python pdf_to_md.py <pdf_path> [--section NAME] [--full] [--no-cache] [--list]
    python pdf_to_md.py <pdf_path> --quick          # stdout summary (title+abstract+TOC)
    python pdf_to_md.py <pdf_path> --lang es         # force Spanish OCR

Output structure (in ~/.claude/tools/md_cache/<name>_<hash>/):
    paper.md          - Full document
    sections/
        _index.md     - TOC with metadata + section names + line counts
        00_abstract.md, 01_introduction.md, ...
        body.md       - Everything before References/Bibliography
        appendix.md   - Appendix + supplementary material

Default behavior: prints path to sections/_index.md (Claude reads TOC first).
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

# --- Configuration ---
CACHE_DIR = Path.home() / ".claude" / "tools" / "md_cache"
CONFIG_FILE = Path.home() / ".claude" / "tools" / "mineru_config.json"
MINERU_API_URL = "https://mineru.net/api/v4"
POLL_INTERVAL = 3
SPLIT_VERSION = 3  # v3: improved abstract extraction, accurate line counts, better image/author detection
MAX_SECTIONS_BEFORE_MERGE = 12

# Section detection patterns
REFERENCES_PATTERN = re.compile(
    r"^#+\s*(References|Bibliography|Works Cited"
    r"|Referencias|Bibliografía|Obras Citadas"              # es
    r"|Referências|Bibliografia"                              # pt
    r"|Références|Bibliographie"                              # fr
    r"|Referenzen|Literaturverzeichnis|Literatur"             # de
    r"|Riferimenti|Bibliografia"                              # it
    r")\s*$",
    re.IGNORECASE,
)
APPENDIX_PATTERN = re.compile(
    r"^#+\s*(Appendix|Appendices|Online Appendix|Supplementary|Supporting Information"
    r"|Apéndice|Apéndices|Anexo|Anexos"                      # es
    r"|Apêndice|Apêndices|Anexo|Anexos|Suplemento"           # pt
    r"|Annexe|Annexes|Matériel supplémentaire"                # fr
    r"|Anhang|Anhänge|Ergänzungsmaterial"                     # de
    r"|Appendice|Appendici|Materiale supplementare"           # it
    r")",
    re.IGNORECASE,
)

# Keywords that identify main sections (case-insensitive substring match)
MAIN_SECTION_KEYWORDS = [
    # --- English (economics) ---
    "introduction", "background", "context", "overview", "motivation", "preamble",
    "literature", "related work", "prior work", "previous work",
    "data", "sample", "measurement", "variables", "descriptive", "stylized facts",
    "model", "framework", "theory", "theoretical", "setup", "formulation",
    "empirical", "identification", "strategy", "methodology", "methods",
    "design", "approach", "estimation", "specification", "experiment",
    "instrumental", "first stage", "reduced form",
    "results", "findings", "estimates", "evidence", "analysis",
    "robustness", "sensitivity", "placebo", "falsification", "validation",
    "event study", "parallel trends", "balance",
    "discussion", "interpretation", "implications",
    "conclusion", "concluding", "summary", "final remarks",
    "welfare", "policy", "counterfactual", "simulation", "calibration",
    "structural estimation", "general equilibrium",
    "mechanism", "channels", "mediation", "transmission",
    "heterogeneity", "subgroup", "distributional", "treatment effect",
    "extensions", "generalization", "alternative",
    "references", "bibliography",
    "appendix", "appendices", "supplement", "online appendix", "supporting information",
    # --- Spanish (economics) ---
    "introducción", "introduccion", "contexto", "antecedentes", "motivación",
    "literatura", "trabajos previos", "trabajos relacionados",
    "datos", "muestra", "medición", "variables", "hechos estilizados",
    "modelo", "marco", "teoría", "teórico",
    "empíric", "identificación", "estrategia", "metodología", "métodos", "diseño",
    "instrumental", "primera etapa", "forma reducida",
    "resultados", "hallazgos", "estimación", "evidencia", "análisis",
    "robustez", "sensibilidad", "validación",
    "estudio de evento", "tendencias paralelas",
    "discusión", "interpretación", "implicaciones",
    "conclusi", "resumen", "observaciones finales",
    "bienestar", "política", "contrafactual", "simulación", "calibración",
    "estimación estructural", "equilibrio general",
    "mecanismo", "canales", "transmisión",
    "heterogeneidad", "subgrupo", "efecto del tratamiento",
    "extensiones", "generalización",
    "bibliografía", "obras citadas",
    "apéndice",
    # --- Portuguese (economics) ---
    "introdução", "motivação",
    "revisão da literatura", "trabalhos relacionados",
    "amostra", "medição", "variáveis",
    "modelo", "quadro", "teoria", "teórico",
    "identificação", "estratégia", "metodologia", "métodos", "desenho",
    "resultados", "achados", "estimação", "evidência", "análise",
    "robustez", "sensibilidade", "validação",
    "discussão", "interpretação", "implicações",
    "conclus", "resumo", "considerações finais",
    "mecanismo", "canais", "transmissão",
    "heterogeneidade",
    "extensões", "generalização",
    "referências",
    "apêndice", "suplemento",
    # --- French (economics) ---
    "résultats", "méthode", "méthodologie", "modèle", "cadre",
    "stratégie", "données", "échantillon",
    "littérature", "travaux", "revue",
    "théorie", "théorique", "empirique", "estimation",
    "robustesse", "sensibilité",
    "discussion", "interprétation",
    "conclusion", "résumé",
    "mécanisme", "hétérogénéité",
    "références", "bibliographie",
    "annexe",
    # --- German (economics) ---
    "einleitung", "hintergrund", "überblick", "motivation",
    "literatur",
    "daten", "stichprobe", "messung",
    "modell", "rahmen", "theorie", "theoretisch",
    "methodik", "methoden", "identifikation", "strategie",
    "ergebnisse", "befunde", "schätzung",
    "robustheit", "sensitivität",
    "diskussion", "interpretation",
    "schlussfolgerung", "zusammenfassung",
    "mechanismus",
    "referenzen", "literaturverzeichnis",
    "anhang",
    # --- Italian (economics) ---
    "introduzione", "contesto",
    "letteratura",
    "dati", "campione", "misurazione",
    "modello", "quadro", "teoria", "teorico",
    "metodologia", "metodi", "identificazione", "strategia",
    "risultati", "stime", "evidenza", "analisi",
    "robustezza", "sensibilità",
    "discussione", "interpretazione",
    "conclusione", "riassunto",
    "meccanismo", "eterogeneità",
    "riferimenti",
    "appendice",
]

# Roman numeral pattern at start of title (I., II., III., IV., ... XII.)
ROMAN_NUMERAL_RE = re.compile(
    r"^(I{1,3}|IV|VI{0,3}|IX|XI{0,2}|X{1,3})[\.\s]",
    re.IGNORECASE,
)

# Abstract detection starters
ABSTRACT_STARTERS = re.compile(
    r"^("
    # English
    r"We\s+(study|examine|analyze|estimate|investigate|document|show|find|use|develop|propose|present|build|exploit|identify|introduce|evaluate|consider|provide|revisit|extend|compare|measure|assess|construct|characterize|decompose|quantify|model|test|derive|embed|calibrate|simulate|formalize|explore|establish|uncover|disentangle)"
    r"|This\s+(paper|article|study|work|note|report|chapter)"
    r"|I\s+(study|examine|analyze|estimate|investigate|document|show|find|use|exploit|develop|propose|present|build|introduce|evaluate|consider|provide)"
    r"|Using\s+|Exploiting\s+|Leveraging\s+|In\s+this\s+(paper|article|study|work)"
    # Spanish
    r"|Este\s+(artículo|trabajo|estudio|documento)"
    r"|En\s+este\s+(trabajo|artículo|estudio)"
    r"|Estudiamos|Examinamos|Analizamos|Investigamos|Estimamos|Proponemos|Presentamos|Usamos|Evaluamos"
    # Portuguese
    r"|Este\s+(artigo|trabalho|estudo)"
    r"|Neste\s+(trabalho|artigo|estudo)"
    r"|Estudamos|Examinamos|Analisamos|Investigamos|Estimamos|Propomos|Apresentamos|Avaliamos"
    # French
    r"|Cet\s+(article|travail)|Cette\s+(étude|recherche)"
    r"|Dans\s+cet\s+(article|travail)|Dans\s+cette\s+(étude)"
    r"|Nous\s+(étudions|examinons|analysons|estimons|proposons|présentons|évaluons|montrons|utilisons)"
    # German
    r"|Diese\s+(Arbeit|Studie|Untersuchung)|Dieser\s+(Artikel|Beitrag)"
    r"|In\s+dieser\s+(Arbeit|Studie)|In\s+diesem\s+(Artikel|Beitrag)"
    r"|Wir\s+(untersuchen|analysieren|zeigen|schätzen|verwenden|präsentieren|entwickeln|bewerten)"
    # Italian
    r"|Questo\s+(articolo|lavoro|studio)"
    r"|In\s+questo\s+(articolo|lavoro|studio)"
    r"|Studiamo|Esaminiamo|Analizziamo|Stimiamo|Proponiamo|Presentiamo|Utilizziamo|Valutiamo"
    r")",
    re.IGNORECASE,
)


def get_api_key() -> str:
    key = os.environ.get("MINERU_API_KEY")
    if key:
        return key
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        key = cfg.get("api_key", "")
        if key:
            return key
    return ""


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def get_cache_dir(pdf_path: Path) -> Path:
    h = file_hash(pdf_path)
    name = slugify(pdf_path.stem) or pdf_path.stem
    return CACHE_DIR / f"{name}_{h}"


def get_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _normalize(text: str) -> str:
    """Strip accents and diacritics for fuzzy matching."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def slugify(text: str) -> str:
    """Convert text to a safe ASCII filename slug."""
    # Normalize unicode and strip combining marks (accents)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    return text[:60]


def clean_orphan_images(md_text: str) -> str:
    """Remove image references that point to local files we don't have."""
    return re.sub(r"!\[[^\]]*\]\((\.?/?(?:[Ii]mages?|[Ff]igures?)/[^)]+)\)", r"[image: \1]", md_text)


# --- Metadata extraction ---

def extract_metadata(md_text: str) -> dict:
    """Extract title, authors, and JEL codes from the markdown text."""
    lines = md_text.split("\n")
    meta = {"title": "", "authors": "", "jel": ""}

    # Title: first # header
    for line in lines[:50]:
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            meta["title"] = m.group(1).strip()
            break

    # Authors: look for lines near the title that have author-like patterns.
    # Collects multiple consecutive author lines (some papers split across lines).
    title_idx = None
    for i, line in enumerate(lines[:50]):
        if re.match(r"^#\s+", line):
            title_idx = i
            break

    if title_idx is not None:
        author_lines = []
        for line in lines[title_idx + 1 : title_idx + 20]:
            stripped = line.strip()
            if not stripped:
                # Blank line: if we already found author lines, stop collecting
                if author_lines:
                    break
                continue
            if stripped.startswith("#"):
                break
            # Stop if we hit abstract text
            if ABSTRACT_STARTERS.match(stripped):
                break
            # Stop if line looks like a date, JEL, keywords, or abstract header
            if re.match(r"^(JEL|Keywords|Palabras clave|Palavras[- ]chave|Mots[- ]clés|Schlüsselwörter|Parole chiave|Abstract|Resumen|Resumo|Résumé|ABSTRACT|\d{4})", stripped, re.IGNORECASE):
                break
            # Skip affiliation/institution lines (contain university, department, email, @)
            if re.search(r"(university|department|institute|faculty|school of|@|\.edu|\.ac\.|nber|cepr)", stripped, re.IGNORECASE):
                continue
            # Skip footnote markers or very short lines that aren't names
            if len(stripped) < 5 or re.match(r"^[\d\*†‡§]+$", stripped):
                continue
            # Skip document metadata / institutional headers
            if re.search(r"(Working Paper|Discussion Paper|Technical Report|Staff Report|National Bureau|Federal Reserve|World Bank|Central Bank|Bureau of|Ministry of|ISSN|ISBN|DOI|Volume|Issue|No\.\s*\d)", stripped, re.IGNORECASE):
                continue
            # Author lines: capitalized names, typically with commas/and, under ~200 chars
            words = stripped.split()
            if len(words) < 40 and re.search(r"[A-Z][a-zà-ÿ]+ [A-Z]", stripped):
                author_lines.append(stripped)
            elif author_lines:
                # Non-matching line after we started collecting → stop
                break

        if author_lines:
            meta["authors"] = "; ".join(author_lines) if len(author_lines) > 1 else author_lines[0]

    # JEL codes — handle English ("JEL codes:", "JEL classification:") and
    # non-English prefixes ("Clasificación JEL:", "Codes JEL:", etc.)
    jel_match = re.search(
        r"(?:"
        r"JEL\s*(?:codes?|classification)?"           # EN: "JEL", "JEL codes", "JEL classification"
        r"|Clasificaci[oó]n\s+JEL"                    # ES: "Clasificación JEL"
        r"|C[oó]digos?\s+JEL"                         # ES: "Códigos JEL"
        r"|Codes?\s+JEL"                              # FR: "Codes JEL"
        r"|JEL[- ]Klassifikation"                     # DE: "JEL-Klassifikation"
        r"|Classificazione\s+JEL"                     # IT: "Classificazione JEL"
        r"|Classifica[cç][aã]o\s+JEL"                # PT: "Classificação JEL"
        r")\s*:?\s*([A-Z]\d{1,2}(?:\s*[,;]\s*[A-Z]\d{1,2})*)",
        md_text[:5000], re.IGNORECASE
    )
    if jel_match:
        meta["jel"] = jel_match.group(1).strip()

    return meta


# --- Abstract extraction ---

def extract_abstract(md_text: str) -> tuple[str, str]:
    """Extract abstract from markdown. Returns (abstract_text, remaining_text).

    Looks for:
    1. Explicit "Abstract" header
    2. First substantial paragraph before the first section header
    """
    lines = md_text.split("\n")

    # Strategy 1: Explicit "Abstract" header
    for i, line in enumerate(lines):
        if re.match(r"^#+\s*(Abstracts?|Resumen|Resumo|Résumé|Zusammenfassung|Riassunto|Sommario|ABSTRACT)\s*:?\s*$", line, re.IGNORECASE):
            # Collect content until next header
            abstract_lines = []
            for j in range(i + 1, len(lines)):
                if re.match(r"^#{1,3}\s+", lines[j]):
                    break
                abstract_lines.append(lines[j])
            abstract_text = "\n".join(abstract_lines).strip()
            if len(abstract_text.split()) >= 20:
                # Remove abstract from the text
                end = i + 1 + len(abstract_lines)
                remaining = "\n".join(lines[:i] + lines[end:])
                return abstract_text, remaining

    # Strategy 2: First substantial paragraph before first section header
    # Find first real section header (not title)
    first_section_idx = None
    title_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^#\s+", line):
            if title_idx is None:
                title_idx = i
            elif first_section_idx is None:
                first_section_idx = i
                break

    if title_idx is not None:
        search_end = first_section_idx if first_section_idx else min(len(lines), 80)
        # Look for a paragraph that starts like an abstract
        para_start = None
        for i in range(title_idx + 1, search_end):
            stripped = lines[i].strip()
            if not stripped:
                continue
            if re.match(r"^#", lines[i]):
                continue
            if ABSTRACT_STARTERS.match(stripped):
                para_start = i
                break
            # Also check for substantial paragraph (50+ words) that isn't author info
            if len(stripped.split()) >= 50 and para_start is None:
                para_start = i
                break

        if para_start is not None:
            # Collect until double blank line, header, or keyword line
            abstract_lines = []
            consecutive_blanks = 0
            for j in range(para_start, search_end):
                stripped = lines[j].strip()
                if re.match(r"^#", lines[j]):
                    break
                # Stop at JEL codes or keywords line (marks end of abstract)
                if re.match(r"^(JEL|Keywords|Palabras clave|Palavras[- ]chave|Mots[- ]clés|Schlüsselwörter|Parole chiave)", stripped, re.IGNORECASE):
                    break
                if not stripped:
                    consecutive_blanks += 1
                    if consecutive_blanks >= 2 and len(abstract_lines) > 2:
                        break
                    abstract_lines.append(lines[j])
                    continue
                consecutive_blanks = 0
                abstract_lines.append(lines[j])
            abstract_text = "\n".join(abstract_lines).strip()
            if len(abstract_text.split()) >= 20:
                end = para_start + len(abstract_lines)
                remaining = "\n".join(lines[:para_start] + lines[end:])
                return abstract_text, remaining

    return "", md_text


# --- Section splitting ---

def _is_main_section(title: str) -> bool:
    """Determine if a section title represents a main section."""
    title_stripped = title.strip()

    # Roman numeral at start → always main (check BEFORE letter prefix)
    if ROMAN_NUMERAL_RE.match(title_stripped):
        return True

    # Numbered main sections (1., 2., but not 2.1, 3.2.1)
    if re.match(r"^\d+\.\s+\S", title_stripped) and not re.match(r"^\d+\.\d+", title_stripped):
        return True

    # Letter-prefix sections (A., B., C.) are always subsections
    if re.match(r"^[A-Za-z][\.\)]\s", title_stripped):
        return False

    # Check keywords on cleaned title
    clean = title_stripped.lower()
    for kw in MAIN_SECTION_KEYWORDS:
        if kw in clean:
            return True
    return False


def split_into_sections(md_text: str, sections_dir: Path) -> str:
    """Split markdown into sections based on headers.

    If >12 sections result, merges subsections into their parent main section.
    Creates individual section files and composite body.md / appendix.md.
    Returns the index content string.
    """
    sections_dir.mkdir(parents=True, exist_ok=True)

    # Clean orphan image references
    md_text = clean_orphan_images(md_text)

    # Extract metadata
    meta = extract_metadata(md_text)

    # Extract abstract
    abstract_text, md_text = extract_abstract(md_text)

    lines = md_text.split("\n")

    # Find all headers
    headers = []
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,3})\s+(.+)$", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headers.append((i, level, title))

    if not headers:
        body_path = sections_dir / "body.md"
        body_path.write_text(md_text, encoding="utf-8")
        index = _build_index(meta, abstract_text, [("(full document)", len(lines), "body.md", "body")],
                             len(lines), 0, 0, 0)
        if abstract_text:
            (sections_dir / "00_abstract.md").write_text(abstract_text, encoding="utf-8")
        (sections_dir / "_index.md").write_text(index, encoding="utf-8")
        return index

    # Split on minimum-level headers (what MinerU gives us)
    section_level = min(h[1] for h in headers)
    section_headers = [(i, lvl, title) for i, lvl, title in headers if lvl == section_level]

    # Build raw sections
    raw_sections = []
    for idx, (line_no, lvl, title) in enumerate(section_headers):
        start = line_no
        end = section_headers[idx + 1][0] if idx + 1 < len(section_headers) else len(lines)
        content = "\n".join(lines[start:end]).strip()
        raw_sections.append((title, content, end - start))

    # Preamble
    if section_headers[0][0] > 0:
        preamble = "\n".join(lines[: section_headers[0][0]]).strip()
        if preamble:
            raw_sections.insert(0, ("Preamble", preamble, section_headers[0][0]))

    # Smart merge: if too many sections, merge subsections into main sections
    if len(raw_sections) > MAX_SECTIONS_BEFORE_MERGE:
        raw_sections = _merge_subsections(raw_sections)

    # Write individual section files + classify
    body_parts = []
    appendix_parts = []
    in_appendix = False
    references_content = None
    index_rows = []

    file_idx = 1  # start at 1 if abstract exists, 0 otherwise
    if abstract_text:
        (sections_dir / "00_abstract.md").write_text(abstract_text, encoding="utf-8")

    for title, content, num_lines in raw_sections:
        slug = slugify(title)
        filename = f"{file_idx:02d}_{slug}.md"
        filepath = sections_dir / filename
        filepath.write_text(content, encoding="utf-8")

        is_ref = bool(REFERENCES_PATTERN.match(f"# {title}"))
        is_app = bool(APPENDIX_PATTERN.match(f"# {title}"))

        if is_ref:
            references_content = content
            in_appendix = True
            index_rows.append((title, num_lines, filename, "ref"))
        elif is_app or in_appendix:
            in_appendix = True
            appendix_parts.append(content)
            index_rows.append((title, num_lines, filename, "appendix"))
        else:
            body_parts.append(content)
            index_rows.append((title, num_lines, filename, "body"))

        file_idx += 1

    # Write composite files
    body_text = "\n\n".join(body_parts)
    appendix_text = "\n\n".join(appendix_parts) if appendix_parts else ""
    (sections_dir / "body.md").write_text(body_text, encoding="utf-8")

    if appendix_parts:
        (sections_dir / "appendix.md").write_text(appendix_text, encoding="utf-8")

    if references_content:
        (sections_dir / "references.md").write_text(references_content, encoding="utf-8")

    body_lines = body_text.count("\n") + 1 if body_parts else 0
    app_lines = appendix_text.count("\n") + 1 if appendix_parts else 0
    ref_lines = references_content.count("\n") + 1 if references_content else 0

    index = _build_index(meta, abstract_text, index_rows, len(lines), body_lines, ref_lines, app_lines)
    (sections_dir / "_index.md").write_text(index, encoding="utf-8")
    return index


def _merge_subsections(sections: list[tuple]) -> list[tuple]:
    """Merge non-main sections into their preceding main section."""
    merged = []
    current_title = None
    current_parts = []

    def _flush():
        if current_title is not None:
            merged_content = "\n\n".join(current_parts)
            merged.append((current_title, merged_content, merged_content.count("\n") + 1))

    for title, content, num_lines in sections:
        if _is_main_section(title):
            _flush()
            current_title = title
            current_parts = [content]
        else:
            if current_title is None:
                current_title = title
                current_parts = [content]
            else:
                current_parts.append(content)

    _flush()
    return merged


def _build_index(meta: dict, abstract_text: str, index_rows: list, total_lines: int,
                 body_lines: int, ref_lines: int, app_lines: int) -> str:
    """Build the _index.md content."""
    abstract_lines = abstract_text.count("\n") + 1 if abstract_text else 0

    index = f"<!-- split_version: {SPLIT_VERSION} -->\n"
    index += "# Paper Index\n\n"

    # Metadata
    if meta.get("title"):
        index += f"**Title**: {meta['title']}  \n"
    if meta.get("authors"):
        index += f"**Authors**: {meta['authors']}  \n"
    if meta.get("jel"):
        index += f"**JEL**: {meta['jel']}  \n"
    index += "\n"

    # Size summary
    if abstract_text:
        index += f"**Abstract**: {abstract_lines} lines (`00_abstract.md`)  \n"
    index += f"**Body**: {body_lines} lines (`body.md`)  \n"
    if ref_lines:
        index += f"**References**: {ref_lines} lines (`references.md`)  \n"
    if app_lines:
        index += f"**Appendix**: {app_lines} lines (`appendix.md`)  \n"
    index += f"**Full**: {total_lines} lines (`../paper.md`)  \n\n"

    # Section table
    index += "| # | Section | Lines | File | Part |\n"
    index += "|---|---------|-------|------|------|\n"
    if abstract_text:
        index += f"| 0 | Abstract | {abstract_lines} | 00_abstract.md | body |\n"
    for title, num_lines, filename, part in index_rows:
        idx = filename.split("_")[0]
        safe_title = title.replace("|", "\\|")
        index += f"| {idx} | {safe_title} | {num_lines} | {filename} | {part} |\n"

    return index


# --- MinerU API functions ---

def _api_request(method, url, api_key, retries=1, **kwargs):
    """Make an API request with retry logic for transient errors."""
    headers = get_headers(api_key)
    last_exc = None

    for attempt in range(retries + 1):
        try:
            resp = requests.request(method, url, headers=headers, **kwargs)

            if resp.status_code == 429:
                if attempt < retries:
                    wait = 60
                    print(f"[MinerU] Rate limited (429). Waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()

            if resp.status_code in (402, 403):
                raise RuntimeError(
                    f"MinerU API access denied ({resp.status_code}). "
                    "Check your API key and quota at https://mineru.net"
                )

            if resp.status_code >= 500:
                if attempt < retries:
                    wait = 5
                    print(f"[MinerU] Server error ({resp.status_code}). Retrying in {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()

            resp.raise_for_status()
            return resp

        except requests.exceptions.ConnectionError as e:
            last_exc = e
            if attempt < retries:
                print(f"[MinerU] Connection error. Retrying in 5s...", file=sys.stderr)
                time.sleep(5)
                continue
            raise

    raise last_exc if last_exc is not None else RuntimeError("API request failed after retries")


def upload_and_extract(pdf_path: Path, api_key: str, lang: str = "auto") -> str:
    """Upload a local PDF to MinerU and return the extracted markdown text."""
    filename = pdf_path.name
    file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
    poll_timeout = min(3600, max(300, int(file_size_mb * 60)))

    api_params = {
        "enable_formula": True,
        "enable_table": True,
        "layout_model": "doclayout_yolo",
        "files": [{"name": filename, "is_ocr": False}],
    }
    if lang != "auto":
        api_params["language"] = lang

    print(f"[MinerU] Requesting upload URL for {filename}...", file=sys.stderr)
    resp = _api_request("POST", f"{MINERU_API_URL}/file-urls/batch", api_key,
                        retries=1, json=api_params)
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"MinerU API error (batch upload): {data.get('msg', data)}")

    batch_id = data["data"]["batch_id"]
    upload_url = data["data"]["file_urls"][0]

    print(f"[MinerU] Uploading {filename} ({file_size_mb:.1f} MB)...", file=sys.stderr)
    with open(pdf_path, "rb") as f:
        put_resp = requests.put(upload_url, data=f.read())
    put_resp.raise_for_status()

    print(f"[MinerU] Processing (batch_id={batch_id}, timeout={poll_timeout}s)...", file=sys.stderr)
    result = _poll_batch(batch_id, api_key, poll_timeout)
    return _download_md(result)


def extract_via_url(url: str, api_key: str, lang: str = "auto") -> str:
    """Extract markdown from a PDF at a public URL."""
    print(f"[MinerU] Submitting URL for extraction...", file=sys.stderr)
    payload = {"url": url, "enable_formula": True, "enable_table": True}
    if lang != "auto":
        payload["language"] = lang
    resp = _api_request("POST", f"{MINERU_API_URL}/extract/task", api_key,
                        retries=1, json=payload)
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"MinerU API error (URL extraction): {data.get('msg', data)}")

    task_id = data["data"]["task_id"]
    print(f"[MinerU] Processing (task_id={task_id})...", file=sys.stderr)
    result = _poll_task(task_id, api_key, 300)
    return _download_md(result)


def _poll_batch(batch_id: str, api_key: str, timeout: int) -> dict:
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            raise TimeoutError(f"Timed out after {timeout}s")

        resp = _api_request("GET", f"{MINERU_API_URL}/extract-results/batch/{batch_id}", api_key)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Poll error: {data.get('msg', data)}")

        results = data["data"]["extract_result"]
        if results:
            result = results[0]
            state = result.get("state", "")
            if state == "done":
                pages = result.get("extract_progress", {}).get("extracted_pages", "?")
                print(f"[MinerU] Done! {pages} pages.", file=sys.stderr)
                return result
            elif state == "failed":
                raise RuntimeError(f"MinerU extraction failed: {result.get('err_msg', 'unknown error')}")
            else:
                p = result.get("extract_progress", {})
                print(f"[MinerU] {state}: {p.get('extracted_pages', 0)}/{p.get('total_pages', '?')} ({elapsed:.0f}s)...", file=sys.stderr)

        time.sleep(POLL_INTERVAL)


def _poll_task(task_id: str, api_key: str, timeout: int) -> dict:
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            raise TimeoutError(f"Timed out after {timeout}s")

        resp = _api_request("GET", f"{MINERU_API_URL}/extract/task/{task_id}", api_key)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Poll error: {data.get('msg', data)}")

        result = data["data"]
        state = result.get("state", "")
        if state == "done":
            pages = result.get("extract_progress", {}).get("extracted_pages", "?")
            print(f"[MinerU] Done! {pages} pages.", file=sys.stderr)
            return result
        elif state == "failed":
            raise RuntimeError(f"MinerU extraction failed: {result.get('err_msg', 'unknown error')}")

        p = result.get("extract_progress", {})
        print(f"[MinerU] {state}: {p.get('extracted_pages', 0)}/{p.get('total_pages', '?')} ({elapsed:.0f}s)...", file=sys.stderr)
        time.sleep(POLL_INTERVAL)


def _download_md(result: dict) -> str:
    md_url = result.get("full_zip_url") or result.get("md_url")
    if not md_url:
        content = result.get("content", "")
        if content:
            return content
        raise RuntimeError(f"No markdown URL in result: {json.dumps(result, indent=2)}")

    if md_url.endswith(".zip"):
        import io
        import zipfile

        zip_resp = requests.get(md_url)
        zip_resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
            md_files = [n for n in zf.namelist() if n.endswith(".md")]
            if not md_files:
                raise FileNotFoundError(f"No .md in zip: {zf.namelist()}")
            # Prefer known names, fall back to largest file
            md_name = None
            for pref in ("paper.md", "content.md", "output.md", "full.md"):
                matches = [n for n in md_files if n.endswith(f"/{pref}") or n == pref]
                if matches:
                    md_name = matches[0]
                    break
            if md_name is None:
                md_name = max(md_files, key=lambda n: zf.getinfo(n).file_size)
            return zf.read(md_name).decode("utf-8")
    else:
        md_resp = requests.get(md_url)
        md_resp.raise_for_status()
        return md_resp.text


# --- Quick mode ---

def quick_summary(cache_dir: Path, meta: dict = None, abstract_text: str = None) -> str:
    """Generate a quick stdout summary from cached data."""
    full_md = cache_dir / "paper.md"
    index_file = cache_dir / "sections" / "_index.md"

    if not full_md.exists():
        return "Error: no cached paper found"

    md_text = full_md.read_text(encoding="utf-8")

    if meta is None:
        meta = extract_metadata(md_text)
    if abstract_text is None:
        abstract_text, _ = extract_abstract(md_text)

    out = []
    if meta.get("title"):
        out.append(f"# {meta['title']}")
    if meta.get("authors"):
        out.append(f"**Authors**: {meta['authors']}")
    if meta.get("jel"):
        out.append(f"**JEL**: {meta['jel']}")
    out.append("")

    if abstract_text:
        out.append("## Abstract")
        out.append(abstract_text)
        out.append("")

    if index_file.exists():
        out.append("## Sections")
        # Parse table from index
        for line in index_file.read_text(encoding="utf-8").split("\n"):
            if line.startswith("|") and not line.startswith("|---") and not line.startswith("| #"):
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 5:
                    out.append(f"  {parts[1]}. {parts[2]} ({parts[3]} lines)")

    return "\n".join(out)


# --- Cache version check ---

def needs_resplit(sections_dir: Path) -> bool:
    """Check if sections were split with an older version."""
    index_file = sections_dir / "_index.md"
    if not index_file.exists():
        return True
    try:
        content = index_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True
    m = re.search(r"split_version:\s*(\d+)", content)
    if not m:
        return True  # no version marker = old version
    return int(m.group(1)) < SPLIT_VERSION


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Convert PDF to Markdown using MinerU Cloud API")
    parser.add_argument("pdf_path", help="Path to PDF file or URL")
    parser.add_argument("--section", "-s", help="Print path to a specific section (substring match)")
    parser.add_argument("--full", action="store_true", help="Print path to full paper.md")
    parser.add_argument("--list", action="store_true", help="Print the section index to stdout")
    parser.add_argument("--quick", "-q", action="store_true", help="Print quick summary (title+abstract+TOC) to stdout")
    parser.add_argument("--lang", default="auto", choices=["auto", "en", "es", "pt", "fr", "de", "it", "zh"],
                        help="OCR language (default: auto = let MinerU detect)")
    parser.add_argument("--no-cache", action="store_true", help="Force re-conversion")
    parser.add_argument("--cache-dir", help="Override cache directory (default: ~/.claude/tools/md_cache)")
    args = parser.parse_args()

    api_key = get_api_key()
    if not api_key:
        print("Error: MINERU_API_KEY not found.", file=sys.stderr)
        print(f"Set env var or create {CONFIG_FILE} with: {{\"api_key\": \"...\"}}", file=sys.stderr)
        sys.exit(1)

    # Allow overriding cache directory
    base_cache = Path(args.cache_dir) if args.cache_dir else CACHE_DIR

    is_url = args.pdf_path.startswith(("http://", "https://"))

    if is_url:
        h = hashlib.sha256(args.pdf_path.encode()).hexdigest()[:12]
        name = args.pdf_path.split("/")[-1].replace(".pdf", "") or "document"
        name = slugify(name)
        cache_dir = base_cache / f"{name}_{h}"
    else:
        pdf_path = Path(args.pdf_path).resolve()
        if not pdf_path.exists():
            print(f"Error: {pdf_path} not found", file=sys.stderr)
            sys.exit(1)
        if pdf_path.suffix.lower() != ".pdf":
            print(f"Error: {pdf_path} is not a PDF file", file=sys.stderr)
            sys.exit(1)
        if args.cache_dir:
            h = file_hash(pdf_path)
            name = slugify(pdf_path.stem) or pdf_path.stem
            cache_dir = base_cache / f"{name}_{h}"
        else:
            cache_dir = get_cache_dir(pdf_path)

    full_md = cache_dir / "paper.md"
    sections_dir = cache_dir / "sections"
    index_file = sections_dir / "_index.md"

    # Check cache
    needs_convert = not full_md.exists() or args.no_cache
    needs_split = needs_convert or needs_resplit(sections_dir)

    if needs_convert:
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            if is_url:
                md_text = extract_via_url(args.pdf_path, api_key, lang=args.lang)
            else:
                md_text = upload_and_extract(pdf_path, api_key, lang=args.lang)
        except Exception as e:
            print(f"Error converting {args.pdf_path}: {e}", file=sys.stderr)
            sys.exit(1)
        if len(md_text.strip()) < 100:
            print(f"Error: MinerU returned minimal content ({len(md_text)} chars). "
                  "The PDF may be image-only or corrupted. Try --lang to force OCR language.",
                  file=sys.stderr)
            sys.exit(1)
        full_md.write_text(md_text, encoding="utf-8")
        # Clean old section files before re-splitting
        if sections_dir.exists():
            for f in sections_dir.glob("*.md"):
                f.unlink()
        split_into_sections(md_text, sections_dir)
        print(f"[MinerU] Saved and split: {cache_dir}", file=sys.stderr)
    elif needs_split:
        # paper.md exists but sections need re-splitting (old version)
        md_text = full_md.read_text(encoding="utf-8")
        # Clean old section files
        if sections_dir.exists():
            for f in sections_dir.glob("*.md"):
                f.unlink()
        split_into_sections(md_text, sections_dir)
        print(f"[MinerU] Re-split (v{SPLIT_VERSION}): {cache_dir.name}", file=sys.stderr)
    else:
        print(f"[MinerU] Cache hit: {cache_dir.name}", file=sys.stderr)

    # Output
    if args.quick:
        print(quick_summary(cache_dir))
    elif args.list:
        print(index_file.read_text(encoding="utf-8"))
    elif args.full:
        print(str(full_md))
    elif args.section:
        query = _normalize(args.section.lower())
        # Score matches: filename match > header match > content match
        scored = []
        for f in sorted(sections_dir.glob("*.md")):
            if f.name in ("_index.md", "body.md", "appendix.md", "references.md"):
                continue
            name_norm = _normalize(f.stem.lower())
            if query in name_norm:
                scored.append((0, f))  # best: filename match
                continue
            content_start = f.read_text(encoding="utf-8")[:500]
            content_norm = _normalize(content_start.lower())
            # Check first header line
            first_line = content_start.split("\n")[0] if content_start else ""
            header_norm = _normalize(first_line.lower())
            if query in header_norm:
                scored.append((1, f))  # good: header match
            elif query in content_norm:
                scored.append((2, f))  # ok: content match
        scored.sort(key=lambda x: x[0])
        if scored:
            print(str(scored[0][1]))
        else:
            print(f"Error: no section matching '{args.section}'", file=sys.stderr)
            available = [f.stem for f in sorted(sections_dir.glob("*.md"))
                         if f.name not in ("_index.md", "body.md", "appendix.md", "references.md")]
            print(f"Available: {', '.join(available)}", file=sys.stderr)
            sys.exit(1)
    else:
        print(str(index_file))


if __name__ == "__main__":
    main()
