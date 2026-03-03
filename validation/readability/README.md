## Readability

Readability is assessed using a set of language-dependent metrics.

For requirements in **English**:

```
python readability_en.py <CATALOG_EN_JSON>
```

#### Output (English)

A timestamped folder is created: `results_YYYYMMDD_HHMMSS/`, containing:

- **readability_en.json**: Original JSON catalog enriched with readability metrics per requirement and aggregated by scope.

- **readability_en.xlsx**: Excel table with one row per requirement and columns for counters and metrics (words, sentences, characters, syllables, polysyllables, Flesch, FKGL, FOG, SMOG, ARI, Coleman–Liau).

For requirements in **Spanish**:

```
python readability_es.py <CATALOG_ES_JSON>
```

#### Output (Spanish)

A timestamped folder is created: `results_YYYYMMDD_HHMMSS/`, containing:

- **readability_es.json**: Original JSON catalog enriched with Spanish readability metrics per requirement and aggregated by scope.

- **readability_es.xlsx**: Excel table with one row per requirement and columns for counters and metrics (words, sentences, characters, syllables, polysyllables, mean_letters, var_letters, IFSZ/INFLESZ, Fernández-Huerta, SMOG (ES), Gutiérrez Polini, Mu).
