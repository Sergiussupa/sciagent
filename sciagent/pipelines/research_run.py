import json
import re
import time
from pathlib import Path

import requests

from ..document.parser import DocumentParser
from ..knowledge_extraction.claim_runtime import (
    IterativeClaimRunner,
)
from ..knowledge_extraction.claims import (
    ClaimExtractor,
)
from ..knowledge_extraction.research_design import (
    ResearchDesignExtractor,
)
from ..knowledge_extraction.research_design_runtime import (
    IterativeResearchDesignRunner,
)
from ..knowledge_fabric.paper_consolidator import (
    PaperConsolidator,
)
from ..memory.research_workspace import (
    ResearchWorkspace,
)
from ..sources.arxiv import ArxivSource


def _safe_name(value):
    return re.sub(
        r"[^a-zA-Z0-9._-]+",
        "_",
        value,
    )


def _write_json(path, value):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class ResearchRunPipeline:
    """
    Rough end-to-end research pipeline.

    Search -> download -> parse -> iterative design ->
    iterative claims -> paper consolidation -> persistent workspace.

    The corpus never needs to fit inside LLM context.
    """

    def __init__(
        self,
        config,
        json_generator,
        model_name="",
        claim_batch_chars=18000,
        design_batch_chars=18000,
    ):
        self.config = config
        self.json_generator = (
            json_generator
        )
        self.model_name = model_name

        self.parser = DocumentParser()

        self.claim_extractor = (
            ClaimExtractor(
                json_generator=json_generator
            )
        )

        self.design_extractor = (
            ResearchDesignExtractor(
                json_generator=json_generator
            )
        )

        self.claim_runner = (
            IterativeClaimRunner(
                extractor=self.claim_extractor,
                max_batch_chars=(
                    claim_batch_chars
                ),
                overlap_pages=1,
            )
        )

        self.design_runner = (
            IterativeResearchDesignRunner(
                extractor=self.design_extractor,
                max_batch_chars=(
                    design_batch_chars
                ),
                overlap_pages=1,
            )
        )

        self.consolidator = (
            PaperConsolidator(
                json_generator=json_generator,
                group_size=8,
                max_outputs_per_group=4,
                target_claims=12,
            )
        )

    def run(
        self,
        query,
        run_id,
        date_from,
        date_to,
        max_papers=10,
    ):
        run_dir = (
            Path(self.config.home)
            / "research_runs"
            / run_id
        )

        papers_dir = (
            run_dir / "papers"
        )

        papers_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        workspace_path = (
            run_dir / "workspace.sqlite3"
        )

        manifest_path = (
            run_dir / "papers.json"
        )

        report_path = (
            run_dir / "report.md"
        )

        source = ArxivSource(
            user_agent=(
                self.config.user_agent
            ),
            delay_seconds=(
                self.config.arxiv_api_delay
            ),
        )

        print()
        print("SEARCH")
        print(" query:", query)
        print(
            " dates:",
            date_from,
            "..",
            date_to,
        )
        print(
            " requested:",
            max_papers,
        )

        papers = source.search(
            keyword=query,
            date_from=date_from,
            date_to=date_to,
            max_results=max_papers,
        )

        print(
            " found:",
            len(papers),
        )

        manifest = {
            "run_id": run_id,
            "query": query,
            "date_from": date_from,
            "date_to": date_to,
            "model": self.model_name,
            "papers": [],
        }

        for paper in papers:
            manifest["papers"].append(
                {
                    "arxiv_id": (
                        paper.arxiv_id
                    ),
                    "title": paper.title,
                    "authors": (
                        paper.authors
                    ),
                    "published": (
                        paper.published
                    ),
                    "categories": (
                        paper.categories
                    ),
                    "abstract": (
                        paper.abstract
                    ),
                    "abs_url": (
                        paper.abs_url
                    ),
                    "pdf_url": (
                        paper.pdf_url
                    ),
                    "status": "pending",
                    "error": None,
                }
            )

        _write_json(
            manifest_path,
            manifest,
        )

        with ResearchWorkspace(
            workspace_path
        ) as workspace:

            for index, item in enumerate(
                manifest["papers"],
                start=1,
            ):
                paper_id = item[
                    "arxiv_id"
                ]

                print()
                print("=" * 72)
                print(
                    "[{}/{}] {}".format(
                        index,
                        len(
                            manifest["papers"]
                        ),
                        paper_id,
                    )
                )
                print(item["title"])
                print("=" * 72)

                try:
                    pdf_path = (
                        papers_dir
                        / (
                            _safe_name(
                                paper_id
                            )
                            + ".pdf"
                        )
                    )

                    self._download_pdf(
                        url=item["pdf_url"],
                        path=pdf_path,
                    )

                    print(
                        " PDF:",
                        pdf_path,
                    )

                    document = (
                        self.parser.parse(
                            str(pdf_path)
                        )
                    )

                    print(
                        " pages:",
                        len(
                            document.pages
                        ),
                    )

                    print(
                        " research design..."
                    )

                    design_result = (
                        self.design_runner.run(
                            document=document,
                            workspace=workspace,
                            run_id=run_id,
                        )
                    )

                    print(
                        "  design:",
                        design_result[
                            "status"
                        ],
                        "items=",
                        design_result[
                            "stored_items"
                        ],
                    )

                    print(
                        " claims..."
                    )

                    claim_result = (
                        self.claim_runner.run(
                            document=document,
                            workspace=workspace,
                            run_id=run_id,
                        )
                    )

                    print(
                        "  claims:",
                        claim_result[
                            "status"
                        ],
                        "stored=",
                        claim_result[
                            "stored_claims"
                        ],
                    )

                    print(
                        " consolidate..."
                    )

                    compact_result = (
                        self.consolidator.run(
                            workspace=workspace,
                            run_id=run_id,
                            paper_id=(
                                document.document_id
                            ),
                        )
                    )

                    print(
                        "  paper claims:",
                        compact_result[
                            "paper_claims"
                        ],
                    )

                    item[
                        "document_id"
                    ] = (
                        document.document_id
                    )

                    item["pages"] = len(
                        document.pages
                    )

                    item["status"] = (
                        "completed"
                    )

                    item[
                        "design_result"
                    ] = design_result

                    item[
                        "claim_result"
                    ] = claim_result

                    item[
                        "consolidation_result"
                    ] = compact_result

                except Exception as exc:
                    item["status"] = (
                        "failed"
                    )

                    item["error"] = (
                        "{}: {}".format(
                            type(exc).__name__,
                            str(exc),
                        )
                    )

                    print(
                        " ERROR:",
                        item["error"],
                    )

                _write_json(
                    manifest_path,
                    manifest,
                )

            self._write_report(
                report_path=report_path,
                manifest=manifest,
                workspace=workspace,
                run_id=run_id,
            )

            print()
            print("=" * 72)
            print("RESEARCH RUN COMPLETE")
            print("=" * 72)

            completed = sum(
                1
                for paper in manifest[
                    "papers"
                ]
                if paper["status"]
                == "completed"
            )

            failed = sum(
                1
                for paper in manifest[
                    "papers"
                ]
                if paper["status"]
                == "failed"
            )

            print(
                "completed:",
                completed,
            )

            print(
                "failed:",
                failed,
            )

            print(
                "workspace:",
                workspace_path,
            )

            print(
                "manifest:",
                manifest_path,
            )

            print(
                "report:",
                report_path,
            )

            print()
            print(
                "workspace counts:"
            )

            for kind, count in (
                workspace.counts(
                    run_id
                ).items()
            ):
                print(
                    "  {:<30} {}".format(
                        kind,
                        count,
                    )
                )

        return manifest

    def _download_pdf(
        self,
        url,
        path,
    ):
        if (
            path.exists()
            and path.stat().st_size > 10000
        ):
            print(
                " download: cached "
                "({:.1f} MB)".format(
                    path.stat().st_size
                    / 1024
                    / 1024
                )
            )
            return

        partial_path = Path(
            str(path) + ".part"
        )

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
            existing_size = (
                partial_path.stat().st_size
                if partial_path.exists()
                else 0
            )

            headers = {
                "User-Agent": (
                    self.config.user_agent
                ),
                # Important for byte-range resume.
                "Accept-Encoding": "identity",
            }

            if existing_size:
                headers["Range"] = (
                    "bytes={}-".format(
                        existing_size
                    )
                )

                print(
                    " download: resume from "
                    "{:.1f} MB".format(
                        existing_size
                        / 1024
                        / 1024
                    )
                )
            else:
                print(
                    " download:",
                    url,
                )

            try:
                response = requests.get(
                    url,
                    headers=headers,
                    stream=True,

                    # Do not allow an apparently
                    # frozen TCP connection forever.
                    #
                    # connect timeout: 10 sec
                    # read timeout:    25 sec
                    timeout=(10, 25),
                )

                if (
                    response.status_code
                    in retryable
                ):
                    raise requests.HTTPError(
                        "retryable HTTP {}".format(
                            response.status_code
                        ),
                        response=response,
                    )

                # A Range request may legitimately
                # return 206 Partial Content.
                if (
                    response.status_code
                    not in (200, 206)
                ):
                    response.raise_for_status()

                if (
                    existing_size
                    and response.status_code == 206
                ):
                    mode = "ab"
                    downloaded = existing_size
                else:
                    # Server ignored Range.
                    # Restart cleanly.
                    mode = "wb"
                    downloaded = 0
                    existing_size = 0

                content_length = (
                    response.headers.get(
                        "Content-Length"
                    )
                )

                expected_total = None

                if content_length:
                    try:
                        remaining = int(
                            content_length
                        )

                        expected_total = (
                            downloaded
                            + remaining
                        )
                    except ValueError:
                        pass

                last_print_mb = -1

                with partial_path.open(
                    mode
                ) as output:
                    for chunk in (
                        response.iter_content(
                            chunk_size=256 * 1024
                        )
                    ):
                        if not chunk:
                            continue

                        output.write(chunk)

                        downloaded += len(
                            chunk
                        )

                        current_mb = int(
                            downloaded
                            / 1024
                            / 1024
                        )

                        if (
                            current_mb
                            != last_print_mb
                        ):
                            last_print_mb = (
                                current_mb
                            )

                            if expected_total:
                                print(
                                    "  {:.1f} / {:.1f} MB".format(
                                        downloaded
                                        / 1024
                                        / 1024,
                                        expected_total
                                        / 1024
                                        / 1024,
                                    )
                                )
                            else:
                                print(
                                    "  {:.1f} MB".format(
                                        downloaded
                                        / 1024
                                        / 1024
                                    )
                                )

                if (
                    partial_path.stat().st_size
                    <= 10000
                ):
                    raise RuntimeError(
                        "downloaded PDF is "
                        "unexpectedly small"
                    )

                with partial_path.open(
                    "rb"
                ) as handle:
                    magic = handle.read(5)

                if magic != b"%PDF-":
                    raise RuntimeError(
                        "downloaded file is "
                        "not a PDF"
                    )

                partial_path.replace(
                    path
                )

                print(
                    " download complete: "
                    "{:.1f} MB".format(
                        path.stat().st_size
                        / 1024
                        / 1024
                    )
                )

                time.sleep(
                    max(
                        1.0,
                        self.config.arxiv_api_delay,
                    )
                )

                return

            except (
                requests.RequestException,
                OSError,
                RuntimeError,
            ) as exc:

                if attempt >= max_attempts:
                    raise

                delay = min(
                    45.0,
                    3.0
                    * (2 ** (attempt - 1)),
                )

                print(
                    " download interrupted: {}"
                    .format(exc)
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
            "PDF download attempts exhausted"
        )

    def _write_report(
        self,
        report_path,
        manifest,
        workspace,
        run_id,
    ):
        lines = []

        lines.append(
            "# SciAgent Research Run"
        )
        lines.append("")

        lines.append(
            "**Query:** {}".format(
                manifest["query"]
            )
        )

        lines.append(
            "**Dates:** {} — {}".format(
                manifest["date_from"],
                manifest["date_to"],
            )
        )

        lines.append(
            "**Papers:** {}".format(
                len(
                    manifest["papers"]
                )
            )
        )

        lines.append("")

        for index, paper in enumerate(
            manifest["papers"],
            start=1,
        ):
            lines.append(
                "## {}. {}".format(
                    index,
                    paper["title"],
                )
            )

            lines.append("")

            lines.append(
                "- arXiv: `{}`".format(
                    paper["arxiv_id"]
                )
            )

            lines.append(
                "- Status: `{}`".format(
                    paper["status"]
                )
            )

            if paper[
                "status"
            ] != "completed":
                lines.append(
                    "- Error: `{}`".format(
                        paper.get(
                            "error"
                        )
                    )
                )
                lines.append("")
                continue

            paper_id = paper.get(
                "document_id",
                paper["arxiv_id"],
            )

            lines.append("")
            lines.append(
                "### Main claims"
            )
            lines.append("")

            compact = (
                workspace.list_artifacts(
                    run_id=run_id,
                    paper_id=paper_id,
                    kind="paper_claim",
                )
            )

            for artifact in compact:
                payload = (
                    artifact["payload"]
                )

                lines.append(
                    "- **{}:** {} "
                    "*(pages {})*".format(
                        payload.get(
                            "kind",
                            "?",
                        ),
                        payload.get(
                            "text",
                            "",
                        ),
                        ", ".join(
                            str(page)
                            for page in artifact[
                                "source_pages"
                            ]
                        ),
                    )
                )

            for label, kind in (
                ("Methods", "method"),
                ("Systems", "system"),
                ("Datasets", "dataset"),
                ("Tasks", "task"),
            ):
                artifacts = (
                    workspace.list_artifacts(
                        run_id=run_id,
                        paper_id=paper_id,
                        kind=kind,
                    )
                )

                seen = set()
                names = []

                for artifact in artifacts:
                    name = str(
                        artifact[
                            "payload"
                        ].get(
                            "name",
                            "",
                        )
                    ).strip()

                    key = name.lower()

                    if (
                        not name
                        or key in seen
                    ):
                        continue

                    seen.add(key)
                    names.append(name)

                if names:
                    lines.append("")
                    lines.append(
                        "### {}".format(
                            label
                        )
                    )
                    lines.append("")

                    for name in names[
                        :30
                    ]:
                        lines.append(
                            "- {}".format(
                                name
                            )
                        )

            lines.append("")

        report_path.write_text(
            "\n".join(lines)
            + "\n",
            encoding="utf-8",
        )
