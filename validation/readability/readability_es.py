import argparse
import json
import math
import re
from pathlib import Path
from datetime import datetime

import pandas as pd


VOWELS_ES = "aeiouáéíóúü"


def count_syllables_es(word: str) -> int:
    """
    Approximate the number of syllables in a Spanish word using a simple heuristic
    based on vowel groups.
    """
    w = (word or "").lower()
    # Keep only Spanish letters
    w = re.sub(r"[^a-záéíóúüñ]", "", w)
    if not w:
        return 0

    count = 0
    prev_vowel = False
    for ch in w:
        is_vowel = ch in VOWELS_ES
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel

    if count == 0:
        count = 1
    return count


def split_sentences(text: str):
    """
    Basic sentence segmentation while trying not to split decimals.
    """
    sentences = re.split(r"(?<=[^0-9])[.!?]+(?![0-9])", text or "")
    sentences = [s for s in sentences if s.strip()]
    if not sentences and (text or "").strip():
        sentences = [text]
    return sentences


def basic_counts_es(text: str) -> dict:
    """
    Compute basic statistics for Spanish text:
      - words
      - sentences
      - alphabetic characters
      - syllables
      - polysyllables (>= 3 syllables)
      - mean and variance of letters per word (for the µ index)
    """
    # Tokenization:
    # - alphanumeric groups with optional internal hyphens/dots (AES-256, 1.3, multi-factor)
    raw_tokens = re.findall(r"\b[\w]+(?:[.-][\w]+)*\b", text or "", flags=re.UNICODE)

    words = []
    letters_per_word = []
    syllables = 0
    polysyllables = 0

    for tok in raw_tokens:
        clean = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", tok)
        if not clean:
            continue
        words.append(clean)
        letters = len(clean)
        letters_per_word.append(letters)

        syl = count_syllables_es(clean)
        syllables += syl
        if syl >= 3:
            polysyllables += 1

    sentences = split_sentences(text or "")

    n_words = len(words)
    if letters_per_word:
        n = len(letters_per_word)
        mean_letters = sum(letters_per_word) / n
        var_letters = sum((l - mean_letters) ** 2 for l in letters_per_word) / n
    else:
        mean_letters = 0.0
        var_letters = 0.0

    return {
        "words": n_words,
        "sentences": len(sentences),
        "chars": sum(letters_per_word),
        "syllables": syllables,
        "polysyllables": polysyllables,
        "mean_letters": mean_letters,
        "var_letters": var_letters,
    }


def ifsz(counts: dict):
    """
    Flesch–Szigriszt index / Szigriszt-Pazos Perspicuity.
    Formula: 206.835 – 62.3 * (syllables/word) – (words/sentence)
    """
    W = counts["words"]
    S = counts["sentences"]
    Sy = counts["syllables"]
    if W == 0 or S == 0:
        return None
    return 206.835 - 62.3 * (Sy / W) - (W / S)


def inflesz(counts: dict):
    """
    INFLESZ scale: numerically the same formula as Flesch–Szigriszt, typically
    interpreted using categorical thresholds. Here we return only the numeric value.
    """
    return ifsz(counts)


def fernandez_huerta(counts: dict):
    """
    Fernández-Huerta index.
    Formula: 206.84 – 60 * (syllables/word) – 1.02 * (words/sentence)
    """
    W = counts["words"]
    S = counts["sentences"]
    Sy = counts["syllables"]
    if W == 0 or S == 0:
        return None
    return 206.84 - 60.0 * (Sy / W) - 1.02 * (W / S)


def gutierrez_polini(counts: dict):
    """
    Gutiérrez de Polini formula (C):
      C = 95.2 − 9.7 * (L/P) − 0.35 * (P/F)
    where L is letters, P is words, and F is sentences.
    """
    W = counts["words"]
    S = counts["sentences"]
    L = counts["chars"]
    if W == 0 or S == 0:
        return None
    return 95.2 - 9.7 * (L / W) - 0.35 * (W / S)


def smog_es(counts: dict):
    """
    SMOG (Simple Measure of Gobbledygook) adapted for Spanish.
    Standard formula:
      1.043 * sqrt(polysyllables * (30 / sentences)) + 3.1291
    Interpreted as "years of schooling required".
    """
    S = counts["sentences"]
    P = counts["polysyllables"]
    if S == 0 or P == 0:
        return None
    return 1.043 * math.sqrt(P * (30.0 / S)) + 3.1291


def mu_index(counts: dict):
    """
    µ readability index (Muñoz & Muñoz).
    Common formula:
      µ = (n / (n-1)) * (x̄ / σ²) * 100
    where n is number of words, x̄ mean letters per word, σ² variance of letters per word.
    """
    n = counts["words"]
    mean_letters = counts["mean_letters"]
    var_letters = counts["var_letters"]
    if n <= 1 or mean_letters <= 0 or var_letters <= 0:
        return None
    return (n / (n - 1.0)) * (mean_letters / var_letters) * 100.0


def compute_metrics_es(text: str, min_words: int = 10) -> dict:
    """
    Compute Spanish readability metrics for a given text.

    Returns basic counts plus:
      - IFSZ / INFLESZ
      - Fernández-Huerta
      - SMOG (adapted)
      - Gutiérrez de Polini
      - µ readability index

    For very short texts (words < min_words or no sentences), metrics are None,
    but counts are still returned.
    """
    text = " ".join((text or "").split())
    if not text:
        return {
            "words": 0,
            "sentences": 0,
            "chars": 0,
            "syllables": 0,
            "polysyllables": 0,
            "mean_letters": 0.0,
            "var_letters": 0.0,
            "ifsz": None,
            "inflesz": None,
            "fernandez_huerta": None,
            "smog": None,
            "gutierrez_polini": None,
            "mu": None,
        }

    counts = basic_counts_es(text)

    if counts["words"] < min_words or counts["sentences"] == 0:
        return {
            **counts,
            "ifsz": None,
            "inflesz": None,
            "fernandez_huerta": None,
            "smog": None,
            "gutierrez_polini": None,
            "mu": None,
        }

    return {
        **counts,
        "ifsz": ifsz(counts),
        "inflesz": inflesz(counts),
        "fernandez_huerta": fernandez_huerta(counts),
        "smog": smog_es(counts),
        "gutierrez_polini": gutierrez_polini(counts),
        "mu": mu_index(counts),
    }


def normalize_text(text: str) -> str:
    return " ".join((text or "").split())


def process_catalog(catalog: dict, min_words: int = 10):
    """
    Process a requirements catalog (JSON) and compute readability ONLY for:
      - descripcion (requirement description)
    """
    out_requirements = []
    rows = []

    metric_keys = [
        "words",
        "sentences",
        "chars",
        "syllables",
        "polysyllables",
        "mean_letters",
        "var_letters",
        "ifsz",
        "inflesz",
        "fernandez_huerta",
        "smog",
        "gutierrez_polini",
        "mu",
    ]

    for req in catalog.get("requisitos", []):
        req_id = req.get("id")
        title = req.get("titulo")

        desc = normalize_text(req.get("descripcion", ""))
        desc_metrics = compute_metrics_es(desc, min_words=min_words)

        # Output JSON (English keys; input schema is preserved when reading)
        out_requirements.append(
            {
                "id": req_id,
                "title": title,
                "readability": {"description": desc_metrics},
            }
        )

        # Row for Excel
        row = {
            "catalog_id": catalog.get("catalog_id"),
            "id": req_id,
            "title": title,
        }
        for key in metric_keys:
            row[key.upper()] = desc_metrics.get(key)

        rows.append(row)

    out_catalog = {
        "catalog_id": catalog.get("catalog_id"),
        "requirements": out_requirements,
    }
    return out_catalog, rows


def main():
    parser = argparse.ArgumentParser(
        description="Compute Spanish readability metrics for a requirements catalog."
    )
    parser.add_argument(
        "input_json",
        help="Path to the input catalog JSON (same schema as your catalog JSON; Spanish text expected).",
    )
    parser.add_argument(
        "--min-words",
        "-m",
        type=int,
        default=10,
        help="Minimum number of words required to compute metrics (default: 10).",
    )

    args = parser.parse_args()

    input_path = Path(args.input_json)
    with input_path.open("r", encoding="utf-8") as f:
        catalog = json.load(f)

    out_catalog, rows = process_catalog(catalog, min_words=args.min_words)

    # One output folder per run: <stem>_readability_es_YYYYMMDD_HHMMSS
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = input_path.parent / f"{input_path.stem}_readability_es_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_json_path = out_dir / "readability_es.json"
    out_xlsx_path = out_dir / "readability_es.xlsx"

    # JSON
    with out_json_path.open("w", encoding="utf-8") as f:
        json.dump(out_catalog, f, ensure_ascii=False, indent=2)

    # Excel
    df = pd.DataFrame(rows)
    df.to_excel(out_xlsx_path, index=False)

    print(f"Readability JSON saved to: {out_json_path}")
    print(f"Readability Excel saved to: {out_xlsx_path}")


if __name__ == "__main__":
    main()
