#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pBERT Redundancy Detection (spaCy -> BERT embeddings -> cosine similarity -> pairs -> clustering)

Expected input JSON:
{
  "catalog_id": "CAT-2025-001",
  "requisitos": [
    {"id":"R-001","descripcion":"..."},
    {"id":"R-002","descripcion":"..."}
  ]
}

Default output directory:
out/pbert_redundancy/<catalog_id>_<YYYYMMDD_HHMMSS>/

Generated files:
- summary.json
- pairs_all.csv                  (ALL pairs) [Excel-friendly: ';' separator + UTF-8 with BOM]
- pairs_redundant.csv            (cosine >= threshold; if top_k is set, additionally filtered by top-k)
- pairs_all.xlsx                 (always)
- pairs_redundant.xlsx           (always)
- clusters.json                  (clusters built from pairs_redundant)
- similarity_matrix.csv          (NxN matrix) [Excel-friendly: ';' separator + UTF-8 with BOM]
- similarity_matrix.xlsx         (only if --excel)
- req_metrics.csv                (per-requirement metrics) [Excel-friendly: ';' separator + UTF-8 with BOM]
- req_metrics.xlsx               (per-requirement metrics)
"""


import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import torch
import spacy
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModel


# -----------------------------
# Input loading and validation
# -----------------------------
def load_catalog(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if "requisitos" not in data or not isinstance(data["requisitos"], list):
        raise ValueError("The input JSON must contain a list under the 'requisitos' key.")
    for r in data["requisitos"]:
        if "id" not in r:
            raise ValueError("Each requirement must contain an 'id' field.")
    return data


def extract_descriptions(reqs: List[Dict]) -> List[str]:
    texts = []
    for r in reqs:
        d = r.get("descripcion", "")
        if d is None:
            d = ""
        texts.append(str(d).strip())
    return texts


# -----------------------------
# spaCy: language-specific loading and preprocessing
# -----------------------------
def build_spacy(lang: str):
    if lang == "es":
        return spacy.load("es_core_news_sm")
    if lang == "en":
        return spacy.load("en_core_web_sm")
    raise ValueError("lang must be either 'es' or 'en'.")


def preprocess_texts(nlp, texts: List[str]) -> List[str]:
    """
    pBERT preprocessing: remove stopwords and punctuation, then lemmatize.
    """
    cleaned = []
    for doc in tqdm(nlp.pipe(texts, batch_size=64), total=len(texts), desc="spaCy preprocess"):
        toks = []
        for t in doc:
            if t.is_space or t.is_punct:
                continue
            if t.is_stop:
                continue
            lemma = (t.lemma_ or "").strip().lower()
            if lemma:
                toks.append(lemma)
        cleaned.append(" ".join(toks))
    return cleaned


# -----------------------------
# BERT embeddings + mean pooling
# -----------------------------
@torch.no_grad()
def encode_bert(
    tokenizer,
    model,
    texts: List[str],
    batch_size: int = 32,
    max_length: int = 256,
    device: str = "cpu",
) -> np.ndarray:
    """
    Returns L2-normalized embeddings: shape (N, H)
    """
    model.to(device)
    model.eval()

    all_vecs = []
    for i in tqdm(range(0, len(texts), batch_size), desc="BERT encode"):
        batch = texts[i : i + batch_size]

        enc = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        enc = {k: v.to(device) for k, v in enc.items()}

        out = model(**enc)
        hidden = out.last_hidden_state  # (B, T, H)

        mask = enc["attention_mask"].unsqueeze(-1).type_as(hidden)  # (B, T, 1)
        summed = (hidden * mask).sum(dim=1)                         # (B, H)
        counts = mask.sum(dim=1).clamp(min=1e-9)                    # (B, 1)
        vecs = summed / counts                                      # mean pooling

        vecs = torch.nn.functional.normalize(vecs, p=2, dim=1)      # L2 norm
        all_vecs.append(vecs.detach().cpu().numpy())

    return np.vstack(all_vecs)


def cosine_matrix(emb: np.ndarray) -> np.ndarray:
    """
    L2-normalized embeddings => cosine similarity equals dot product
    """
    return emb @ emb.T


# -----------------------------
# Pairs: all / redundant (+ optional top-k filter)
# -----------------------------
@dataclass
class PairRow:
    id_a: str
    id_b: str
    score: float
    rank_from_a: int = 0
    rank_from_b: int = 0


def compute_ranks_topk(sim: np.ndarray, k: int) -> np.ndarray:
    """
    ranks[i, j] = rank (1..k) of j in i's top-k neighbors; 0 if not present.
    """
    n = sim.shape[0]
    ranks = np.zeros((n, n), dtype=np.int16)
    kk = min(k, n - 1)
    for i in range(n):
        row = sim[i].copy()
        row[i] = -1.0
        idx = np.argpartition(-row, kth=kk - 1)[:kk]
        idx = idx[np.argsort(-row[idx])]
        for r, j in enumerate(idx, start=1):
            ranks[i, j] = r
    return ranks


def build_pairs_all(sim: np.ndarray, ids: List[str], ranks: Optional[np.ndarray]) -> List[PairRow]:
    n = sim.shape[0]
    out: List[PairRow] = []
    for i in range(n):
        for j in range(i + 1, n):
            ra = int(ranks[i, j]) if ranks is not None else 0
            rb = int(ranks[j, i]) if ranks is not None else 0
            out.append(PairRow(ids[i], ids[j], float(sim[i, j]), ra, rb))
    return out


def build_pairs_redundant(
    sim: np.ndarray,
    ids: List[str],
    threshold: float,
    top_k: Optional[int],
    ranks: Optional[np.ndarray],
) -> List[PairRow]:
    n = sim.shape[0]
    out: List[PairRow] = []
    for i in range(n):
        for j in range(i + 1, n):
            s = float(sim[i, j])
            if s < threshold:
                continue

            if top_k is None:
                # Without top_k: keep ALL pairs above the threshold
                out.append(PairRow(ids[i], ids[j], s, 0, 0))
            else:
                # With top_k: additionally require membership in i's or j's top-k
                ra = int(ranks[i, j]) if ranks is not None else 0
                rb = int(ranks[j, i]) if ranks is not None else 0
                if ra == 0 and rb == 0:
                    continue
                out.append(PairRow(ids[i], ids[j], s, ra, rb))
    return out


# -----------------------------
# Connectivity-based clustering (Union-Find)
# -----------------------------
class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            self.parent[rx] = ry
        elif self.rank[rx] > self.rank[ry]:
            self.parent[ry] = rx
        else:
            self.parent[ry] = rx
            self.rank[rx] += 1


def clusters_from_pairs(n: int, pairs: List[PairRow], id_to_idx: Dict[str, int]) -> List[List[int]]:
    uf = UnionFind(n)
    for p in pairs:
        uf.union(id_to_idx[p.id_a], id_to_idx[p.id_b])

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        root = uf.find(i)
        groups.setdefault(root, []).append(i)

    clusters = sorted(groups.values(), key=lambda g: (-len(g), g[0]))
    return clusters


def representative_by_mean_similarity(sim: np.ndarray, cluster: List[int]) -> int:
    if len(cluster) == 1:
        return cluster[0]
    sub = sim[np.ix_(cluster, cluster)]
    mean_scores = (sub.sum(axis=1) - np.diag(sub)) / (len(cluster) - 1)
    return cluster[int(np.argmax(mean_scores))]


# -----------------------------
# Per-requirement metrics (for SPSS)
# -----------------------------
def compute_req_metrics(
    sim: np.ndarray,
    ids: List[str],
    threshold: float,
    top_k: Optional[int],
    pairs_redundant: List[PairRow],
) -> pd.DataFrame:
    """
    mean_sim(i): mean similarity to all other requirements (diagonal excluded)
    degree_t(i): consistent with the redundancy definition used:
      - si top_k is None: score >= threshold (todos los pares)
      - si top_k está activo: usa exactamente pairs_redundant (threshold + filtro top-k)
    """
    n = len(ids)
    id_to_idx = {rid: i for i, rid in enumerate(ids)}

    # mean_sim from complete matrix (independent of top_k)
    if n <= 1:
        mean_sim = np.zeros(n, dtype=float)
    else:
        row_sums = sim.sum(axis=1) - np.diag(sim)
        mean_sim = row_sums / (n - 1)

    # degree
    degree = np.zeros(n, dtype=int)

    if top_k is None:
        # Redundancy defined solely by threshold (full matrix)
        mask = (sim >= threshold) & (~np.eye(n, dtype=bool))
        degree = mask.sum(axis=1).astype(int)
    else:
        # Redundancy defined by the actually selected pairs (pairs_redundant)
        for p in pairs_redundant:
            ia = id_to_idx[p.id_a]
            ib = id_to_idx[p.id_b]
            degree[ia] += 1
            degree[ib] += 1

    df = pd.DataFrame({
        "req_id": ids,
        "mean_sim": mean_sim,
        "degree_t": degree
    })
    return df


# -----------------------------
# Output writing
# -----------------------------
def write_pairs_csv_excel_friendly(path: Path, pairs: List[PairRow]):
    """
    CSV formatted for Excel (common EU/ES locale settings):
    - separator ';'
    - encoding 'utf-8-sig' (BOM) so Excel detects UTF-8 correctly
    """
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id_a", "id_b", "score", "rank_from_a", "rank_from_b"])
        for p in sorted(pairs, key=lambda x: -x.score):
            w.writerow([p.id_a, p.id_b, f"{p.score:.6f}", p.rank_from_a, p.rank_from_b])


def write_pairs_xlsx(path: Path, pairs: List[PairRow]):
    df = pd.DataFrame(
        [{
            "id_a": p.id_a,
            "id_b": p.id_b,
            "score": round(p.score, 6),
            "rank_from_a": p.rank_from_a,
            "rank_from_b": p.rank_from_b,
        } for p in sorted(pairs, key=lambda x: -x.score)]
    )
    df.to_excel(path, index=False, engine="openpyxl")


def write_clusters_json(path: Path, clusters: List[List[int]], ids: List[str], sim: np.ndarray):
    out = []
    for cid, members in enumerate(clusters, start=1):
        rep = representative_by_mean_similarity(sim, members)
        out.append({
            "cluster_id": cid,
            "size": len(members),
            "representative": ids[rep],
            "members": [ids[i] for i in members],
        })
    with path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def write_summary(
    path: Path,
    params: Dict,
    n: int,
    n_pairs_total: int,
    n_pairs_redundant: int,
    clusters: List[List[int]],
):
    n_redundant = sum(len(c) for c in clusters if len(c) > 1)
    redundancy_rate = (n_redundant / n) if n else 0.0

    summary = {
        "params": params,
        "metrics": {
            "n_requirements": n,
            "n_pairs_total": n_pairs_total,
            "n_pairs_redundant": n_pairs_redundant,
            "n_clusters": len(clusters),
            "redundant_requirements": n_redundant,
            "redundancy_rate": redundancy_rate,
        },
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def write_similarity_matrix_csv_excel_friendly(path: Path, sim: np.ndarray, ids: List[str]):
    df = pd.DataFrame(sim, index=ids, columns=ids)
    df.to_csv(path, encoding="utf-8-sig", sep=";")


def write_similarity_matrix_xlsx(path: Path, sim: np.ndarray, ids: List[str]):
    df = pd.DataFrame(sim, index=ids, columns=ids)
    df.to_excel(path, engine="openpyxl")


def write_req_metrics_csv_excel_friendly(path: Path, df: pd.DataFrame):
    df.to_csv(path, index=False, encoding="utf-8-sig", sep=";")


def write_req_metrics_xlsx(path: Path, df: pd.DataFrame):
    df.to_excel(path, index=False, engine="openpyxl")


# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser(description="pBERT redundancy detection (spaCy + BERT + cosine similarity)")
    ap.add_argument("--input", required=True, help="Path to the requirements JSON catalog")
    ap.add_argument("--lang", choices=["es", "en"], required=True, help="Language for spaCy preprocessing")
    ap.add_argument("--out_dir", default="", help="Output directory (if omitted, a timestamped directory is created)")
    ap.add_argument("--hf_model", default="bert-base-multilingual-cased", help="HuggingFace model name/path (BERT)")
    ap.add_argument("--batch_size", type=int, default=32)
    ap.add_argument("--max_length", type=int, default=256)
    ap.add_argument("--threshold", type=float, default=0.90, help="Redundancy threshold (cosine >= threshold)")
    ap.add_argument("--top_k", type=int, default=None, help="Optional: filter redundant pairs by top-k nearest neighbors")
    ap.add_argument("--device", default="cpu", help="Device: cpu or cuda")
    ap.add_argument("--excel", action="store_true", help="Also export the similarity matrix to XLSX")
    args = ap.parse_args()

    in_path = Path(args.input)
    data = load_catalog(in_path)
    reqs = data["requisitos"]

    catalog_id = data.get("catalog_id", "CATALOG")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.out_dir.strip():
        out_dir = Path(args.out_dir)
    else:
        out_dir = Path("out") / "pbert_redundancy" / f"{catalog_id}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    ids = [r["id"] for r in reqs]
    texts = extract_descriptions(reqs)

    # spaCy preprocess
    nlp = build_spacy(args.lang)
    pre_texts = preprocess_texts(nlp, texts)

    # BERT embeddings
    tokenizer = AutoTokenizer.from_pretrained(args.hf_model)
    model = AutoModel.from_pretrained(args.hf_model)

    emb = encode_bert(
        tokenizer=tokenizer,
        model=model,
        texts=pre_texts,
        batch_size=args.batch_size,
        max_length=args.max_length,
        device=args.device,
    )

    sim = cosine_matrix(emb)

    # Compute ranks only if top_k is enabled
    ranks = compute_ranks_topk(sim, args.top_k) if args.top_k is not None else None

    # Build pairs
    pairs_all = build_pairs_all(sim, ids, ranks)
    pairs_redundant = build_pairs_redundant(sim, ids, args.threshold, args.top_k, ranks)

    # Build clusters from redundant pairs
    id_to_idx = {rid: i for i, rid in enumerate(ids)}
    clusters = clusters_from_pairs(len(ids), pairs_redundant, id_to_idx)

    # Outputs: pairs + clusters
    write_pairs_csv_excel_friendly(out_dir / "pairs_all.csv", pairs_all)
    write_pairs_csv_excel_friendly(out_dir / "pairs_redundant.csv", pairs_redundant)
    write_pairs_xlsx(out_dir / "pairs_all.xlsx", pairs_all)
    write_pairs_xlsx(out_dir / "pairs_redundant.xlsx", pairs_redundant)
    write_clusters_json(out_dir / "clusters.json", clusters, ids, sim)

    # Outputs: similarity matrix
    write_similarity_matrix_csv_excel_friendly(out_dir / "similarity_matrix.csv", sim, ids)
    if args.excel:
        write_similarity_matrix_xlsx(out_dir / "similarity_matrix.xlsx", sim, ids)

    # Outputs: per-requirement metrics (SPSS)
    req_df = compute_req_metrics(
        sim=sim,
        ids=ids,
        threshold=args.threshold,
        top_k=args.top_k,
        pairs_redundant=pairs_redundant,
    )
    # Add context columns (useful for SPSS and traceability)
    req_df.insert(0, "catalog_id", catalog_id)
    req_df.insert(1, "lang_used", args.lang)
    req_df.insert(2, "threshold", args.threshold)
    req_df.insert(3, "top_k", -1 if args.top_k is None else args.top_k)

    write_req_metrics_csv_excel_friendly(out_dir / "req_metrics.csv", req_df)
    write_req_metrics_xlsx(out_dir / "req_metrics.xlsx", req_df)

    # Summary
    n = len(ids)
    n_pairs_total = n * (n - 1) // 2
    params = {
        "input": str(in_path),
        "catalog_id": catalog_id,
        "lang_used": args.lang,
        "hf_model": args.hf_model,
        "batch_size": args.batch_size,
        "max_length": args.max_length,
        "threshold": args.threshold,
        "top_k": args.top_k,
        "device": args.device,
        "out_dir": str(out_dir),
    }
    write_summary(
        out_dir / "summary.json",
        params=params,
        n=n,
        n_pairs_total=n_pairs_total,
        n_pairs_redundant=len(pairs_redundant),
        clusters=clusters,
    )

    print(f"OK. Results saved to: {out_dir}")


if __name__ == "__main__":
    main()