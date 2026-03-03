import os
import json
from datetime import datetime
import argparse

import pandas as pd
import matplotlib.pyplot as plt
from bert_score import BERTScorer

# -------------------- ARGUMENT PARSING --------------------
parser = argparse.ArgumentParser(description="BERTScore requirement–reference evaluator (strict JSON input)")

parser.add_argument('--reqfile', type=str, required=True, help='Requirements file (Excel or JSON)')
parser.add_argument('--reffile', type=str, required=True, help='References file (JSON, strict schema)')
parser.add_argument(
    '--lang',
    type=str,
    default='auto',
    choices=['auto', 'es', 'en'],
    help="Language for BERTScore and normative text selection (auto=use idioma_catalogo from the references JSON)"
)
parser.add_argument('--rescale', action='store_true', help='Apply baseline rescaling (optional)')

args = parser.parse_args()

# -------------------- CONFIGURATION --------------------
requirements_file = args.reqfile
references_file = args.reffile
use_rescale = args.rescale

# Output folder
output_dir = "results_" + datetime.now().strftime("%Y%m%d_%H%M%S")
os.makedirs(output_dir, exist_ok=True)


# -------------------- LOADING FUNCTIONS --------------------
def load_requirements(path: str) -> pd.DataFrame:
    """Load requirements from an Excel or JSON file.

    Supported formats:
      - Excel: expected columns: ID, Título, Texto (normalized internally)
      - JSON: expected structure:
        {
          "catalog_id": "...",
          "requisitos": [
            { "id": "...", "titulo": "...", "descripcion": "..." }
          ]
        }

    Returns a DataFrame with internal columns: id, title, text

    IMPORTANT:
      - Input JSON keys remain in Spanish to preserve upstream compatibility.
      - Only internal column names are normalized to English.
    """
    ext = os.path.splitext(path)[1].lower()

    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(path)
        # Normalize internal column names (keep CLI args and input structures unchanged).
        df = df.rename(columns={"ID": "id", "Título": "title", "Texto": "text"})
        return df

    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        requisitos = data.get("requisitos", [])
        rows: list[dict] = []
        for r in requisitos:
            rows.append({"id": r.get("id"), "title": r.get("titulo", ""), "text": r.get("descripcion", "")})

        return pd.DataFrame(rows)

    raise ValueError(f"Unsupported requirements file format: {ext}")


def load_references(path: str, lang_arg: str = "auto") -> tuple[pd.DataFrame, str]:
    """Load references from a strict-schema JSON file.

    Expected JSON structure:
    {
      "catalog_id": "...",
      "idioma_catalogo": "es|en",
      "referencias": [
        {
          "id": "...",
          "referencia_normativa": "...",
          "idioma_normativo_original": "es|en|desconocido",
          "texto_normativo_es": "...",
          "texto_normativo_en": "..."
        }
      ]
    }

    Returns:
      - DataFrame with internal columns: id, text, legal_reference
      - detected idioma_catalogo (str)

    IMPORTANT:
      - Input JSON keys remain in Spanish to preserve upstream compatibility.
      - The returned DataFrame column names remain aligned with the existing workflow.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(
            "The references JSON must be an object (dict) with keys 'idioma_catalogo' and 'referencias'."
        )

    catalog_language = data.get("idioma_catalogo")
    if catalog_language not in ("es", "en"):
        raise ValueError(
            f"Invalid or missing idioma_catalogo in references JSON: {catalog_language!r}. It must be 'es' or 'en'."
        )

    references = data.get("referencias")
    if not isinstance(references, list):
        raise ValueError("The 'referencias' key must exist and be a list.")

    # Language to use for BERTScore and normative-text selection
    usage_language = lang_arg if lang_arg != "auto" else catalog_language
    if usage_language not in ("es", "en"):
        raise ValueError(f"Invalid usage language: {usage_language!r}")

    rows: list[dict] = []
    for i, ref in enumerate(references):
        if not isinstance(ref, dict):
            raise ValueError(f"Entry referencias[{i}] is not a JSON object.")

        required_keys = (
            "id",
            "referencia_normativa",
            "idioma_normativo_original",
            "texto_normativo_es",
            "texto_normativo_en",
        )
        for k in required_keys:
            if k not in ref:
                raise ValueError(f"Missing required key '{k}' in referencias[{i}].")

        normative_text = ref.get(f"texto_normativo_{usage_language}")
        if normative_text is None or str(normative_text).strip() == "":
            raise ValueError(
                f"texto_normativo_{usage_language} is empty in referencias[{i}] (id={ref.get('id')})."
            )

        rows.append(
            {
                "id": ref.get("id"),
                "text": normative_text,
                "legal_reference": ref.get("referencia_normativa", ""),
            }
        )

    return pd.DataFrame(rows), catalog_language


# -------------------- DATA LOADING --------------------
print("\n Loading requirements and references...")

requirements_df = load_requirements(requirements_file)

references_ext = os.path.splitext(references_file)[1].lower()
if references_ext != ".json":
    raise ValueError("The references file must be JSON (.json).")

references_df, detected_catalog_language = load_references(references_file, args.lang)

# Determine final language for BERTScore
bertscore_language = args.lang if args.lang != "auto" else detected_catalog_language

if args.lang != "auto" and args.lang != detected_catalog_language:
    print(
        f"\n [WARNING] The references JSON indicates idioma_catalogo='{detected_catalog_language}', "
        f"but --lang='{args.lang}' was explicitly provided."
    )

print(f"\n Selected BERTScore language: {bertscore_language}")
print(f" Baseline rescaling: {'yes' if use_rescale else 'no'}")

# -------------------- SCORING --------------------
scorer = BERTScorer(lang=bertscore_language, rescale_with_baseline=use_rescale)

result_ids: list = []
result_titles: list = []
precision_list: list[float] = []
recall_list: list[float] = []
f1_list: list[float] = []
best_legal_reference_list: list[str] = []
best_normative_excerpt_list: list[str] = []

print("\n Scoring with BERTScore (best reference per requirement)...")

for _, requirement_row in requirements_df.iterrows():
    requirement_id = requirement_row.get("id")
    requirement_title = requirement_row.get("title", "")
    requirement_text = requirement_row.get("text", "")

    if pd.isna(requirement_id) or pd.isna(requirement_text) or str(requirement_text).strip() == "":
        continue

    reference_group_df = (
        references_df[references_df["id"] == requirement_id]
        .dropna(subset=["text"])
        .copy()
    )
    reference_group_df["text"] = reference_group_df["text"].astype(str)

    reference_texts = reference_group_df["text"].tolist()
    if not reference_texts:
        print(f" Requirement {requirement_id} has no references. Skipping...")
        continue

    candidate_texts = [str(requirement_text)] * len(reference_texts)
    P, R, F1 = scorer.score(candidate_texts, reference_texts)

    best_idx = int(F1.argmax().item())

    result_ids.append(requirement_id)
    result_titles.append(requirement_title)

    precision_list.append(float(P[best_idx].item()))
    recall_list.append(float(R[best_idx].item()))
    f1_list.append(float(F1[best_idx].item()))

    best_normative_excerpt_list.append(reference_texts[best_idx])

    legal_references = reference_group_df["legal_reference"].fillna("").astype(str).tolist()
    best_legal_reference_list.append(legal_references[best_idx] if best_idx < len(legal_references) else "")

# -------------------- EXPORT RESULTS --------------------
results_df = pd.DataFrame(
    {
        "id": result_ids,
        "title": result_titles,
        "precision": precision_list,
        "recall": recall_list,
        "f1": f1_list,
        "best_legal_reference": best_legal_reference_list,
        "best_normative_excerpt": best_normative_excerpt_list,
    }
)

excel_path = os.path.join(output_dir, "bertscore_results.xlsx")
results_df.to_excel(excel_path, index=False)
print(f"\n Results saved (Excel): {excel_path}")

json_path = os.path.join(output_dir, "bertscore_results.json")
results_df.to_json(json_path, orient="records", force_ascii=False, indent=2)
print(f" Results saved (JSON): {json_path}")

# -------------------- PLOTS --------------------
if f1_list:
    plt.figure()
    plt.hist(f1_list, bins=20)
    plt.xlabel("F1 Score")
    plt.ylabel("Count")
    plt.title("F1 Score distribution")
    plt.savefig(os.path.join(output_dir, "f1_histogram.png"))

    plt.figure(figsize=(10, 5))
    plt.plot(f1_list, marker='o', label='F1 Score')
    plt.plot(precision_list, linestyle='--', label='Precision')
    plt.plot(recall_list, linestyle='-.', label='Recall')
    plt.title("BERTScore per requirement (best reference)")
    plt.xlabel("Requirement index")
    plt.ylabel("Score")
    plt.ylim(0, 1)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "metrics_lines.png"))

print("\n Evaluation completed successfully.")
