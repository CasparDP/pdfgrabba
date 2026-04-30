"""Parse a BibTeX file, fetch CrossRef metadata, build a download manifest."""

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import bibtexparser
import requests
from bibtexparser.bparser import BibTexParser


JOURNAL_ABBREVIATIONS = {
    "quarterly journal of economics": "QJE",
    "american economic review": "AER",
    "journal of political economy": "JPE",
    "econometrica": "ECMA",
    "journal of economic perspectives": "JEP",
    "journal of labor economics": "JLE",
    "journal of economic literature": "JEL",
    "review of economic studies": "REStud",
    "review of economics and statistics": "REStat",
    "journal of finance": "JF",
    "journal of financial economics": "JFE",
    "review of financial studies": "RFS",
    "journal of accounting research": "JAR",
    "journal of accounting and economics": "JAE",
    "the accounting review": "TAR",
    "accounting review": "TAR",
    "review of accounting studies": "RAS",
    "contemporary accounting research": "CAR",
    "auditing: a journal of practice & theory": "AJPT",
    "auditing a journal of practice theory": "AJPT",
    "american economic journal: applied economics": "AEJ-App",
    "american economic journal applied economics": "AEJ-App",
    "technological forecasting and social change": "TFSC",
    "journal of monetary economics": "JME",
    "handbook of labor economics": "HLE",
    "harper's magazine": "Harpers",
    "harpers magazine": "Harpers",
}


@dataclass
class ManifestEntry:
    bib_key: str
    doi: Optional[str]
    url: str
    title: str
    authors: list[str]
    journal: str
    journal_abbrev: str
    year: int
    target_filename: str
    status: str  # pending, downloaded, skipped, failed, no_doi
    notes: str = ""


def abbreviate_journal(journal_name: str) -> str:
    clean = re.sub(r"[{}\\]", "", journal_name).strip().lower()
    clean = re.sub(r"^the\s+", "", clean)

    for full, abbrev in JOURNAL_ABBREVIATIONS.items():
        if full in clean or clean in full:
            return abbrev

    words = [w for w in clean.split() if w not in ("of", "the", "and", "a", "an", "in", "for")]
    if len(words) <= 3:
        return "".join(w[0].upper() for w in words)
    return "".join(w[0].upper() for w in words[:4])


def clean_latex(text: str) -> str:
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = re.sub(r"[\\\"'`^~]", "", text)
    return text.strip()


def get_first_author_surname(authors_str: str) -> str:
    authors_str = clean_latex(authors_str)
    first_author = authors_str.split(" and ")[0].strip()
    if "," in first_author:
        surname = first_author.split(",")[0].strip()
    else:
        parts = first_author.split()
        surname = parts[-1] if parts else first_author
    return re.sub(r"[^a-zA-Z]", "", surname)


def make_filename(authors_str: str, journal: str, year: str) -> str:
    surname = get_first_author_surname(authors_str)
    abbrev = abbreviate_journal(journal)
    return f"{surname}_{abbrev}_{year}.pdf"


def fetch_crossref_metadata(doi: str, email: str) -> Optional[dict]:
    url = f"https://api.crossref.org/works/{doi}"
    headers = {"User-Agent": f"pdfgrabba/0.1 (academic research; mailto:{email})"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()["message"]
            return {
                "title": data.get("title", [""])[0],
                "authors": [
                    f"{a.get('family', '')}, {a.get('given', '')}"
                    for a in data.get("author", [])
                ],
                "journal": (data.get("container-title") or [""])[0],
                "year": (data.get("published-print") or data.get("published-online") or {})
                .get("date-parts", [[None]])[0][0],
                "doi_url": data.get("URL", f"https://doi.org/{doi}"),
            }
        return None
    except Exception as e:
        print(f"  CrossRef error for {doi}: {e}")
        return None


def parse_bib_file(bib_path: str) -> list[dict]:
    with open(bib_path, "r", encoding="utf-8") as f:
        content = f.read()
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    bib_db = bibtexparser.loads(content, parser=parser)
    return bib_db.entries


def build_manifest(
    bib_path: str,
    output_dir: str,
    *,
    email: str,
    skip_existing: bool = True,
) -> list[dict]:
    entries = parse_bib_file(bib_path)
    output_path = Path(output_dir)
    manifest = []

    print(f"\nParsed {len(entries)} entries from {bib_path}")
    print(f"Output directory: {output_dir}")
    print("-" * 60)

    for entry in entries:
        bib_key = entry.get("ID", "unknown")
        doi = entry.get("doi", "").strip()
        authors_str = entry.get("author", "Unknown")
        journal = entry.get("journal", entry.get("booktitle", "Unknown"))
        year = entry.get("year", "0000")
        title = clean_latex(entry.get("title", "Unknown"))

        target_filename = make_filename(authors_str, journal, year)

        print(f"\n[{bib_key}] {title[:60]}...")

        if not doi:
            print("  ⚠ No DOI — skipping (manual download needed)")
            manifest.append(asdict(ManifestEntry(
                bib_key=bib_key, doi=None, url="",
                title=title,
                authors=authors_str.split(" and "),
                journal=clean_latex(journal),
                journal_abbrev=abbreviate_journal(journal),
                year=int(year) if year.isdigit() else 0,
                target_filename=target_filename,
                status="no_doi",
                notes="No DOI in bib entry",
            )))
            continue

        if skip_existing and (output_path / target_filename).exists():
            print(f"  ✓ Already exists: {target_filename}")
            manifest.append(asdict(ManifestEntry(
                bib_key=bib_key, doi=doi, url=f"https://doi.org/{doi}",
                title=title,
                authors=authors_str.split(" and "),
                journal=clean_latex(journal),
                journal_abbrev=abbreviate_journal(journal),
                year=int(year) if year.isdigit() else 0,
                target_filename=target_filename,
                status="skipped",
                notes="File already exists",
            )))
            continue

        print(f"  Fetching CrossRef metadata for {doi}...")
        cr_meta = fetch_crossref_metadata(doi, email=email)
        time.sleep(0.5)

        if cr_meta:
            cr_journal = cr_meta["journal"] or clean_latex(journal)
            cr_year = cr_meta["year"] or (int(year) if year.isdigit() else 0)
            cr_authors = cr_meta["authors"] if cr_meta["authors"] else authors_str.split(" and ")

            if cr_meta["authors"]:
                first_surname = cr_meta["authors"][0].split(",")[0].strip()
                first_surname = re.sub(r"[^a-zA-Z]", "", first_surname)
                cr_abbrev = abbreviate_journal(cr_journal)
                target_filename = f"{first_surname}_{cr_abbrev}_{cr_year}.pdf"

            print(f"  ✓ CrossRef: {cr_journal} ({cr_year})")
        else:
            cr_journal = clean_latex(journal)
            cr_year = int(year) if year.isdigit() else 0
            cr_authors = authors_str.split(" and ")
            print("  ⚠ CrossRef lookup failed, using bib metadata")

        doi_url = f"https://doi.org/{doi}"
        print(f"  → Target: {target_filename}")

        manifest.append(asdict(ManifestEntry(
            bib_key=bib_key, doi=doi, url=doi_url,
            title=title,
            authors=cr_authors,
            journal=cr_journal,
            journal_abbrev=abbreviate_journal(cr_journal),
            year=cr_year,
            target_filename=target_filename,
            status="pending",
        )))

    return manifest


def save_manifest(manifest: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def load_manifest(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_summary(manifest: list[dict]) -> None:
    statuses: dict[str, int] = {}
    for entry in manifest:
        s = entry["status"]
        statuses[s] = statuses.get(s, 0) + 1

    print("\n" + "=" * 60)
    print("MANIFEST SUMMARY")
    print("=" * 60)
    print(f"Total entries:  {len(manifest)}")
    for status, count in sorted(statuses.items()):
        print(f"  {status:12s}:  {count}")
