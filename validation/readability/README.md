## Readability

Readability is assessed using a set of language-dependent metrics.

For requirements in **English**:

```
python readability_en.py <CATALOG_EN_JSON>
```

#### Output (English)

A timestamped folder is created: `<input_stem>_readability_en_YYYYMMDD_HHMMSS/`, containing:

- **readability_en.json**: JSON output containing the catalog identifier and one entry per requirement with its identifier, title, and description-level English readability metrics.

- **readability_en.xlsx**: Excel table with one row per requirement and columns for counters and metrics (words, sentences, characters, syllables, polysyllables, Flesch, FKGL, FOG, SMOG, ARI, Coleman–Liau).

For requirements in **Spanish**:

```
python readability_es.py <CATALOG_ES_JSON>
```

#### Output (Spanish)

A timestamped folder is created: `<input_stem>_readability_es_YYYYMMDD_HHMMSS/`, containing:

- **readability_es.json**: JSON output containing the catalog identifier and one entry per requirement with its identifier, title, and description-level Spanish readability metrics.

- **readability_es.xlsx**: Excel table with one row per requirement and columns for counters and metrics (words, sentences, characters, syllables, polysyllables, mean_letters, var_letters, IFSZ/INFLESZ, Fernández-Huerta, SMOG (ES), Gutiérrez Polini, Mu).
