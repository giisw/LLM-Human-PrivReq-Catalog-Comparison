## Ambiguity

Ambiguity is assessed using **NALABSpy**, following the dictionary-based requirement-smell approach used by NALABS/RCM.

First, transform the catalog into the NALABSpy input format:

```
python catalog_to_nalabs_input.py <CATALOG> <TRANSFORMED_CATALOG>
```

Next, you can run the analysis with NALABSpy.

```
python NALABSpy/NALABS.py -i <TRANSFORMED_CATALOG> --id-header req_id --text-header text -o <NALABS_OUTPUT_JSON> -A
```

Finally, generate the consolidated report using the reporting script:

```
python nalabs_report.py <NALABS_OUTPUT_JSON> --input-json <TRANSFORMED_CATALOG>
```

#### Output

By default, the report is generated under `nalabs_runs/<output_stem>_YYYYMMDD_HHMMSS/`, containing the following files:

- **<output_stem>\_summary.json**: Structured summary with catalog-level aggregate metrics (total N, counts and percentages by smell, clean rate, any-issue rate, statistics on issues per requirement, `security_related` tag rate, and notes).

- **<output_stem>\_report.xlsx**: Excel version of the summary, including sheets for (i) aggregate metrics, (ii) count/percent table by smell, and (iii) per-requirement details (`id`, `text`, detected smells list, smell flags, `issues_count`, and `security_related`).
