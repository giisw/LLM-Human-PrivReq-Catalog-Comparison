## Consistency

### BERTScore

**BERTScore** compares each requirement against its associated regulatory text(s) and selects the **best-matching reference** per requirement (highest F1).

```
python compare_bertscore.py --reqfile <PATH_REQUIREMENTS> --reffile <PATH_REFERENCES> [--lang <auto|es|en>] [--rescale]
```

#### Output

A timestamped folder is created: `results_YYYYMMDD_HHMMSS/`, containing:

- **bertscore_results.xlsx**: Excel table with one row per requirement (`id`, `title`, `precision`, `recall`, `f1`, `best_legal_reference`, `best_normative_excerpt`).

- **bertscore_results.json**: Same table as JSON (list of records), using the same field names as the Excel output.

- **f1_histogram.png**: Histogram of the F1 score distribution across the evaluated requirements.

- **metrics_lines.png**: Line plot of F1, Precision, and Recall by requirement index (trend comparison).

### LABSE

**LaBSE** compares requirements and regulatory texts using multilingual sentence embeddings, so similarity scoring works even when requirement and reference are in different languages.

```
python compare_labse.py --reqfile <PATH_REQUIREMENTS> --reffile <PATH_REFERENCES> [--model <MODEL_NAME_OR_PATH>]
```

#### Output

A timestamped folder is created: `results_YYYYMMDD_HHMMSS/`, containing:

- **labse_results.xlsx**: Excel table with one row per requirement (`id`, `title`, `text`, `num_references`, `best_similarity`, `best_legal_reference`, `best_normative_excerpt`).

- **labse_results.json**: Same table as JSON (list of records), using the same field names as the Excel output.

- **labse_similarity_lines.png**: Line plot of the best LaBSE cosine similarity per requirement (Y-axis in [-1, 1]).

## Traceability

To remove elements that may negatively affect semantic consistency and do not add value for similarity-based evaluation, use the following script:

```
python clean_traceability.py --infile <PATH_TRACEABILITY_JSON> [--outfile <PATH_TRACEABILITY_CLEAN_JSON>]
```

#### Output

The output is the cleaned traceability document (JSON).
