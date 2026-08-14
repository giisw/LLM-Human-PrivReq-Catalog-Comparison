## Redundancy

Redundancy is computed using pBERT embeddings (spaCy-based preprocessing + BERT), measuring pairwise cosine similarity between requirements.

```
python pbert_redundancy.py --input <CATALOG> --lang <en|es> --threshold <THRESHOLD> [--top_k <K>] [--excel]
```

**--top_k** (optional): after thresholding, retains a redundant pair only if either requirement appears among the other requirement's k nearest neighbors. All pairwise similarities are still computed and exported in `pairs_all`.

**--excel** (optional): additionally exports the similarity matrix in Excel format (`similarity_matrix.xlsx`). The pair-list and per-requirement XLSX files are generated regardless of this option.

#### Output

A timestamped folder is created under `out/pbert_redundancy/`, containing:

- **summary.json**: Execution summary (parameters, aggregated redundancy metrics, total/redundant pair counts, cluster count, and redundancy rate).

- **pairs_all.csv** / **pairs_all.xlsx**: Full list of all requirement pairs (N·(N−1)/2) with cosine similarity; includes `rank_from_a`/`rank_from_b` when using `--top_k`.

- **pairs_redundant.csv** / **pairs_redundant.xlsx**: Subset of pairs classified as redundant according to the chosen threshold (and, if applicable, filtered by `--top_k`).

- **clusters.json**: Redundancy clusters built from `pairs_redundant`, including one representative requirement per cluster.

- **similarity_matrix.csv** / **similarity_matrix.xlsx** (with `--excel`): NxN cosine similarity matrix across all requirements (diagonal ≈ 1.0), useful for inspection and analysis.

- **req_metrics.csv** / **req_metrics.xlsx**: Per-requirement redundancy metrics containing `catalog_id`, `lang_used`, `threshold`, `top_k`, `req_id`, `mean_sim`, and `degree_t`.