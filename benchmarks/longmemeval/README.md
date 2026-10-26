# LongMemEval adapter for MasterAgent

Benchmark harness for the "experiential learning without experience bloat"
paper (see `docs/plans/knowledge-learning-loop.md` §10). This directory is
**offline tooling** — it talks to a running MasterAgent over HTTP and shares
nothing with the app's hermetic test suite.

## What it measures

For every LongMemEval question:

1. **Ingest** — the question's haystack sessions become timestamped MasterAgent
   interactions under a fresh entity (`longmemeval/<question_id>`). Each
   interaction's content begins with `[Session date: YYYY-MM-DD]` so temporal
   reasoning sees dates as text (the ingest API has no timestamp override by
   design — dates as content is what get-context's reader actually sees).
2. **Footprint** — interaction count + estimated tokens ingested for the
   question (the x-axis of the growth-curve plot).
3. **Answer** — `GET /api/memory/get-context` returns the memory payload; a
   FIXED reader LLM answers the question strictly from that payload, replying
   `INSUFFICIENT_INFORMATION` when it can't. The memory system is evaluated in
   isolation: scores reflect memory quality, not agent scaffolding.
4. **Judge** — an LLM judge scores the answer 0/1 against the reference
   answer (official LongMemEval protocol). Abstention questions score correct
   only when the reader says `INSUFFICIENT_INFORMATION`.

Knowledge-tier contamination across questions is real (get-context's
knowledge tier is global) and is treated as system-level behavior — recorded,
not hidden. This is the honest comparison against append-only baselines.

## Layout

| File | Purpose |
|---|---|
| `adapter.py` | The harness (ingest → footprint → get-context → reader → judge → results) |
| `download_dataset.py` | Dump LongMemEval from HuggingFace to local JSONL |
| `requirements.txt` | `requests` (+ `datasets` only for downloading) |

## Usage

```powershell
cd benchmarks/longmemeval
pip install -r requirements.txt

# 1. one-time dataset dump (needs the `datasets` package)
python download_dataset.py --split LongMemEval_s --out longmemeval_s.jsonl

# 2. smoke run: ingest + footprint only, no LLM calls (bench_smoke.jsonl is a
#    committed 3-question fixture; the real dataset needs step 1)
python adapter.py --base-url http://localhost:8084 --email ... --password ... `
    --agent-key ... --dataset bench_smoke.jsonl --skip-judge

# 3. full run (needs reader/judge env: READER_* and JUDGE_* below)
$env:READER_BASE_URL="https://api.openai.com/v1"; $env:READER_MODEL="gpt-4o-mini"; $env:READER_API_KEY="..."
$env:JUDGE_BASE_URL="..."; $env:JUDGE_MODEL="..."; $env:JUDGE_API_KEY="..."
python adapter.py --base-url http://localhost:8084 --email ... --password ... `
    --agent-key ... --dataset longmemeval_s.jsonl --out results/run1.jsonl
```

Reader and judge are any OpenAI-compatible chat endpoints (the Z.AI/GLM
endpoints used elsewhere in this setup work via their OpenAI-compatible base
URLs). Reader and judge should be DIFFERENT models, or the judge is grading
its own family's phrasing.

`--agent-key` is a **memory agent** key (`mem_...`), not a prompt-manager
`pm_` key — memory endpoints authenticate against `memory_agents`
(Settings → Memory Agents in the UI, or `POST /api/memory/config/agents`
as admin).

## Ablations (the paper's core experiment)

`--ablation loop_closed` (default) and `--ablation loop_open` flip the
learning-loop settings via the admin API before the run:

| Mode | `knowledge_retrieval_quality_weight` | Attribution |
|---|---|---|
| loop_closed | 0.0 | on |
| loop_open | 0.05 | on + attribution triggered after ingest |

Honesty note baked into the design: within a single same-day run the loop's
effect is ~0 by construction (recurrence needs retrievals ≥7d apart; echo
failures need lessons distilled after events). Meaningful loop-open/closed
deltas need the **multi-day protocol**: run ingest+answer daily against a
long-lived stack while the nightly `knowledge_outcome_attribution` job
processes events, then compare curves. The scaffold records
`ablation` + settings on every result row so multi-day runs aggregate cleanly.

## Results format

One JSON object per question:

```json
{"question_id": "...", "question_type": "temporal_reasoning", "score": 1,
 "judge_raw": "correct", "footprint_interactions": 27, "footprint_tokens_est": 104512,
 "answer": "...", "ablation": "loop_closed", "settings": {...}}
```

Summary (accuracy overall + per question_type, mean footprint) prints at the
end and is the input to `curves.py`-style analysis (accuracy vs footprint,
loop-open vs loop-closed) — plotted in the paper, not here.
