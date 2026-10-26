#!/usr/bin/env python3
"""Dump LongMemEval from HuggingFace to local JSONL for adapter.py.

Requires the `datasets` package (pip install datasets). The dataset fields
follow the official release: question_id, question_type, question, answer,
question_date, haystack_dates, haystack_sessions.
"""
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("--repo", default="xiaowu0162/LongMemEval", help="HuggingFace dataset id")
parser.add_argument("--config", default=None, help="dataset config if the repo requires one (e.g. LongMemEval_s)")
parser.add_argument("--split", default="test")
parser.add_argument("--out", default="longmemeval.jsonl")
args = parser.parse_args()

from datasets import load_dataset  # noqa: E402  (deliberate: only needed here)

ds = load_dataset(args.repo, args.config, split=args.split)
with open(args.out, "w", encoding="utf-8") as f:
    for row in ds:
        f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
print(f"wrote {len(ds)} questions to {args.out}")
