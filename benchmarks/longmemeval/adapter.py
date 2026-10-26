#!/usr/bin/env python3
"""LongMemEval adapter — benchmark harness for MasterAgent (offline tooling).

Per question: fresh entity -> ingest haystack sessions as timestamped
interactions -> measure footprint -> get-context -> fixed reader LLM answers
from the memory payload -> judge LLM scores vs the reference answer.

See README.md for the protocol, the honest same-day ablation caveat, and the
environment variables (READER_*/JUDGE_*).
"""
import argparse
import json
import os
import sys
import time
import uuid

import requests

ENTITY_TYPE = "longmemeval"
INSUFFICIENT = "INSUFFICIENT_INFORMATION"
TOKEN_CHARS = 4  # heuristic: ~4 chars per token
BULK_BATCH = 50  # interactions/bulk page size


# ── MasterAgent client ────────────────────────────────────────────────────────

class MasterAgentClient:
    def __init__(self, base_url, email, password, agent_key, timeout=120):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.agent = requests.Session()
        self.agent.headers.update({"X-API-Key": agent_key, "Content-Type": "application/json"})
        r = requests.post(f"{self.base}/api/auth/login", json={"email": email, "password": password}, timeout=timeout)
        r.raise_for_status()
        self.admin = requests.Session()
        self.admin.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})

    def ingest_bulk(self, interactions):
        """POST /api/memory/interactions/bulk in pages. Returns ingested count."""
        done = 0
        for i in range(0, len(interactions), BULK_BATCH):
            page = interactions[i:i + BULK_BATCH]
            r = self.agent.post(f"{self.base}/api/memory/interactions/bulk", json=page, timeout=self.timeout)
            if r.status_code not in (200, 202):
                raise RuntimeError(f"bulk ingest failed ({r.status_code}): {r.text[:300]}")
            body = r.json()
            done += body.get("ingested", body.get("accepted", len(page)))
        return done

    def get_context(self, entity_id):
        r = self.agent.get(
            f"{self.base}/api/memory/get-context",
            params={"entity_type": ENTITY_TYPE, "entity_id": entity_id},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def admin_stats(self):
        r = self.admin.get(f"{self.base}/api/memory/admin/stats", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_settings(self):
        r = self.admin.get(f"{self.base}/api/memory/config/settings", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def set_settings(self, **kv):
        r = self.admin.put(f"{self.base}/api/memory/config/settings", json=kv, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def trigger_attribution(self):
        r = self.admin.post(f"{self.base}/api/memory/trigger/knowledge-outcome-attribution", timeout=self.timeout)
        if r.status_code != 200:
            raise RuntimeError(f"attribution trigger failed: {r.text[:200]}")

    def trigger_knowledge_generation(self):
        r = self.admin.post(f"{self.base}/api/memory/trigger/generate-knowledge", timeout=self.timeout)
        if r.status_code not in (200, 202):
            # endpoint name may differ across versions — non-fatal by contract
            print(f"  (knowledge generation trigger unavailable: {r.status_code})")


# ── Dataset ───────────────────────────────────────────────────────────────────

def load_questions(path):
    questions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


def session_to_interaction(sess_idx, date_str, session, entity_id):
    """One haystack session -> one interaction. Dates ride INSIDE the content
    (the ingest API has no timestamp override; dates-as-text is what the
    reader sees, which is what temporal reasoning needs)."""
    turns = []
    for turn in session:
        role = str(turn.get("role", "user")).capitalize()
        turns.append(f"{role}: {turn.get('content', '')}")
    content = f"[Session date: {date_str}] (session {sess_idx + 1})\n\n" + "\n\n".join(turns)
    return {
        "interaction_type": "longmemeval_session",
        "content": content,
        "primary_entity_type": ENTITY_TYPE,
        "primary_entity_id": entity_id,
        "source": "api",
        "metadata": {"benchmark": "longmemeval", "session_index": sess_idx, "session_date": date_str},
    }


def estimate_tokens(text):
    return max(1, len(text) // TOKEN_CHARS)


# ── Reader / judge (OpenAI-compatible) ────────────────────────────────────────

def chat(base_url, model, api_key, messages, timeout=180):
    r = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


READER_SYSTEM = (
    "You answer questions strictly from the provided memory context, which is "
    "everything a memory system retrieved for this user. Quote or paraphrase "
    "only what the context supports. If the context does not contain the "
    "answer, reply exactly " + INSUFFICIENT + " — never guess."
)


def serialize_context(payload, char_budget=120_000):
    """Flatten the get-context payload into reader-visible text (distilled
    tiers first — they are the memory system's answer to raw-text bloat)."""
    parts = []
    for k in payload.get("knowledge") or []:
        parts.append(f"[Knowledge] {k.get('name')}: {k.get('summary') or ''}\n{k.get('content') or ''}")
    for i in payload.get("intelligence") or []:
        parts.append(f"[Intelligence] {i.get('name')}: {i.get('summary') or ''}")
        if i.get("content"):
            parts.append(str(i["content"]))
    for m in payload.get("memories") or []:
        parts.append(f"[Memory] {m.get('content_summary') or ''}")
    for it in payload.get("interactions") or []:
        parts.append(f"[Interaction {it.get('interaction_type', '')}] {it.get('content') or ''}")
    text = "\n\n".join(p for p in parts if p.strip())
    if len(text) > char_budget:
        text = text[:char_budget] + f"\n\n[...context truncated at {char_budget} chars]"
    return text or "(empty memory)"


def reader_answer(reader, question, context_text):
    return chat(reader["base_url"], reader["model"], reader["api_key"],
                [{"role": "system", "content": READER_SYSTEM},
                 {"role": "user", "content": f"Memory context:\n\n{context_text}\n\nQuestion: {question}"}])


JUDGE_PROMPT = """You are grading a question-answering run. Compare the model's answer to the reference answer.

Question: {question}
Reference answer: {reference}
Model answer: {answer}

Grade "correct" if the model answer contains the key information of the reference answer (phrasing may differ), otherwise "incorrect". Reply with exactly one word: correct or incorrect."""


def judge_answer(judge, question, reference, answer, question_type):
    if question_type == "abstention":
        return (1 if INSUFFICIENT.lower() in answer.lower() else 0), "abstention_rule"
    verdict = chat(judge["base_url"], judge["model"], judge["api_key"],
                   [{"role": "user", "content": JUDGE_PROMPT.format(
                       question=question, reference=reference, answer=answer)}]).lower()
    score = 1 if "correct" in verdict and "incorrect" not in verdict else 0
    return score, verdict


# ── Runner ────────────────────────────────────────────────────────────────────

ABLATIONS = {
    "loop_closed": {"knowledge_retrieval_quality_weight": 0.0},
    "loop_open": {"knowledge_retrieval_quality_weight": 0.05},
}


def main():
    ap = argparse.ArgumentParser(description="LongMemEval adapter for MasterAgent")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--agent-key", required=True)
    ap.add_argument("--dataset", required=True, help="JSONL of LongMemEval questions")
    ap.add_argument("--limit", type=int, default=0, help="first N questions only")
    ap.add_argument("--skip-judge", action="store_true", help="ingest + footprint only (no LLM calls)")
    ap.add_argument("--ablation", choices=sorted(ABLATIONS), default="loop_closed")
    ap.add_argument("--out", default="results/run.jsonl")
    args = ap.parse_args()

    client = MasterAgentClient(args.base_url, args.email, args.password, args.agent_key)
    settings_before = client.get_settings()
    overrides = ABLATIONS[args.ablation]
    client.set_settings(**overrides)
    print(f"ablation={args.ablation} settings {overrides} (was "
          f"weight={settings_before.get('knowledge_retrieval_quality_weight')})")

    questions = load_questions(args.dataset)
    if args.limit:
        questions = questions[:args.limit]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    scores = []

    with open(args.out, "a", encoding="utf-8") as sink:
        for n, q in enumerate(questions, 1):
            qid = str(q.get("question_id") or f"q-{uuid.uuid4().hex[:8]}")
            entity_id = qid
            sessions = q.get("haystack_sessions") or []
            dates = q.get("haystack_dates") or ["unknown"] * len(sessions)
            interactions = [session_to_interaction(i, dates[i] if i < len(dates) else "unknown", s, entity_id)
                            for i, s in enumerate(sessions)]
            footprint_tokens = sum(estimate_tokens(ix["content"]) for ix in interactions)
            t0 = time.time()
            ingested = client.ingest_bulk(interactions) if interactions else 0
            row = {
                "question_id": qid, "question_type": q.get("question_type", ""),
                "footprint_interactions": ingested, "footprint_tokens_est": footprint_tokens,
                "ablation": args.ablation, "settings": overrides,
                "ingest_seconds": round(time.time() - t0, 1),
            }

            if args.skip_judge:
                row.update({"skipped": "no-judge smoke run"})
                print(f"[{n}/{len(questions)}] {qid}: ingested {ingested} ix, ~{footprint_tokens} tok (smoke)")
            else:
                if args.ablation == "loop_open":
                    client.trigger_attribution()
                payload = client.get_context(entity_id)
                context_text = serialize_context(payload)
                reader = {"base_url": os.environ["READER_BASE_URL"], "model": os.environ["READER_MODEL"],
                          "api_key": os.environ["READER_API_KEY"]}
                answer = reader_answer(reader, q["question"], context_text)
                judge = {"base_url": os.environ["JUDGE_BASE_URL"], "model": os.environ["JUDGE_MODEL"],
                         "api_key": os.environ["JUDGE_API_KEY"]}
                score, judge_raw = judge_answer(judge, q["question"], q.get("answer", ""), answer,
                                                q.get("question_type", ""))
                row.update({"score": score, "judge_raw": judge_raw, "answer": answer})
                scores.append(score)
                print(f"[{n}/{len(questions)}] {qid}: score={score} ({row['question_type']})")

            sink.write(json.dumps(row, ensure_ascii=False) + "\n")
            sink.flush()

    client.set_settings(**{"knowledge_retrieval_quality_weight": 0.0})
    if scores:
        by_type = {}
        for n, q in enumerate(questions):
            if n < len(scores):
                by_type.setdefault(q.get("question_type", ""), []).append(scores[n])
        print(f"\naccuracy: {sum(scores)}/{len(scores)} = {sum(scores) / len(scores):.3f}")
        for t, s in sorted(by_type.items()):
            print(f"  {t}: {sum(s)}/{len(s)} = {sum(s) / len(s):.3f}")
    print(f"results appended to {args.out}; retrieval weight restored to 0.0")


if __name__ == "__main__":
    sys.exit(main())
