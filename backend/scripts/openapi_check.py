"""
backend/scripts/openapi_check.py — Hygiene ratchet for MasterAgent OpenAPI contract.

Asserts:
1. No missing or duplicate operationIds.
2. No missing tags on endpoints.
3. No module-prefixed schema names (e.g. memory__config__Settings, indicating duplicate model names).
4. Tracks untyped responses against a committed baseline (contracts/openapi_gaps.json).
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Set

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_FILE = ROOT_DIR / "contracts" / "openapi.json"
GAPS_FILE = ROOT_DIR / "contracts" / "openapi_gaps.json"

def check_openapi():
    if not CONTRACT_FILE.exists():
        print(f"Error: Contract file {CONTRACT_FILE} does not exist. Run export_openapi.py first.", file=sys.stderr)
        sys.exit(1)

    spec = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))

    is_mutate = "--mutate" in sys.argv
    if is_mutate:
        # Deliberately mutate spec by stripping operationId from an operation
        paths = spec.get("paths", {})
        for path_methods in paths.values():
            for method, op in path_methods.items():
                if isinstance(op, dict) and "operationId" in op:
                    op.pop("operationId")
                    break
            else:
                continue
            break

    paths = spec.get("paths", {})
    components = spec.get("components", {}).get("schemas", {})

    operation_ids: Set[str] = set()
    errors: List[str] = []
    untyped_ops: List[str] = []

    # 1. Check Schema Names for Module Prefixes (e.g. memory__config__Settings)
    for schema_name in components.keys():
        if "__" in schema_name:
            errors.append(f"Module-prefixed schema name detected: '{schema_name}'. Rename duplicate Pydantic models.")

    # 2. Iterate Operations
    for path, methods in paths.items():
        for method, op in methods.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch", "options", "head"):
                continue

            op_id = op.get("operationId")
            op_label = f"{method.upper()} {path}"

            # Check operationId
            if not op_id:
                errors.append(f"Missing operationId: {op_label}")
            elif op_id in operation_ids:
                errors.append(f"Duplicate operationId '{op_id}': {op_label}")
            else:
                operation_ids.add(op_id)

            # Check tags
            tags = op.get("tags", [])
            if not tags:
                errors.append(f"Missing tags: {op_label}")

            # Check untyped / 200 response schema
            responses = op.get("responses", {})
            success_resp = responses.get("200") or responses.get("201")
            is_untyped = True
            if success_resp:
                content = success_resp.get("content", {})
                if "application/json" in content:
                    schema = content["application/json"].get("schema", {})
                    if schema and schema != {}:
                        is_untyped = False
            
            if is_untyped:
                untyped_ops.append(op_id or op_label)

    # Output structural errors if any
    if errors:
        if is_mutate:
            print(f"Mutation Harness Passed: Hygiene ratchet successfully caught defect ({errors[0]}).")
            sys.exit(0)
        print("OpenAPI Hygiene Check Failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    if is_mutate:
        print("Mutation Harness Failed: Mutated defect was not caught by hygiene check!", file=sys.stderr)
        sys.exit(1)

    # 3. Ratchet Baseline Check for Untyped Operations
    untyped_ops.sort()
    
    is_update_baseline = "--update-baseline" in sys.argv

    if is_update_baseline or not GAPS_FILE.exists():
        GAPS_FILE.write_text(json.dumps({"untyped_operations": untyped_ops}, indent=2) + "\n", encoding="utf-8")
        print(f"Updated hygiene baseline in {GAPS_FILE} ({len(untyped_ops)} untyped ops).")
    else:
        gaps_data = json.loads(GAPS_FILE.read_text(encoding="utf-8"))
        baseline_gaps: Set[str] = set(gaps_data.get("untyped_operations", []))
        
        new_untyped = [op for op in untyped_ops if op not in baseline_gaps]

        if new_untyped:
            print("OpenAPI Ratchet Failure — New untyped endpoints detected:", file=sys.stderr)
            for op in new_untyped:
                print(f"  - {op}", file=sys.stderr)
            print("Add a response_model or run with --update-baseline if intentional.", file=sys.stderr)
            sys.exit(1)

        fixed_gaps = len(baseline_gaps) - len(untyped_ops)
        print(f"OpenAPI Hygiene Check Passed. Baseline untyped ops: {len(untyped_ops)} (fixed: {max(0, fixed_gaps)}).")

if __name__ == "__main__":
    check_openapi()
