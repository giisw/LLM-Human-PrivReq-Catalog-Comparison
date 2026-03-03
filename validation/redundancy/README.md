## Redundancy

Redundancy is computed using pBERT embeddings (SpaCy-based preprocessing + BERT), measuring pairwise cosine similarity between requirements.

```
python pbert_redundancy.py --input <CATALOG> --lang <en|es> --threshold <THRESHOLD> [--top_k <K>] [--excel]
```

**--top_k** (optional): keeps only the k nearest neighbors per requirement instead of evaluating/reporting all pairs.

**--excel** (optional): additionally exports the similarity matrix and pair lists to Excel format.

#### Output

A timestamped folder is created under `out/pbert_redundancy/`, containing:

- **summary.json**: Execution summary (parameters, aggregated redundancy metrics, total/redundant pair counts, cluster count, and redundancy rate).

- **pairs_all.csv** / **pairs_all.xlsx**: Full list of all requirement pairs (N·(N−1)/2) with cosine similarity; includes `rank_from_a`/`rank_from_b` when using `--top_k`.

- **pairs_redundant.csv** / **pairs_redundant.xlsx**: Subset of pairs classified as redundant according to the chosen threshold (and, if applicable, filtered by `--top_k`).

- **clusters.json**: Redundancy clusters built from `pairs_redundant`, including one representative requirement per cluster.

- **similarity_matrix.csv** / **similarity_matrix.xlsx**: NxN cosine similarity matrix across all requirements (diagonal ≈ 1.0), useful for inspection and analysis.
