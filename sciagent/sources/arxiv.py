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


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "could",
    "detect",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "to",
    "what",
    "when",
    "where",
    "which",
    "why",
    "with",
    "would",
}


def _clean(text: Optional[str]) -> str:
    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()


def _date_compact(
    value: str,
    end: bool = False,
) -> str:
    dt = datetime.strptime(
        value,
        "%Y-%m-%d",
    )

    return dt.strftime(
        "%Y%m%d"
    ) + (
        "2359"
        if end
        else "0000"
    )


def _query_terms(
    keyword: str,
) -> List[str]:
    raw = re.findall(
        r"[A-Za-z0-9][A-Za-z0-9._+-]*",
        keyword.lower(),
    )

    terms = []
    seen = set()

    for term in raw:
        term = term.strip("._+-")

        if len(term) < 2:
            continue

        if term in STOP_WORDS:
            continue

        if term in seen:
            continue

        seen.add(term)
        terms.append(term)

    # Prevent giant generated queries.
    return terms[:10]


def _date_filter(
    core: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> str:
    parts = [core]

    if date_from and date_to:
        parts.append(
            "submittedDate:[{} TO {}]".format(
                _date_compact(date_from),
                _date_compact(
                    date_to,
                    True,
                ),
            )
        )

    return " AND ".join(parts)


def build_query(
    keyword: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> str:
    """
    Default query: all meaningful words must occur somewhere.

    This deliberately does NOT treat a natural-language question
    as one exact phrase.
    """

    terms = _query_terms(keyword)

    if terms:
        core = " AND ".join(
            'all:"{}"'.format(
                term.replace('"', "")
            )
            for term in terms
        )
    else:
        escaped = keyword.replace(
            '"',
            "",
        )

        core = 'all:"{}"'.format(
            escaped
        )

    return _date_filter(
        core,
        date_from,
        date_to,
    )


def build_broad_query(
    keyword: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> str:
    terms = _query_terms(keyword)

    if not terms:
        return build_query(
            keyword,
            date_from,
            date_to,
        )

    core = "(" + " OR ".join(
        'all:"{}"'.format(
            term.replace('"', "")
        )
        for term in terms
    ) + ")"

    return _date_filter(
        core,
        date_from,
        date_to,
    )


def parse_feed(
    xml_text: str,
) -> List[Paper]:
    root = ET.fromstring(
        xml_text
    )

    papers = []

    for entry in root.findall(
        "a:entry",
        ATOM,
    ):
        id_url = _clean(
            entry.findtext(
                "a:id",
                default="",
                namespaces=ATOM,
            )
        )

        arxiv_id = (
            id_url
            .rstrip("/")
            .split("/")[-1]
        )

        if re.match(
            r"^\d{4}\.\d+v\d+$",
            arxiv_id,
        ):
            arxiv_id = (
                arxiv_id.split("v")[0]
            )

        authors = []

        for author in entry.findall(
            "a:author",
            ATOM,
        ):
            authors.append(
                _clean(
                    author.findtext(
                        "a:name",
                        default="",
                        namespaces=ATOM,
                    )
                )
            )

        categories = []

        for category in entry.findall(
            "a:category",
            ATOM,
        ):
            term = category.attrib.get(
                "term",
                "",
            )

            if term:
                categories.append(term)

        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=_clean(
                    entry.findtext(
                        "a:title",
                        default="",
                        namespaces=ATOM,
                    )
                ),
                authors=authors,
                abstract=_clean(
                    entry.findtext(
                        "a:summary",
                        default="",
                        namespaces=ATOM,
                    )
                ),
                published=_clean(
                    entry.findtext(
                        "a:published",
                        default="",
                        namespaces=ATOM,
                    )
                ),
                updated=_clean(
                    entry.findtext(
                        "a:updated",
                        default="",
                        namespaces=ATOM,
                    )
                ),
                categories=categories,
                abs_url=(
                    "https://arxiv.org/abs/"
                    + arxiv_id
                ),
                pdf_url=(
                    "https://arxiv.org/pdf/"
                    + arxiv_id
                ),
                html_url=(
                    "https://arxiv.org/html/"
                    + arxiv_id
                ),
            )
        )

    return papers


class ArxivSource:
    def __init__(
        self,
        user_agent: str,
        delay_seconds: float = 3.0,
        timeout: int = 60,
    ):
        self.user_agent = user_agent
        self.delay_seconds = (
            delay_seconds
        )
        self.timeout = timeout
        self._last_request = 0.0

    def _wait(self):
        elapsed = (
            time.monotonic()
            - self._last_request
        )

        remaining = (
            self.delay_seconds
            - elapsed
        )

        if remaining > 0:
            time.sleep(remaining)

        self._last_request = (
            time.monotonic()
        )

    def _get(
        self,
        params,
    ):
        retryable = {
            429,
            500,
            502,
            503,
            504,
        }

        max_attempts = 6

        for attempt in range(
            1,
            max_attempts + 1,
        ):
            try:
                self._wait()

                response = requests.get(
                    API_URL,
                    params=params,
                    headers={
                        "User-Agent": (
                            self.user_agent
                        )
                    },

                    # Fast failure on broken connection,
                    # generous read timeout afterwards.
                    timeout=(
                        12,
                        self.timeout,
                    ),
                )

                if (
                    response.status_code
                    not in retryable
                ):
                    response.raise_for_status()
                    return response

                error = (
                    "HTTP {}".format(
                        response.status_code
                    )
                )

                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                delay = None

                if retry_after:
                    try:
                        delay = float(
                            retry_after
                        )
                    except ValueError:
                        pass

            except requests.RequestException as exc:
                error = (
                    "{}: {}".format(
                        type(exc).__name__,
                        exc,
                    )
                )

                delay = None

            if attempt >= max_attempts:
                raise RuntimeError(
                    "arXiv API failed after "
                    "{} attempts: {}".format(
                        max_attempts,
                        error,
                    )
                )

            if delay is None:
                delay = min(
                    60.0,
                    3.0
                    * (
                        2
                        ** (attempt - 1)
                    ),
                )

            print(
                " arXiv request failed: {}"
                .format(error)
            )

            print(
                " retrying in {:.1f}s "
                "({}/{})..."
                .format(
                    delay,
                    attempt,
                    max_attempts,
                )
            )

            time.sleep(delay)

        raise RuntimeError(
            "unreachable retry state"
        )

    def _fetch(
        self,
        query,
        max_results,
    ):
        results = []
        start = 0
        page_size = min(
            100,
            max_results,
        )

        while (
            len(results)
            < max_results
        ):
            batch = min(
                page_size,
                max_results
                - len(results),
            )

            params = {
                "search_query": query,
                "start": start,
                "max_results": batch,
                "sortBy": (
                    "submittedDate"
                ),
                "sortOrder": (
                    "descending"
                ),
            }

            response = self._get(
                params
            )

            page = parse_feed(
                response.text
            )

            if not page:
                break

            results.extend(page)

            if len(page) < batch:
                break

            start += len(page)

        return results

    def _score(
        self,
        paper,
        terms,
    ):
        title = paper.title.lower()
        abstract = (
            paper.abstract.lower()
        )

        score = 0
        matched = 0

        for term in terms:
            in_title = (
                term in title
            )

            in_abstract = (
                term in abstract
            )

            if (
                in_title
                or in_abstract
            ):
                matched += 1

            if in_title:
                score += 4

            if in_abstract:
                score += 1

        return score, matched

    def search(
        self,
        keyword: str,
        date_from: Optional[str],
        date_to: Optional[str],
        max_results: int = 100,
        page_size: int = 100,
    ) -> List[Paper]:

        terms = _query_terms(
            keyword
        )

        strict_query = (
            build_query(
                keyword,
                date_from,
                date_to,
            )
        )

        strict = self._fetch(
            strict_query,
            max_results,
        )

        by_id = {
            paper.arxiv_id: paper
            for paper in strict
        }

        # If strict AND search did not produce enough candidates,
        # broaden the query and rank metadata locally.
        if (
            len(by_id)
            < max_results
            and len(terms) >= 2
        ):
            broad_query = (
                build_broad_query(
                    keyword,
                    date_from,
                    date_to,
                )
            )

            candidate_pool = max(
                50,
                max_results * 8,
            )

            broad = self._fetch(
                broad_query,
                candidate_pool,
            )

            scored = []

            minimum_matches = (
                2
                if len(terms) >= 3
                else 1
            )

            for paper in broad:
                score, matched = (
                    self._score(
                        paper,
                        terms,
                    )
                )

                if (
                    matched
                    < minimum_matches
                ):
                    continue

                scored.append(
                    (
                        score,
                        paper.published,
                        paper,
                    )
                )

            scored.sort(
                key=lambda item: (
                    item[0],
                    item[1],
                ),
                reverse=True,
            )

            for _, _, paper in scored:
                if (
                    paper.arxiv_id
                    not in by_id
                ):
                    by_id[
                        paper.arxiv_id
                    ] = paper

                if (
                    len(by_id)
                    >= max_results
                ):
                    break

        results = list(
            by_id.values()
        )

        # Defensive local date filter.
        if date_from or date_to:
            filtered = []

            for paper in results:
                d = paper.published[:10]

                if (
                    date_from
                    and d < date_from
                ):
                    continue

                if (
                    date_to
                    and d > date_to
                ):
                    continue

                filtered.append(paper)

            results = filtered

        return results[
            :max_results
        ]
