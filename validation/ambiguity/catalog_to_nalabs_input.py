import json
import sys
from pathlib import Path


def main() -> None:
    """Convert a requirements catalog JSON into NaLAbS input format.

    Input JSON schema is kept unchanged (e.g., 'requisitos', 'descripcion').
    Output is a JSON list of objects: [{'req_id': ..., 'text': ...}, ...].
    """
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python catalog_to_nalabs_input.py <catalog.json> [output.json]")

    in_path = Path(sys.argv[1])

    # If no output path is provided, use a default filename next to the input file.
    if len(sys.argv) >= 3:
        out_path = Path(sys.argv[2])
    else:
        out_path = in_path.with_name(in_path.stem + "_nalabs_input.json")

    with in_path.open("r", encoding="utf-8") as f:
        catalog = json.load(f)

    requirements = catalog.get("requisitos")
    if not isinstance(requirements, list):
        raise SystemExit("Error: expected a list under key 'requisitos' in the input JSON.")

    rows = []
    for i, r in enumerate(requirements, start=1):
        if not isinstance(r, dict):
            continue
        rid = r.get("id") or f"REQ-{i:04d}"
        rows.append(
            {
                "req_id": str(rid),
                "text": (r.get("descripcion") or "").strip(),
            }
        )

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"OK: {out_path} ({len(rows)} requirements)")


if __name__ == "__main__":
    main()
