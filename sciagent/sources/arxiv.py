import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlencode

import requests

from ..models import Paper


ATOM = {"a": "http://www.w3.org/2005/Atom"}
ARXIV = {"arxiv": "http://arxiv.org/schemas/atom"}
API_URL = "https://export.arxiv.org/api/query"


def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _date_compact(value: str, end: bool = False) -> str:
    dt = datetime.strptime(value, "%Y-%m-%d")
    return dt.strftime("%Y%m%d") + ("2359" if end else "0000")


def build_query(keyword: str, date_from: Optional[str], date_to: Optional[str]) -> str:
    escaped = keyword.replace('"', "")
    parts = ['all:"%s"' % escaped]
    if date_from and date_to:
        parts.append("submittedDate:[%s TO %s]" % (_date_compact(date_from), _date_compact(date_to, True)))
    return " AND ".join(parts)


def parse_feed(xml_text: str) -> List[Paper]:
    root = ET.fromstring(xml_text)
    papers = []
    for entry in root.findall("a:entry", ATOM):
        id_url = _clean(entry.findtext("a:id", default="", namespaces=ATOM))
        arxiv_id = id_url.rstrip("/").split("/")[-1]
        arxiv_id = arxiv_id.split("v")[0] if re.match(r"^\d{4}\.\d+v\d+$", arxiv_id) else arxiv_id
        authors = []
        for author in entry.findall("a:author", ATOM):
            authors.append(_clean(author.findtext("a:name", default="", namespaces=ATOM)))
        categories = []
        for category in entry.findall("a:category", ATOM):
            term = category.attrib.get("term", "")
            if term:
                categories.append(term)
        abs_url = "https://arxiv.org/abs/%s" % arxiv_id
        pdf_url = "https://arxiv.org/pdf/%s" % arxiv_id
        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=_clean(entry.findtext("a:title", default="", namespaces=ATOM)),
                authors=authors,
                abstract=_clean(entry.findtext("a:summary", default="", namespaces=ATOM)),
                published=_clean(entry.findtext("a:published", default="", namespaces=ATOM)),
                updated=_clean(entry.findtext("a:updated", default="", namespaces=ATOM)),
                categories=categories,
                abs_url=abs_url,
                pdf_url=pdf_url,
                html_url="https://arxiv.org/html/%s" % arxiv_id,
            )
        )
    return papers


class ArxivSource:
    def __init__(self, user_agent: str, delay_seconds: float = 3.0, timeout: int = 60):
        self.user_agent = user_agent
        self.delay_seconds = delay_seconds
        self.timeout = timeout
        self._last_request = 0.0

    def _wait(self):
        elapsed = time.monotonic() - self._last_request
        remaining = self.delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()

    def search(self, keyword: str, date_from: Optional[str], date_to: Optional[str], max_results: int = 100, page_size: int = 100) -> List[Paper]:
        query = build_query(keyword, date_from, date_to)
        results = []
        start = 0
        while len(results) < max_results:
            batch = min(page_size, max_results - len(results))
            params = {
                "search_query": query,
                "start": start,
                "max_results": batch,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            self._wait()
            response = requests.get(
                API_URL,
                params=params,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
            page = parse_feed(response.text)
            if not page:
                break
            results.extend(page)
            if len(page) < batch:
                break
            start += len(page)
        # local defensive date filter
        if date_from or date_to:
            filtered = []
            for paper in results:
                d = paper.published[:10]
                if date_from and d < date_from:
                    continue
                if date_to and d > date_to:
                    continue
                filtered.append(paper)
            results = filtered
        return results[:max_results]
