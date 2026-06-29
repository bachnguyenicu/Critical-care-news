#!/usr/bin/env python3
"""Build an academic Critical Care Daily digest without Claude.

This updater is intentionally dependency-free. It uses PubMed E-utilities,
extracts recent ICU-relevant articles, and writes a structured digest for:

- quick listening practice,
- academic reading,
- PICO-style appraisal,
- bedside implications,
- medical-English learning.

It does not replace full-text appraisal. It is a daily triage and learning tool.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import textwrap
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_EMAIL = os.environ.get("NCBI_EMAIL", "critical-care-daily@example.com")

SEARCH_TERMS = (
    '("critical care"[MeSH Terms] OR "intensive care units"[MeSH Terms] '
    'OR "critical care"[Title/Abstract] OR "intensive care"[Title/Abstract] '
    'OR ICU[Title/Abstract] OR sepsis[Title/Abstract] OR "septic shock"[Title/Abstract] '
    'OR ARDS[Title/Abstract] OR "acute respiratory distress"[Title/Abstract] '
    'OR ventilation[Title/Abstract] OR "mechanical ventilation"[Title/Abstract] '
    'OR vasopressor[Title/Abstract] OR norepinephrine[Title/Abstract] '
    'OR "renal replacement therapy"[Title/Abstract] OR delirium[Title/Abstract] '
    'OR sedation[Title/Abstract] OR "ventilator-associated pneumonia"[Title/Abstract]) '
    'AND (randomized[Title/Abstract] OR trial[Title/Abstract] OR guideline[Title/Abstract] '
    'OR meta-analysis[Publication Type] OR systematic review[Title/Abstract] '
    'OR cohort[Title/Abstract] OR "clinical trial"[Publication Type]) '
    'NOT (letter[Publication Type] OR comment[Publication Type] OR editorial[Publication Type])'
)

STAT_PATTERN = re.compile(
    r"(\b\d+([.,]\d+)?%|\b\d+([.,]\d+)?\s*(patients|participants|trials|studies|days|hours)|"
    r"\b(RR|OR|HR|CI|confidence interval|risk ratio|odds ratio|hazard ratio|p\s*[<=>])\b)",
    re.I,
)

VOCAB = [
    ("primary outcome", "the main outcome the investigators planned to test"),
    ("confidence interval", "a range showing statistical uncertainty around an estimate"),
    ("heterogeneity", "variation between studies or patient groups"),
    ("intention-to-treat", "analysis according to the original assigned groups"),
    ("generalizability", "how well the findings apply to your patients"),
    ("absolute risk", "the actual event rate difference patients may experience"),
    ("adjusted estimate", "a result corrected for measured confounders"),
    ("noninferiority", "testing whether a treatment is not unacceptably worse"),
]

ICU_RELEVANCE_PATTERN = re.compile(
    r"(critical care|intensive care|critically ill|\bICU\b|sepsis|septic shock|ARDS|"
    r"mechanical ventilation|ventilator|vasopressor|norepinephrine|extracorporeal|ECMO|"
    r"renal replacement|continuous kidney|ventilator-associated pneumonia)",
    re.I,
)

PHRASES = [
    "This study examined whether ...",
    "The primary outcome was ...",
    "The effect estimate favored ..., but the confidence interval ...",
    "These findings should be interpreted cautiously because ...",
    "For bedside practice, the key question is whether ...",
]


def request_json(endpoint: str, params: dict[str, str | int]) -> dict:
    params = {**params, "retmode": "json", "tool": "critical-care-daily", "email": DEFAULT_EMAIL}
    url = f"{EUTILS}/{endpoint}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def request_xml(endpoint: str, params: dict[str, str | int]) -> ET.Element:
    params = {**params, "retmode": "xml", "tool": "critical-care-daily", "email": DEFAULT_EMAIL}
    url = f"{EUTILS}/{endpoint}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=45) as response:
        return ET.fromstring(response.read())


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def first_text(node: ET.Element, path: str) -> str:
    found = node.find(path)
    return clean_text("".join(found.itertext())) if found is not None else ""


def sentence_split(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if len(p.strip()) > 20]


def pub_date(article: ET.Element) -> str:
    pub = article.find(".//JournalIssue/PubDate")
    if pub is None:
        return ""
    year = first_text(pub, "Year")
    month = first_text(pub, "Month")
    day = first_text(pub, "Day")
    medline = first_text(pub, "MedlineDate")
    return " ".join(x for x in [month, day, year] if x) if year else medline


def abstract_sections(article: ET.Element) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    for item in article.findall(".//Abstract/AbstractText"):
        label = clean_text(item.attrib.get("Label", "")) or "Abstract"
        text = clean_text("".join(item.itertext()))
        if text:
            sections.setdefault(label, []).append(text)
    return {label: " ".join(parts) for label, parts in sections.items()}


def publication_types(article: ET.Element) -> list[str]:
    return [clean_text("".join(x.itertext())) for x in article.findall(".//PublicationType")]


def article_type(title: str, types: list[str]) -> str:
    haystack = " ".join([title, *types]).lower()
    if "guideline" in haystack:
        return "Clinical practice guideline"
    if "meta-analysis" in haystack or "systematic review" in haystack:
        return "Systematic review / meta-analysis"
    if "randomized" in haystack or "clinical trial" in haystack:
        return "Randomized / clinical trial"
    if "cohort" in haystack:
        return "Cohort study"
    return "Recent research article"


def evidence_rank(kind: str) -> str:
    k = kind.lower()
    if "guideline" in k:
        return "Guideline: practice-relevant, but recommendations depend on evidence certainty and local resources."
    if "meta-analysis" in k or "systematic" in k:
        return "High-yield synthesis: check heterogeneity, included study quality, and whether ICU patients match your setting."
    if "randomized" in k or "trial" in k:
        return "Interventional evidence: check allocation, blinding, protocol adherence, and absolute effect size."
    if "cohort" in k:
        return "Observational evidence: useful for association and prognosis, but residual confounding is likely."
    return "Early evidence: useful for awareness, not enough alone to change practice."


def score_article(item: dict) -> int:
    haystack = " ".join([item["title"], item["abstract"], item["type"]]).lower()
    score = 0
    for term, value in [
        ("randomized", 8),
        ("trial", 5),
        ("meta-analysis", 8),
        ("systematic review", 7),
        ("guideline", 7),
        ("mortality", 5),
        ("septic shock", 4),
        ("sepsis", 3),
        ("ards", 4),
        ("mechanical ventilation", 4),
        ("vasopressor", 3),
        ("intensive care", 4),
        ("critically ill", 4),
        ("delirium", 2),
    ]:
        if term in haystack:
            score += value
    if len(item["abstract"]) > 800:
        score += 4
    if STAT_PATTERN.search(item["abstract"]):
        score += 4
    return score


def is_icu_relevant(item: dict) -> bool:
    haystack = " ".join([item["title"], item["abstract"], item["journal"]])
    return bool(ICU_RELEVANCE_PATTERN.search(haystack))


def search_pmids(days: int, retmax: int) -> list[str]:
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    result = request_json(
        "esearch.fcgi",
        {
            "db": "pubmed",
            "term": SEARCH_TERMS,
            "sort": "pub+date",
            "retmax": retmax,
            "mindate": start.isoformat(),
            "maxdate": today.isoformat(),
            "datetype": "pdat",
        },
    )
    return result.get("esearchresult", {}).get("idlist", [])


def fetch_articles(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []
    root = request_xml("efetch.fcgi", {"db": "pubmed", "id": ",".join(pmids)})
    articles = []
    for pubmed_article in root.findall(".//PubmedArticle"):
        citation = pubmed_article.find(".//MedlineCitation")
        article = pubmed_article.find(".//Article")
        if citation is None or article is None:
            continue
        pmid = clean_text("".join(citation.findtext("PMID", default="")))
        title = first_text(article, "ArticleTitle")
        sections = abstract_sections(article)
        abstract = " ".join(sections.values())
        journal = first_text(article, "Journal/Title") or first_text(article, "Journal/ISOAbbreviation")
        types = publication_types(article)
        if not pmid or not title or len(abstract) < 250:
            continue
        item = {
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "sections": sections,
            "journal": journal or "PubMed",
            "date": pub_date(article),
            "type": article_type(title, types),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "urlLabel": "View on PubMed",
        }
        if not is_icu_relevant(item):
            continue
        item["score"] = score_article(item)
        articles.append(item)
    return articles


def load_history(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("pmids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_history(path: Path, pmids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"pmids": sorted(pmids), "updated": dt.date.today().isoformat()}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_section(sections: dict[str, str], names: list[str]) -> str:
    for wanted in names:
        for label, text in sections.items():
            if wanted.lower() in label.lower():
                return text
    return ""


def choose_sentences(text: str, limit: int, prefer_stats: bool = False) -> list[str]:
    sentences = sentence_split(text)
    if prefer_stats:
        with_stats = [s for s in sentences if STAT_PATTERN.search(s)]
        rest = [s for s in sentences if s not in with_stats]
        sentences = with_stats + rest
    return sentences[:limit]


def infer_pico(item: dict) -> dict[str, str]:
    title = item["title"]
    sections = item["sections"]
    methods = find_section(sections, ["method", "design", "setting", "participants"]) or item["abstract"]
    objective = find_section(sections, ["objective", "background", "purpose"]) or title

    population = "Critically ill or ICU-relevant patients described in the abstract; confirm eligibility criteria in the full text."
    if re.search(r"(adult|children|patient|participants?|critically ill|ICU|intensive care)[^.]{0,180}", methods, re.I):
        population = re.search(r"(adult|children|patient|participants?|critically ill|ICU|intensive care)[^.]{0,180}", methods, re.I).group(0)

    intervention = "Exposure or intervention stated in the title/objective."
    comparator = "Comparator or control group stated in the methods/results, if present."
    if " versus " in title.lower() or " vs " in title.lower():
        parts = re.split(r"\s+versus\s+|\s+vs\.?\s+", title, flags=re.I)
        intervention = parts[0].strip(" .:-")
        comparator = parts[1].strip(" .:-") if len(parts) > 1 else comparator
    elif " compared with " in item["abstract"].lower():
        m = re.search(r"(.{0,120}) compared with (.{0,120})", item["abstract"], re.I)
        if m:
            intervention = m.group(1).strip(" .:-")
            comparator = m.group(2).strip(" .:-")

    outcomes = find_section(sections, ["outcome", "result"]) or "Main outcomes are those reported in the abstract; prioritize patient-centered outcomes such as mortality, ventilation duration, ICU stay, and adverse events."
    outcomes = textwrap.shorten(outcomes, width=360, placeholder="...")
    return {
        "population": clean_text(population),
        "intervention": clean_text(intervention),
        "comparator": clean_text(comparator),
        "outcomes": clean_text(outcomes),
    }


def key_results(item: dict) -> list[str]:
    results = find_section(item["sections"], ["result", "finding"]) or item["abstract"]
    chosen = choose_sentences(results, 4, prefer_stats=True)
    if not chosen:
        chosen = choose_sentences(item["abstract"], 4)
    return chosen


def critical_appraisal(item: dict) -> list[str]:
    k = item["type"].lower()
    abstract = item["abstract"].lower()
    notes = [evidence_rank(item["type"])]
    if "meta-analysis" in k or "systematic" in k:
        notes.append("Look for heterogeneity, small-study effects, and whether pooled outcomes are clinically comparable.")
    elif "randomized" in k or "trial" in k:
        notes.append("Check randomization, concealment, blinding, missing data, and whether analysis was intention-to-treat.")
    elif "cohort" in k:
        notes.append("Check confounding by indication, adjustment variables, immortal-time bias, and missing outcome data.")
    if "single" in abstract:
        notes.append("Single-center data may not generalize well to different ICU resources or case-mix.")
    if not STAT_PATTERN.search(item["abstract"]):
        notes.append("The abstract does not expose much numerical detail, so the full text is important before practice decisions.")
    return notes[:4]


def practice_impact(item: dict) -> str:
    k = item["type"].lower()
    if "guideline" in k:
        return "Potentially practice-shaping: compare recommendations with your unit protocol and resource availability."
    if "meta-analysis" in k or "randomized" in k or "trial" in k:
        return "Worth discussing in journal club; consider practice change only after checking absolute effects, harms, and applicability."
    if "cohort" in k:
        return "Useful for awareness and hypothesis generation; avoid changing practice from this alone."
    return "Awareness item: read the full source before applying it at the bedside."


def english_notes(item: dict) -> dict[str, list[dict[str, str]] | list[str]]:
    text = item["abstract"].lower()
    vocab = []
    for term, meaning in VOCAB:
        if term.lower() in text or len(vocab) < 4:
            vocab.append({"term": term, "meaning": meaning})
        if len(vocab) == 5:
            break
    return {"phrases": PHRASES[:4], "vocabulary": vocab}


def build_article_card(item: dict) -> dict:
    p = infer_pico(item)
    results = key_results(item)
    academic_summary = " ".join(choose_sentences(item["abstract"], 5, prefer_stats=True))
    if len(academic_summary) > 1500:
        academic_summary = academic_summary[:1490].rsplit(" ", 1)[0] + "."
    return {
        "title": item["title"],
        "source": item["journal"],
        "date": item["date"],
        "type": item["type"],
        "summary": academic_summary,
        "analysis": practice_impact(item),
        "pico": p,
        "keyResults": results,
        "criticalAppraisal": critical_appraisal(item),
        "practiceImpact": practice_impact(item),
        "englishNotes": english_notes(item),
        "url": item["url"],
        "urlLabel": item["urlLabel"],
        "pmid": item["pmid"],
    }


def script_for_article(n: int, card: dict) -> dict:
    sentences = [
        f"Story {n} is about {card['title']}.",
        f"This is a {card['type'].lower()} from {card['source']}.",
        f"The clinical question is best framed as follows: in {card['pico']['population']}, how should we interpret {card['pico']['intervention']} compared with {card['pico']['comparator']}?",
    ]
    for result in card["keyResults"][:3]:
        sentences.append(result)
    sentences.extend(
        [
            "For critical appraisal, focus on whether the design supports a causal conclusion and whether the patients resemble your ICU population.",
            f"The bedside implication is this: {card['practiceImpact']}",
            "Useful English phrase: these findings should be interpreted cautiously because the details of design and applicability matter.",
        ]
    )
    return {"heading": f"Story {n} - {card['title'][:62]}", "sentences": sentences}


def build_digest(articles: list[dict]) -> dict:
    today = dt.date.today()
    display_date = today.strftime("%B %-d, %Y") if os.name != "nt" else today.strftime("%B %#d, %Y")
    chosen = articles[:3]
    cards = [build_article_card(item) for item in chosen]
    script = [
        {
            "heading": "Intro",
            "sentences": [
                f"Welcome to Critical Care Daily for {today.strftime('%B %d, %Y')}.",
                f"Today we will review {len(cards)} recent ICU-relevant publication{'s' if len(cards) != 1 else ''}.",
                "The format is quick listen first, then PICO, key results, critical appraisal, bedside impact, and medical English notes.",
                "Use this as a morning triage tool, then open the source link for full-text appraisal before changing practice.",
            ],
        }
    ]
    for n, card in enumerate(cards, 1):
        script.append(script_for_article(n, card))
    script.append(
        {
            "heading": "Outro",
            "sentences": [
                "That wraps up today's journal club style update.",
                "Before applying any finding, check the full source, the absolute effect size, and your local ICU context.",
                "For English practice, repeat one academic phrase from each article out loud.",
            ],
        }
    )
    return {
        "schemaVersion": 2,
        "date": display_date,
        "subtitle": "Journal-club style ICU update: PICO, key results, appraisal, bedside impact, and medical English.",
        "script": script,
        "articles": cards,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="digest.json")
    parser.add_argument("--history", default="data/covered_pmids.json")
    parser.add_argument("--archive-dir", default="archive")
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--retmax", type=int, default=50)
    args = parser.parse_args()

    output = Path(args.output)
    history_path = Path(args.history)
    archive_dir = Path(args.archive_dir)

    known = load_history(history_path)
    pmids = search_pmids(args.days, args.retmax)
    time.sleep(0.35)
    articles = fetch_articles(pmids)
    articles.sort(key=lambda x: x["score"], reverse=True)

    fresh = [a for a in articles if a["pmid"] not in known]
    selected = fresh[:3] if len(fresh) >= 2 else articles[:3]
    if len(selected) < 2:
        raise SystemExit("Found fewer than two usable PubMed items; leaving digest unchanged.")

    digest = build_digest(selected)
    output.write_text(json.dumps(digest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"digest-{dt.date.today().isoformat()}.json"
    archive_path.write_text(json.dumps(digest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    known.update(a["pmid"] for a in selected)
    save_history(history_path, known)
    print("Updated academic digest with:")
    for item in selected:
        print(f"- PMID {item['pmid']}: {textwrap.shorten(item['title'], width=100)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
