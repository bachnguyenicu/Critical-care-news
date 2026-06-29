#!/usr/bin/env python3
"""Build the daily Critical Care Daily digest without Claude.

The script uses only the Python standard library and PubMed E-utilities.
It fetches recent critical-care publications, skips previously covered PMIDs
when possible, and writes digest.json in the schema expected by index.html.
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
    'OR ARDS[Title/Abstract] OR ventilation[Title/Abstract] '
    'OR "mechanical ventilation"[Title/Abstract] OR vasopressor[Title/Abstract]) '
    'AND (randomized[Title/Abstract] OR trial[Title/Abstract] OR guideline[Title/Abstract] '
    'OR meta-analysis[Publication Type] OR systematic review[Title/Abstract] '
    'OR cohort[Title/Abstract] OR "clinical trial"[Publication Type]) '
    'NOT (letter[Publication Type] OR comment[Publication Type] OR editorial[Publication Type])'
)


def request_json(endpoint: str, params: dict[str, str | int]) -> dict:
    params = {**params, "retmode": "json", "tool": "critical-care-daily", "email": DEFAULT_EMAIL}
    url = f"{EUTILS}/{endpoint}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def request_xml(endpoint: str, params: dict[str, str | int]) -> ET.Element:
    params = {**params, "retmode": "xml", "tool": "critical-care-daily", "email": DEFAULT_EMAIL}
    url = f"{EUTILS}/{endpoint}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=45) as response:
        data = response.read()
    return ET.fromstring(data)


def sentence_split(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if len(p.strip()) > 20]


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def first_text(node: ET.Element, path: str) -> str:
    found = node.find(path)
    return clean_text("".join(found.itertext())) if found is not None else ""


def pub_date(article: ET.Element) -> str:
    pub = article.find(".//JournalIssue/PubDate")
    if pub is None:
        return ""
    year = first_text(pub, "Year")
    month = first_text(pub, "Month")
    day = first_text(pub, "Day")
    medline = first_text(pub, "MedlineDate")
    if year:
        return " ".join(x for x in [month, day, year] if x)
    return medline


def abstract_text(article: ET.Element) -> str:
    chunks = []
    for item in article.findall(".//Abstract/AbstractText"):
        label = item.attrib.get("Label")
        text = clean_text("".join(item.itertext()))
        if text:
            chunks.append(f"{label}: {text}" if label else text)
    return " ".join(chunks)


def publication_types(article: ET.Element) -> list[str]:
    return [clean_text("".join(x.itertext())) for x in article.findall(".//PublicationType")]
