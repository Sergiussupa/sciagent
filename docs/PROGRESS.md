# SciAgent Development Progress

**Snapshot:** 2026-09-06
**Stage:** working end-to-end research prototype

SciAgent has reached its first usable research-session milestone.

The system can:

- search arXiv;
- download PDFs with retry and resume;
- parse scientific papers;
- process large papers in bounded-context batches;
- extract research-design objects;
- extract scientific claims;
- persist temporary research knowledge in ResearchWorkspace;
- consolidate raw claims into compact paper-level knowledge;
- process multiple papers in one ResearchRun;
- reopen the same ResearchRun and ask multiple follow-up questions.

The project is intentionally still prototype-quality.

## Development principle

SciAgent follows a breadth-first development strategy:

> Build the full scientific-research loop first. Improve individual modules when real end-to-end usage shows that they are bottlenecks.

A module does not need to be perfect before development continues.

Useful prototype-quality modules may be temporarily frozen while adjacent parts of the architecture are implemented.

Current experiments primarily use `qwen3:14b`.

A larger and stronger model may substantially improve extraction, classification, retrieval planning and synthesis without requiring architectural changes.

The architecture should therefore remain model-agnostic instead of being over-optimized for one local model.

## Core architectural principle

```text
Memory != Context
```

The research corpus may be much larger than the LLM context window.

Documents and extracted knowledge remain persistent on disk. Each LLM call receives only a bounded subset of the information required for the current operation.

## Current end-to-end flow

```text
Research query
    |
    v
arXiv search
    |
    v
PDF download + retry/resume
    |
    v
DocumentParser
    |
    v
page-aware bounded batches
    |
    +-----------------------------+
    |                             |
    v                             v
ResearchDesignExtractor       ClaimExtractor
    |                             |
    v                             v
ResearchWorkspace <---------- checkpoints
    |
    v
PaperConsolidator
    |
    v
compact paper knowledge
    |
    v
persistent ResearchRun
    |
    v
interactive sciagent ask
```

# Current module status

## arXiv acquisition

Status: **working prototype**

Implemented:

- keyword search;
- date filtering;
- natural-language keyword decomposition;
- strict and broad fallback search;
- local metadata relevance ranking;
- retry/backoff;
- timeout recovery;
- metadata extraction;
- PDF URL discovery.

Assessment:

**Good enough for current arXiv experiments.**

Search relevance is not yet research-grade. Broad fallback queries may return weakly related papers.

## PDF downloader

Status: **working prototype**

Implemented:

- streaming downloads;
- progress display;
- connection/read timeouts;
- retry;
- exponential backoff;
- `.part` files;
- HTTP Range resume;
- cached PDF reuse;
- basic PDF validation.

Assessment:

**Strong prototype.**

A real interrupted ~19 MB arXiv download successfully resumed from the partial file.

## DocumentParser

Status: **prototype**

Implemented:

- PyMuPDF text extraction;
- page preservation;
- title extraction;
- abstract extraction;
- section detection;
- numbered and unnumbered section handling;
- document structure usable by downstream extractors.

Assessment:

**Good enough for current multi-paper experiments.**

The parser is not yet evidence-grade canonical document infrastructure.

Future work includes:

- stable canonical element IDs;
- detailed provenance;
- tables;
- figures;
- formulas;
- source reconciliation.

## ResearchDesignExtractor

Status: **working prototype**

Extracts:

- research questions;
- methods;
- systems;
- datasets;
- models;
- baselines;
- tasks;
- metrics;
- experimental conditions.

Supports iterative page-aware bounded-context processing.

Assessment:

**Useful but noisy.**

Large papers and review papers may produce duplicate or overly specific research-design objects.

Semantic normalization is intentionally deferred.

## ClaimExtractor

Status: **working prototype**

Extracts:

- CONTRIBUTION;
- FINDING;
- INTERPRETATION;
- LIMITATION;
- epistemic type;
- source pages;
- confidence.

Supports incremental batch processing and persistent checkpoints.

Assessment:

**Useful raw scientific knowledge extraction.**

Raw claims intentionally remain detailed and may contain redundancy.

## PaperConsolidator

Status: **working prototype**

Performs hierarchical bounded-context reduction:

```text
raw claims
    |
    v
small consolidation groups
    |
    v
intermediate reductions
    |
    v
compact paper claims
```

The original raw claims remain preserved.

Intermediate consolidation artifacts are persisted for crash recovery.

Assessment:

**Important and already useful prototype.**

Semantic prioritization is imperfect. Some implementation details may survive consolidation while some important details may be compressed too aggressively.

## ResearchWorkspace

Status: **strong prototype**

Persistent SQLite task-scoped research memory.

Stores:

- raw claims;
- consolidated paper claims;
- research questions;
- methods;
- systems;
- datasets;
- models;
- baselines;
- tasks;
- metrics;
- conditions;
- consolidation intermediates;
- checkpoints.

Implemented:

- persistence;
- exact artifact deduplication;
- source-page accumulation;
- stage checkpoints;
- failure recovery;
- run-scoped storage;
- counts and snapshots.

Assessment:

**One of the strongest current architectural components.**

It demonstrates that research memory can be persistent and much larger than the LLM context.

## ResearchRunPipeline

Status: **working integration prototype**

Current flow:

```text
query
 -> arXiv
 -> N papers
 -> download
 -> parse
 -> research design extraction
 -> claim extraction
 -> paper consolidation
 -> one persistent workspace
```

Previously completed stages are reused after restart.

Assessment:

**First complete end-to-end SciAgent workflow.**

## ResearchSession / sciagent ask

Status: **early working prototype**

Supports:

- reopening an existing ResearchRun;
- multiple sequential questions;
- follow-up questions;
- persistent dialogue history;
- Russian-language questions over mostly English scientific knowledge;
- retrieval-query planning;
- bounded knowledge retrieval;
- answers with internal `[K...]` knowledge references.

Dialogue history remains outside the active LLM context.

Only recent dialogue and relevant retrieved knowledge are supplied to each answer.

Assessment:

**Already useful, but not yet evidence-grade.**

# Validation status

Current automated tests:

```text
27 passed
```

Current contracts include:

- CanonicalDocument@0.1
- ClaimSet@0.1
- EntityList@0.1
- PaperKnowledge@0.1
- ResearchDesign@0.1

# First real 10-paper milestone

Research query:

```text
neuromorphic vision event cameras
```

Observed result:

```text
papers requested: 10
papers completed: 10
papers failed: 0
```

The resulting ResearchWorkspace contained:

| Knowledge type | Count |
|---|---:|
| raw claims | 400 |
| consolidated paper claims | 107 |
| research questions | 115 |
| methods | 214 |
| systems | 103 |
| datasets | 146 |
| models | 140 |
| baselines | 92 |
| tasks | 99 |
| metrics | 165 |
| conditions | 121 |
| consolidation groups | 81 |

This demonstrates that SciAgent can process a corpus larger than one LLM context and preserve it as reusable research memory.

See:

`docs/demos/event_vision_10_v01.md`

# Current limitations

These are observations, not yet the project's prioritized issue list.

Detailed problems will be discussed separately before being turned into tracked issues.

Current limitations include:

- arXiv is currently the only acquisition source;
- search relevance can still be noisy;
- research-design extraction produces duplicates;
- retrieval remains relatively simple;
- `[K...]` citations are internal knowledge references rather than polished paper/page citations;
- synthesis may occasionally turn a plausible inference into a stronger claim than the retrieved evidence directly supports;
- evidence-grade source provenance is not yet implemented;
- tables and figures are not part of the normal evidence pipeline;
- there is no long-term KnowledgeReconciler yet;
- interactive sessions cannot yet autonomously search for new papers and extend the current workspace;
- ResearchRun identity/query protection is still incomplete.

These limitations do not block continued architectural development.

# Development philosophy

SciAgent intentionally avoids endlessly optimizing a single module before the rest of the system exists.

The preferred loop is:

```text
working prototype
    |
    v
real end-to-end use
    |
    v
observe actual bottlenecks
    |
    v
improve the bottlenecks that matter
```

A model-dependent component that works reasonably well with a 14B model does not need to be optimized indefinitely before testing the rest of the architecture.

Model quality and architecture quality are treated as related but separate concerns.

# Next milestone

The next major interactive capability is:

```text
ANSWER_FROM_WORKSPACE
SEARCH_AND_EXTEND_WORKSPACE
```

Target interaction:

```text
sciagent> Какие основные технологии используются?

sciagent> Какие из них лучше работают при слабом освещении?

sciagent> Найди ещё свежие статьи про event-based SLAM.

[search arXiv]
[process new papers]
[extend the same ResearchWorkspace]

sciagent> Теперь пересмотри предыдущий вывод.
```

After this milestone, development can increasingly focus on scientific grounding, evidence verification, retrieval quality, cross-paper synthesis and long-term knowledge reconciliation.
