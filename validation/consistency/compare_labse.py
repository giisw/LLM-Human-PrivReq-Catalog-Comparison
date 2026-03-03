import os
import json
import argparse
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt

from sentence_transformers import SentenceTransformer, util


# -------------------- CLI ARGUMENTS --------------------
parser = argparse.ArgumentParser(
    description="LaBSE-based requirement–reference evaluator (semantic similarity)"
)

# IMPORTANT: do not rename CLI arguments (compatibility requirement)
parser.add_argument('--reqfile', type=str, required=True, help='Requirements file (Excel or JSON)')
parser.add_argument('--reffile', type=str, required=True, help='References file (Excel or JSON, strict schema)')
parser.add_argument('--model', type=str, default='sentence-transformers/LaBSE', help='Sentence-Transformers model name (default: sentence-transformers/LaBSE)')

args = parser.parse_args()

requirements_file = args.reqfile
references_file = args.reffile
labse_model_name = args.model

# Output folder
run_dir = "results_labse_" + datetime.now().strftime("%Y%m%d_%H%M%S")
os.makedirs(run_dir, exist_ok=True)


# -------------------- LOADERS --------------------
def load_requirements(path: str) -> pd.DataFrame:
    """
    Load requirements from:
      - Excel with columns: ID, Título, Texto
      - JSON with structure:
        {
          "catalog_id": "...",
          "requisitos": [
            { "id": "...", "titulo": "...", "descripcion": "..." }
          ]
        }

    The input JSON keys are NOT modified (compatibility requirement).
    Returns a DataFrame with internal columns: id, title, text
    """
    ext = os.path.splitext(path)[1].lower()

    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(path)
        expected = {"ID", "Título", "Texto"}
        if not expected.issubset(set(df.columns)):
            raise ValueError(f"Requirements Excel must contain columns {expected}")
        df = df[["ID", "Título", "Texto"]].copy()
        return df.rename(columns={"ID": "id", "Título": "title", "Texto": "text"})

    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        requirements = data.get("requisitos", [])
        rows = []
        for r in requirements:
            rows.append({
                "id": r.get("id"),
                "title": r.get("titulo", ""),
                "text": r.get("descripcion", "")
            })
        return pd.DataFrame(rows)

    raise ValueError(f"Unsupported requirements file format: {ext}")


def load_references(path: str) -> pd.DataFrame:
    """
    Load references from:
      - Excel with columns: ID, Texto
        (optionally: Referencia_normativa, Idioma_normativo_original)
      - JSON with structure:
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

    For LaBSE, the script ALWAYS uses the regulatory text in the ORIGINAL language:
      - text = texto_normativo_<idioma_normativo_original> if language is 'es' or 'en'
      - if idioma_normativo_original is 'desconocido' (or anything else), text = "" (discarded)

    Returns a DataFrame with internal columns:
      - id
      - text
      - legal_reference
      - original_language
    """
    ext = os.path.splitext(path)[1].lower()

    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(path)

        expected = {"ID", "Texto"}
        if not expected.issubset(set(df.columns)):
            raise ValueError(f"References Excel must contain columns {expected}")

        # Optional columns (keep backward compatible naming)
        if "Referencia_normativa" not in df.columns and "referencia_normativa" in df.columns:
            df = df.rename(columns={"referencia_normativa": "Referencia_normativa"})
        if "Referencia_normativa" not in df.columns:
            df["Referencia_normativa"] = ""

        if "Idioma_normativo_original" not in df.columns and "idioma_normativo_original" in df.columns:
            df = df.rename(columns={"idioma_normativo_original": "Idioma_normativo_original"})
        if "Idioma_normativo_original" not in df.columns:
            df["Idioma_normativo_original"] = ""

        df = df[["ID", "Texto", "Referencia_normativa", "Idioma_normativo_original"]].copy()
        return df.rename(columns={
            "ID": "id",
            "Texto": "text",
            "Referencia_normativa": "legal_reference",
            "Idioma_normativo_original": "original_language"
        })

    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("References JSON must be an object (dict) containing key 'referencias'.")

        references = data.get("referencias", [])
        if not isinstance(references, list):
            raise ValueError("Key 'referencias' must exist and be a list.")

        rows = []
        for r in references:
            original_language = r.get("idioma_normativo_original", "desconocido")

            if original_language in ("es", "en"):
                ref_text = r.get(f"texto_normativo_{original_language}", "") or ""
            else:
                ref_text = ""  # unknown / not verifiable

            rows.append({
                "id": r.get("id"),
                "text": ref_text,
                "legal_reference": r.get("referencia_normativa", ""),
                "original_language": original_language
            })

        return pd.DataFrame(rows)

    raise ValueError(f"Unsupported references file format: {ext}")


# -------------------- LOAD DATA --------------------
print("Loading requirements and references...")
req_df = load_requirements(requirements_file)
ref_df = load_references(references_file)

if req_df.empty:
    raise RuntimeError("No requirements found in the provided file.")

if ref_df.empty:
    print("[WARNING] No references found; similarity scoring cannot be performed.")

# Keep only references with verifiable text
ref_df["text"] = ref_df["text"].fillna("").astype(str)
ref_valid_df = ref_df[ref_df["text"].str.strip() != ""].copy().reset_index(drop=True)

if ref_valid_df.empty:
    print("[WARNING] All references are empty / not verifiable; similarity scoring cannot be performed.")
else:
    print(f"Valid references: {len(ref_valid_df)} (out of {len(ref_df)})")

# -------------------- LOAD LABSE MODEL --------------------
print(f"Loading LaBSE model: {labse_model_name}")
model = SentenceTransformer(labse_model_name)

# Requirement embeddings
print("Computing requirement embeddings...")
req_embeddings = model.encode(
    req_df["text"].fillna("").astype(str).tolist(),
    batch_size=32,
    convert_to_tensor=True,
    show_progress_bar=True
)

# Reference embeddings (only valid references)
if not ref_valid_df.empty:
    print("Computing reference embeddings (original-language regulatory text)...")
    ref_embeddings = model.encode(
        ref_valid_df["text"].astype(str).tolist(),
        batch_size=64,
        convert_to_tensor=True,
        show_progress_bar=True
    )
else:
    ref_embeddings = None


# -------------------- SCORING (multi-reference, best per requirement) --------------------
print("\nScoring LaBSE similarity (best reference per requirement)...")

records = []

for i, req_row in req_df.iterrows():
    req_id = req_row["id"]
    req_title = req_row["title"]
    req_text = req_row["text"]

    if ref_embeddings is None:
        records.append({
            "id": req_id,
            "title": req_title,
            "requirement_text": req_text,
            "num_valid_references": 0,
            "best_cosine_similarity": None,
            "best_legal_reference": None,
            "best_reference_language": None,
            "best_reference_text": None
        })
        continue

    # Indices of valid references associated with this requirement
    mask = (ref_valid_df["id"] == req_id)
    idx_refs = mask[mask].index.to_list()

    if not idx_refs:
        print(f"[INFO] Requirement {req_id} has no valid references. Skipping.")
        records.append({
            "id": req_id,
            "title": req_title,
            "requirement_text": req_text,
            "num_valid_references": 0,
            "best_cosine_similarity": None,
            "best_legal_reference": None,
            "best_reference_language": None,
            "best_reference_text": None
        })
        continue

    # Requirement embedding (1 x d)
    req_emb_i = req_embeddings[i].unsqueeze(0)

    # Embeddings of associated references (k x d)
    ref_emb_i = ref_embeddings[idx_refs]

    # Cosine similarities vector (length k)
    sims = util.cos_sim(req_emb_i, ref_emb_i)[0]

    best_sim = sims.max().item()
    best_pos = sims.argmax().item()
    best_ref_idx = idx_refs[best_pos]

    best_ref_text = ref_valid_df.loc[best_ref_idx, "text"]
    best_ref_norm = ref_valid_df.loc[best_ref_idx, "legal_reference"]
    best_ref_lang = ref_valid_df.loc[best_ref_idx, "original_language"]

    records.append({
        "id": req_id,
        "title": req_title,
        "requirement_text": req_text,
        "num_valid_references": len(idx_refs),
        "best_cosine_similarity": best_sim,  # range [-1, 1]
        "best_legal_reference": best_ref_norm,
        "best_reference_language": best_ref_lang,
        "best_reference_text": best_ref_text
    })

results_df = pd.DataFrame(records)

# -------------------- SAVE OUTPUTS --------------------
excel_path = os.path.join(run_dir, "labse_results.xlsx")
json_path = os.path.join(run_dir, "labse_results.json")

results_df.to_excel(excel_path, index=False)
results_df.to_json(json_path, orient="records", force_ascii=False, indent=2)

print("\nResults saved to:")
print(f"  - Excel: {excel_path}")
print(f"  - JSON:  {json_path}")

# -------------------- PLOT --------------------
valid_results = results_df.dropna(subset=["best_cosine_similarity"])

if not valid_results.empty:
    plt.figure(figsize=(10, 5))
    plt.plot(valid_results["best_cosine_similarity"].tolist(), marker='o')
    plt.title("LaBSE similarity (cosine, -1 to 1) per requirement")
    plt.xlabel("Requirement index (with valid references)")
    plt.ylabel("LaBSE similarity (cosine)")
    plt.ylim(-1, 1)
    plt.grid(True)
    plt.tight_layout()

    plot_path = os.path.join(run_dir, "labse_similarity_lines.png")
    plt.savefig(plot_path)
    print(f"Plot saved to: {plot_path}")

print("\nLaBSE evaluation completed.")
