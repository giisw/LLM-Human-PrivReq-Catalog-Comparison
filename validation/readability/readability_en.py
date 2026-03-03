import argparse
import json
import math
import re
from pathlib import Path
from datetime import datetime

import pandas as pd


def count_syllables_en(word: str) -> int:
    """
    Approximate English syllable count using a simple heuristic.

    Notes:
      - Non-alphabetic characters are removed before counting vowel groups.
      - If no letters remain after cleaning (purely numeric tokens such as "1", "1.3", "2024"),
        the token contributes 0 syllables.
    """
    word = (word or "").lower()
    word_clean = re.sub(r"[^a-z]", "", word)
    vowels = "aeiouy"

    if not word_clean:
        return 0

    count = 0
    prev_vowel = False
    for ch in word_clean:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel

    # Remove silent 'e'
    if word_clean.endswith("e") and count > 1:
        count -= 1
    if count == 0:
        count = 1
    return count


def basic_counts(text: str) -> dict:
    """
    Compute basic statistics for a text: words, sentences, characters,
    syllables, polysyllables.
    """
    # Words:
    # - includes letters, digits, hyphens, dots and slashes.
    #   Examples: "AES-256", "1.3", "ISO/IEC-27001"
    token_pattern = r"\b[\w./-]+\b"
    words = re.findall(token_pattern, text or "")

    # Sentences: do not split when the dot is between digits (1.3, 3.0, etc.)
    sentences = re.split(r"(?<=[^0-9])[.!?]+(?![0-9])", text or "")
    sentences = [s for s in sentences if s.strip()]
    if not sentences and (text or "").strip():
        sentences = [text]

    # Characters: only letters and digits (no punctuation)
    chars = sum(len(re.sub(r"[^A-Za-z0-9]", "", w)) for w in words)
    syllables = sum(count_syllables_en(w) for w in words)
    polysyllables = sum(1 for w in words if count_syllables_en(w) >= 3)

    return {
        "words": len(words),
        "sentences": len(sentences),
        "chars": chars,
        "syllables": syllables,
        "polysyllables": polysyllables,
    }


def ari(counts: dict):
    if counts["words"] == 0 or counts["sentences"] == 0:
        return None
    return (
        4.71 * (counts["chars"] / counts["words"])
        + 0.5 * (counts["words"] / counts["sentences"])
        - 21.43
    )


def flesch(counts: dict):
    if counts["words"] == 0 or counts["sentences"] == 0:
        return None
    return (
        206.835
        - 1.015 * (counts["words"] / counts["sentences"])
        - 84.6 * (counts["syllables"] / counts["words"])
    )


def fkgl(counts: dict):
    if counts["words"] == 0 or counts["sentences"] == 0:
        return None
    return (
        0.39 * (counts["words"] / counts["sentences"])
        + 11.8 * (counts["syllables"] / counts["words"])
        - 15.59
    )


def gunning_fog(counts: dict):
    if counts["words"] == 0 or counts["sentences"] == 0:
        return None
    return 0.4 * (
        (counts["words"] / counts["sentences"])
        + 100 * (counts["polysyllables"] / counts["words"])
    )


def coleman_liau(counts: dict):
    if counts["words"] == 0:
        return None
    L = counts["chars"] / counts["words"] * 100  # letters per 100 words
    S = counts["sentences"] / counts["words"] * 100  # sentences per 100 words
    return 0.0588 * L - 0.296 * S - 15.8


def smog(counts: dict):
    """
    Standard SMOG formula. For very short texts the estimate is unreliable;
    in that case we return None.
    """
    if counts["sentences"] == 0 or counts["polysyllables"] == 0:
        return None
    return 1.043 * math.sqrt(counts["polysyllables"] * (30 / counts["sentences"])) + 3.1291


def compute_metrics(text: str, min_words: int = 10) -> dict:
    """
    Compute English readability metrics for a given text.

    Returns counts plus ARI, Flesch, FKGL, Gunning Fog, SMOG, Coleman-Liau.
    For very short texts (words < min_words or 0 sentences) metrics
    are returned as None, but counts are kept.
    """
    text = " ".join((text or "").split())
    if not text:
        return {
            "words": 0,
            "sentences": 0,
            "chars": 0,
            "syllables": 0,
            "polysyllables": 0,
            "flesch": None,
            "fkgl": None,
            "fog": None,
            "smog": None,
            "ari": None,
            "coleman_liau": None,
        }

    counts = basic_counts(text)

    if counts["words"] < min_words or counts["sentences"] == 0:
        return {
            **counts,
            "flesch": None,
            "fkgl": None,
            "fog": None,
            "smog": None,
            "ari": None,
            "coleman_liau": None,
        }

    return {
        **counts,
        "flesch": flesch(counts),
        "fkgl": fkgl(counts),
        "fog": gunning_fog(counts),
        "smog": smog(counts),
        "ari": ari(counts),
        "coleman_liau": coleman_liau(counts),
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
        "flesch",
        "fkgl",
        "fog",
        "smog",
        "ari",
        "coleman_liau",
    ]

    for req in catalog.get("requisitos", []):
        req_id = req.get("id")
        title = req.get("titulo")

        desc = normalize_text(req.get("descripcion", ""))
        desc_metrics = compute_metrics(desc, min_words=min_words)

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
        description="Compute English readability metrics for a requirements catalog."
    )
    parser.add_argument(
        "input_json",
        help="Path to the input catalog JSON (same schema as your catalog JSON; English text expected).",
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

    # One output folder per run: <stem>_readability_en_YYYYMMDD_HHMMSS
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = input_path.parent / f"{input_path.stem}_readability_en_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_json_path = out_dir / "readability_en.json"
    out_xlsx_path = out_dir / "readability_en.xlsx"

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
