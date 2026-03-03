#!/usr/bin/env python3
import argparse
import json
import os
import re


def clean_normative_text(text: str) -> str:
    """
    Removes typical noise from normative excerpts extracted from ENS / ISO / GDPR, etc.
    Intended for downstream semantic scoring (e.g., BERTScore / LaBSE) without losing
    legally relevant content.

    Notes:
    - Input JSON structure is preserved (e.g., 'referencias', 'texto_normativo_es', 'texto_normativo_en').
    - Only the normative text fields are cleaned; everything else is left untouched.
    """
    if text is None:
        return ""
    t = str(text)

    # 0) Remove asterisk markers such as "Article 33.**"
    t = re.sub(r'\*{2,}', '', t)

    # 0.5) Remove leading headers such as "Artículo 33.", "Artículo 33.1", "Article 33."
    t = re.sub(
        r'^\s*(Artículo|Art\.?|Article)\s+\d+(\.\d+)?\s*[.:,-]*\s*',
        '',
        t,
        flags=re.IGNORECASE
    )

    # 1) Remove identifiers in brackets like [op.pl.2.1], [mp.if.1], etc.
    t = re.sub(r'\[[^\]]*\]', ' ', t)

    # 2) Remove list dashes at the beginning of a line/sentence
    t = re.sub(r'^[\-\u2013\u2014]\s*', '', t)              # absolute beginning
    t = re.sub(r'[\r\n]+[\-\u2013\u2014]\s*', ' ', t)       # after line breaks

    # 3) Remove parentheses that contain only codes / references without letters
    def _clean_parentheses(match):
        inner = match.group(1)
        # keep if there is any letter
        if re.search(r'[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]', inner):
            return '(' + inner + ')'
        return ' '
    t = re.sub(r'\(([^)]*)\)', _clean_parentheses, t)

    # 4) Remove prefixes like "Refuerzo R1- ..." / "Reinforcement R1 - ..."
    t = re.sub(
        r'^\s*(Refuerzo\s+R\d+\s*[-\u2013\u2014]\s*|Reinforcement\s+R\d+\s*[-\u2013\u2014]\s*)',
        '',
        t,
        flags=re.IGNORECASE
    )

    # 5) Remove bullets like "a)", "b.", "1.", "2." and ordinals "2.º", "- 3.º", etc.
    bullet_pat = r'(?:[A-Za-z0-9][\)\.]|\d+\.\s*[ºª])'
    t = re.sub(r'^\s*' + bullet_pat + r'\s+', ' ', t)
    t = re.sub(r'([:;])\s*' + bullet_pat + r'\s+', r'\1 ', t)
    t = re.sub(r'([\r\n\-\u2022\u2013\u2014])\s*' + bullet_pat + r'\s+', r'\1 ', t)
    t = re.sub(r'([\.!?])\s*' + bullet_pat + r'\s+', r'\1 ', t)

    # 5.1) Internal bullets:
    #     - letters like " a) Text..." or " (a) Text..."
    #     - numbers like " 1. Text..." when they look like headings (not 1.2, etc.)
    t = re.sub(r'\s+[A-Za-z]\)\s+', ' ', t)                       # " a) Text..."
    t = re.sub(r'\s+\(\s*[A-Za-z]\s*\)\s+', ' ', t)            # " (a) Text..."
    t = re.sub(r'\s+\d+\.\s+(?=[A-ZÁÉÍÓÚÜÑ])', ' ', t)            # " 1. Text..."

    # 6) Replace newlines with spaces
    t = re.sub(r'[\r\n]+', ' ', t)

    # 6.5) Remove isolated hyphens in the middle of a sentence
    t = re.sub(r'(\S)\s*[\-\u2013\u2014]\s+(\S)', r'\1 \2', t)
    t = re.sub(r'([:.,])\s*[\-\u2013\u2014]\s*', r'\1 ', t)
    t = re.sub(r'[\-\u2013\u2014]\s*([.,])', r'\1', t)

    # 7) Handle ';'
    t = re.sub(r';\s*$', '.', t)
    t = re.sub(r';\s*(["»”])\s*$', r'.\1', t)
    t = t.replace(';', ',')

    # 7 bis) Handle trailing ':'
    t = re.sub(r':\s*$', '.', t)

    # 8) Normalize whitespace
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'\s+([,\.:\)])', r'\1', t)
    t = re.sub(r'([\(\[]) +', r'\1', t)

    # 9) Fix odd punctuation combinations
    t = re.sub(r',\s*\.', '.', t)
    t = re.sub(r':\s*\.', '.', t)
    t = re.sub(r'\.{2,}', '.', t)

    t = t.strip()

    # 10) Ensure it ends with a terminal punctuation mark
    if t and t[-1] not in '.!?':
        t += '.'

    return t


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean normative text fields (ES/EN) from a traceability JSON file."
    )
    parser.add_argument(
        "--infile",
        type=str,
        required=True,
        help="Path to the raw traceability JSON file."
    )
    parser.add_argument(
        "--outfile",
        type=str,
        required=False,
        help="Output path for the cleaned JSON (defaults to adding _clean.json)."
    )

    args = parser.parse_args()
    infile_path = args.infile

    if args.outfile:
        outfile_path = args.outfile
    else:
        base, _ext = os.path.splitext(infile_path)
        outfile_path = base + "_clean.json"

    # Load input JSON
    with open(infile_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    references = data.get("referencias", [])
    total_refs = 0
    cleaned_es = 0
    cleaned_en = 0

    for ref in references:
        total_refs += 1
        if "texto_normativo_es" in ref:
            ref["texto_normativo_es"] = clean_normative_text(ref["texto_normativo_es"])
            cleaned_es += 1
        if "texto_normativo_en" in ref:
            ref["texto_normativo_en"] = clean_normative_text(ref["texto_normativo_en"])
            cleaned_en += 1

    # Save output JSON
    with open(outfile_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Input file : {infile_path}")
    print(f"Output file: {outfile_path}")
    print(f"Total references: {total_refs}")
    print(f"  - cleaned texto_normativo_es: {cleaned_es}")
    print(f"  - cleaned texto_normativo_en: {cleaned_en}")


if __name__ == "__main__":
    main()
