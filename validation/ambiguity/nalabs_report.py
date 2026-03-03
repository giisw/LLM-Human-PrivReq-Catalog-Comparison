import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime

import pandas as pd


DEFAULT_NEGATIVE_SMELLS = [
    "Not a Requirement",
    "Low Readability",
    "Ambiguity Detected",
    "Vagueness",
    "Subjectivity Detected",
    "Subjectivity",
    "Weakness",
    "Optionality",
]

EXCLUDED_FIELDS = {"Conjunction", "Continuances", "Imperatives", "References"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_present(v: Any) -> bool:
    if v is True:
        return True
    if v is False or v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return False


def percentile(values: List[float], p: float):
    if not values:
        return None
    vals = sorted(values)
    idx = int(p * (len(vals) - 1))
    return vals[idx]


def dedupe_preserve_order(items: List[str]) -> List[str]:
    return list(dict.fromkeys(items))


def main():
    ap = argparse.ArgumentParser(
        description="Builds aggregated metrics from NALABSpy/RCM JSON output and exports an XLSX report."
    )
    ap.add_argument(
        "nalabs_output_json",
        type=Path,
        help="Path to the NALABS output JSON (e.g., nalabs_outputFULL.json).",
    )
    ap.add_argument(
        "--negative-smells",
        type=str,
        default=",".join(DEFAULT_NEGATIVE_SMELLS),
        help="CSV list of negative smells to consider.",
    )
    ap.add_argument(
        "--out-root",
        type=Path,
        default=None,
        help="Root folder where the per-run folder will be created. Default: ./nalabs_runs",
    )
    ap.add_argument(
        "--input-json",
        type=Path,
        default=None,
        help="Path to the input JSON (default: nalabs_input.json in the same directory as the output).",
    )
    args = ap.parse_args()

    output_path: Path = args.nalabs_output_json
    if not output_path.exists():
        raise SystemExit(f"Error: file not found: {output_path}")

    negative_smells = [s.strip() for s in args.negative_smells.split(",") if s.strip()]

    # 1) Read NALABS output
    out_rows = load_json(output_path)
    if not isinstance(out_rows, list):
        raise SystemExit("Error: output must be a JSON array (list).")

    out_by_id = {
        str(r.get("ID")): r
        for r in out_rows
        if isinstance(r, dict) and r.get("ID") is not None
    }
    output_records = len(out_by_id)

    # 2) Read NALABS input to obtain the true N (full catalog)
    input_path = args.input_json if args.input_json is not None else output_path.with_name("nalabs_input.json")

    input_ids: List[str] = []
    input_text_by_id: Dict[str, str] = {}

    if input_path.exists():
        in_rows = load_json(input_path)
        if not isinstance(in_rows, list):
            raise SystemExit("Error: input JSON must be a JSON array (list).")

        for r in in_rows:
            if not isinstance(r, dict):
                continue
            rid = r.get("req_id") or r.get("id")
            if rid is None:
                continue
            rid = str(rid)
            input_ids.append(rid)
            input_text_by_id[rid] = str(r.get("text", "")).strip()

        input_ids = dedupe_preserve_order(input_ids)  # unique IDs
        N = len(input_ids)
        input_used = True
    else:
        # Fallback: this is NOT the "full catalog size"; it is "what exists in the output"
        input_ids = list(out_by_id.keys())
        N = len(input_ids)
        input_used = False

    if N == 0:
        raise SystemExit("Error: could not determine N (empty requirement list).")

    missing_in_output = sum(1 for rid in input_ids if rid not in out_by_id)

    # 3) Per-requirement computation
    counts: Dict[str, int] = {k: 0 for k in negative_smells}
    issues_per_req: List[int] = []
    security_related = 0
    by_req_rows = []

    for rid in input_ids:
        record = out_by_id.get(rid, {})  # if missing, assume clean
        present_smells = []

        # Security Related does NOT count as an "issue" (label only)
        sec = False
        if isinstance(record, dict) and record.get("Security Related") is True:
            sec = True
            security_related += 1

        text = input_text_by_id.get(rid, "")
        if not text and isinstance(record, dict):
            text = str(record.get("Requirement", "")).strip()

        flags = {}
        for k in negative_smells:
            flag = False
            if isinstance(record, dict) and k in record and is_present(record.get(k)):
                flag = True
                counts[k] += 1
                present_smells.append(k)
            flags[k] = flag

        issues_count = len(present_smells)
        issues_per_req.append(issues_count)

        by_req_rows.append({
            "req_id": rid,
            "text": text,
            "security_related": sec,
            "issues_count": issues_count,
            "negative_smells_list": ";".join(present_smells),
            **{f"smell__{k}": flags[k] for k in negative_smells},
        })

    # 4) Aggregated metrics
    total_issues = sum(issues_per_req)  # suma de issues_count
    clean = sum(1 for x in issues_per_req if x == 0)
    any_issue = N - clean  # requirements with >=1 negative issue

    issues_mean = statistics.mean(issues_per_req) if issues_per_req else 0.0
    issues_median = statistics.median(issues_per_req) if issues_per_req else 0.0
    issues_p90 = percentile([float(x) for x in issues_per_req], 0.90)

    percents = {k: (counts[k] / N * 100.0) for k in negative_smells}

    summary = {
        "total_requirements": N,
        "output_records": output_records,
        "missing_in_output": missing_in_output,
        "total_issues": total_issues,
        "requirements_with_issues": any_issue,
        "negative_smells_used": negative_smells,
        "excluded_fields": sorted(EXCLUDED_FIELDS),
        "count_by_smell": counts,
        "percent_by_smell": {k: round(v, 2) for k, v in percents.items()},
        "clean_rate": {"count_clean": clean, "percent_clean": round((clean / N * 100.0), 2)},
        "any_issue_rate": {"count_any_issue": any_issue, "percent_any_issue": round((any_issue / N * 100.0), 2)},
        "issues_per_requirement": {
            "mean": round(float(issues_mean), 3),
            "median": float(issues_median),
            "p90": issues_p90,
            "max": max(issues_per_req) if issues_per_req else 0,
        },
        "security_related": {
            "count": security_related,
            "percent": round((security_related / N * 100.0), 2),
            "note": "Label (non-negative); it does not count as an issue.",
        },
        "input_used_for_total": input_used,
        "notes": [
            "Security Related is NOT considered an issue (does not affect clean/any_issue).",
            "Conjunction/Continuances/Imperatives/References are excluded by design.",
            "If the input JSON is missing, N is inferred from the output and does NOT represent the true catalog size.",
        ],
    }

    # 5) Per-run output folder
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = args.out_root if args.out_root is not None else Path.cwd() / "nalabs_runs"
    run_dir = out_root / f"{output_path.stem}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_path = run_dir / f"{output_path.stem}_summary.json"
    xlsx_path = run_dir / f"{output_path.stem}_report.xlsx"

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # 6) Excel (contains all relevant outputs)
    df_by_req = pd.DataFrame(by_req_rows)

    df_summary_kv = pd.DataFrame([
        {"metric": "total_requirements", "value": N},
        {"metric": "output_records", "value": output_records},
        {"metric": "missing_in_output", "value": missing_in_output},
        {"metric": "total_issues", "value": total_issues},
        {"metric": "requirements_with_issues", "value": any_issue},
        {"metric": "clean_count", "value": clean},
        {"metric": "clean_percent", "value": summary["clean_rate"]["percent_clean"]},
        {"metric": "any_issue_count", "value": any_issue},
        {"metric": "any_issue_percent", "value": summary["any_issue_rate"]["percent_any_issue"]},
        {"metric": "issues_mean", "value": summary["issues_per_requirement"]["mean"]},
        {"metric": "issues_median", "value": summary["issues_per_requirement"]["median"]},
        {"metric": "issues_p90", "value": summary["issues_per_requirement"]["p90"]},
        {"metric": "issues_max", "value": summary["issues_per_requirement"]["max"]},
        {"metric": "security_related_count", "value": security_related},
        {"metric": "security_related_percent", "value": summary["security_related"]["percent"]},
        {"metric": "negative_smells_used", "value": ";".join(negative_smells)},
        {"metric": "excluded_fields", "value": ";".join(sorted(EXCLUDED_FIELDS))},
        {"metric": "input_used_for_total", "value": input_used},
    ])

    # This is count_by_smell and percent_by_smell in Excel
    df_smell_stats = pd.DataFrame([
        {"smell": k, "count": counts[k], "percent": round(percents[k], 2)}
        for k in negative_smells
    ])

    df_notes = pd.DataFrame([{"note": n} for n in summary["notes"]])

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_summary_kv.to_excel(writer, sheet_name="Summary", index=False)
        df_smell_stats.to_excel(writer, sheet_name="SmellStats", index=False)
        df_by_req.to_excel(writer, sheet_name="ByRequirement", index=False)
        df_notes.to_excel(writer, sheet_name="Notes", index=False)

    print(f"OK: generated in {run_dir}")
    print(f"- {summary_path.name}")
    print(f"- {xlsx_path.name}")


if __name__ == "__main__":
    main()