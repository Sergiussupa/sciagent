# Architecture contracts

## Invariants

1. Canonical scientific data is independent of agents.
2. A paper can belong to zero, one or many Collections and ResearchCells.
3. ResearchCells are views/routing scopes, never document owners.
4. Memory is not context. The model receives a bounded projection assembled by `ContextBuilder`.
5. Expensive outputs are persisted and reusable.
6. Pipeline stages communicate through durable artifacts/database records.
7. ResearchCells can form a hierarchy and split without re-downloading/re-parsing canonical papers.

## Durable entities

### ResearchRun
A search/discovery operation and its parameters/status.

### Collection
A named stable set of paper references, e.g. `agent_august_2026`.

### Paper
Canonical metadata keyed by arXiv ID.

### Raw artifacts
Full HTML, clean text and section JSON under `state/artifacts/papers/<id>`.

### PaperMemory
Structured per-paper interpretation/summary.

### Evidence
Atomic claim/result records that retain paper identity and section provenance.

### SynthesisMemory
A compact scope-level scientific picture. It is rebuildable from PaperMemory/Evidence and must not replace them.

### ResearchCell
A hierarchical domain view such as `geology -> geophysics`. Domain assignments link papers to cells many-to-many.

### WorkingMemory
Ephemeral current-task state only.

## Event-style extension

Current v0.1 records important events in `event_log`. Future pipeline consumers can react to concepts such as:

```text
PaperDiscovered
PaperStored
PaperDeepRead
PaperSummarized
EvidenceExtracted
PaperRouted
SynthesisUpdated
CellSplit
```

A future plugin should prefer consuming a durable record/event and producing a new artifact instead of reaching into another agent's private state.

## ResearchCell split example

```text
GeologyCell
    |
    +-- GeophysicsCell
    +-- GeochemistryCell
    +-- SedimentologyCell
```

No paper is moved. New child cells receive `domain_assignments` referencing existing canonical paper IDs. Each child may later own its own retriever/vector index/synthesis without duplicating raw documents.

## Future Agentic-RAG

Replace `rag/retriever.py` with hybrid retrieval while keeping the contract:

```text
(question, collection/cell scope, budget) -> ranked canonical records/evidence
```

Possible implementation:

```text
BM25/FTS + embeddings + citation graph + evidence score + recency
                    |
                    v
              ContextBroker
                    |
                    v
                   LLM
```

## Context pressure

The canonical store never needs compaction. Only the LLM surface does.

- `ContextBudget` reserves output tokens and packs prioritized blocks.
- full HTML stays in raw memory;
- paper summaries/evidence stay durable;
- `memory.compaction.prune_tool_result()` can bound large transient tool outputs;
- synthesis should periodically be rebuilt from evidence rather than repeatedly summarized from older summaries.
