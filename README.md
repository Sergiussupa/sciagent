# Scientific Research Agent v0.1

Clean-room Python 3.8+ prototype for persistent scientific research over arXiv.

It is deliberately split into **canonical knowledge**, **pipelines**, **ResearchCells**, **context management**, and **LLM policy** so later components (agentic RAG, new sources, domain sub-agents, citation graphs, embeddings) can be added without rewriting ingestion.

## What works now

- Search arXiv by keyword + date interval through the arXiv export API.
- Persist the search as `ResearchRun` + named `Collection` in SQLite.
- Reuse the active collection in later commands, even after restarting the program.
- Save canonical paper metadata once; collections/cells reference papers instead of copying them.
- Summarize every paper from abstract, or use `--deep` to open arXiv HTML with Playwright, extract clean sections, save raw HTML/text/sections, then summarize selected sections.
- Five memory layers:
  1. raw artifacts (`raw.html`, `clean.txt`, `sections.json`)
  2. `paper_memory`
  3. atomic `evidence`
  4. `synthesis_memory`
  5. bounded working context assembled by `ContextBuilder`
- Context budget defaults to 8k tokens with 1500 reserved for output. Large papers are not repeatedly injected wholesale.
- ResearchCells: assign one paper to multiple domain views; split a parent cell into child cells without reparsing documents.
- Basic RAG over saved paper memory/evidence, scoped to a collection or ResearchCell.
- Append-only `event_log` and `pipeline_runs` for resumability/auditing scaffolding.

## Install on the existing machine

```bash
cd ~/scientific_research_agent_v0_1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # optional; shell env vars are what the code reads today
python -m sciagent init
python -m sciagent doctor
```

The code defaults to `./state` for persistent state. Run commands from the project directory, or set `SCIAGENT_HOME` to an absolute path.

## The exact conversation scenario

### 1. Find papers containing `agent` in August 2026 and remember the result

```bash
python -m sciagent search \
  --query agent \
  --from 2026-08-01 \
  --to 2026-08-31 \
  --name agent_august_2026 \
  --max 300
```

That makes `agent_august_2026` the **active collection** and stores all returned paper IDs/metadata in SQLite.

Inspect it later:

```bash
python -m sciagent collections
python -m sciagent papers --collection agent_august_2026 --limit 30
```

### 2. Later: "look what they are about and send me a summary of each"

If no collection is specified, `summarize` uses the active collection:

```bash
python -m sciagent summarize
```

By default this is abstract-level and therefore much faster. For selected papers, do deep browser reading:

```bash
python -m sciagent summarize --collection agent_august_2026 --limit 10 --deep --force
```

`--deep` obeys a 16 second navigation interval by default and stores full HTML artifacts under:

```text
state/artifacts/papers/<arxiv-id>/
  raw.html
  clean.txt
  sections.json
```

### 3. Build/update a cross-paper synthesis

```bash
python -m sciagent synthesize \
  --collection agent_august_2026 \
  --goal "What changed in AI-agent research during August 2026?"
```

### 4. Ask the saved collection later (basic Agentic-RAG foundation)

```bash
python -m sciagent rag \
  --collection agent_august_2026 \
  --question "Which papers concern long-term memory in agents?"
```

## LLM behavior

Default provider is `auto`:

1. If Ollama responds at `http://127.0.0.1:11434`, use it.
2. Otherwise use an **extractive fallback** that does not hallucinate but is only a placeholder summary (mostly abstract preservation).

Typical local configuration:

```bash
export SCIAGENT_LLM=ollama
export SCIAGENT_MODEL='qwen2.5:7b'
export OLLAMA_URL='http://127.0.0.1:11434'
```

Or pass a model per command:

```bash
python -m sciagent summarize --model 'your-installed-model'
```

## Context architecture (8k window)

`ContextBuilder` treats memory and prompt context as different things.

For a deep paper summary it keeps required blocks (task/title/abstract) and selects a small set of high-value sections such as methods, experiments, results, ablations, limitations and conclusions. `ContextBudget` then packs blocks into approximately `SCIAGENT_CONTEXT_TOKENS - SCIAGENT_OUTPUT_RESERVE`.

The raw article is never deleted. A later pipeline can return to exact source sections instead of recursively summarizing summaries.

## ResearchCells

Route the active collection into reusable domain views:

```bash
python -m sciagent route --collection agent_august_2026
python -m sciagent cells list
```

Create a domain hierarchy manually:

```bash
python -m sciagent cells create geology
python -m sciagent cells split geology geophysics geochemistry sedimentology
python -m sciagent cells list
```

A paper may be assigned to multiple cells. A future geoscience RAG and physics RAG can therefore reference the same canonical paper without copying/re-reading it.

Ask only one cell:

```bash
python -m sciagent rag \
  --cell ai_agents \
  --question "What mechanisms are proposed for persistent agent memory?"
```

## Architecture

```text
sources/arxiv.py                  discovery
        |
        v
ResearchRun -> Collection -> canonical Paper store
                              |
              +---------------+----------------+
              |                                |
              v                                v
       browser/arxiv_reader              cells/router
              |                                |
              v                                v
       Raw artifacts                       ResearchCells
              |
              v
         PaperMemory
              |
              v
       Evidence Ledger
              |
              v
       Synthesis Memory
              |
              v
       ContextBuilder ----> LLM
              |
              +----> RAG / future agents / future pipelines
```

## Extension contracts

Add a new source by producing `Paper` objects. Add a new downstream capability by consuming canonical paper/memory/evidence records. Avoid putting domain ownership into `Paper` itself.

Useful next plugins:

- Semantic Scholar/OpenAlex citation enricher.
- Embedding/hybrid retriever replacing the intentionally simple lexical retriever.
- LLM domain router with hierarchical ResearchCell decomposition.
- Evidence contradiction clustering.
- Periodic synthesis rebuild directly from Evidence Ledger to avoid summary drift.
- Browser decision policy (`observe -> decide -> act`) on top of the existing browser runtime.
- Pipeline scheduler/resume by `pipeline_runs`.

## Safety / arXiv behavior

Discovery uses the arXiv export API rather than automating the web `/search` page. Deep reading uses `/html/<id>` via Playwright with a conservative navigation delay. Do not add stealth/CAPTCHA bypass logic.
