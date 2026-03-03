## Ambiguity

Ambiguity is assessed using the RCM-based ambiguity detection implemented in **NALABSpy**.

First, transform the catalog into the NALABSpy input format:

```
python catalog_to_nalabs_input.py <CATALOG>
```

Next, you can run the analysis with NALABSpy.

```
python NALABS.py -i <TRANSFORMED_CATALOG> --id-header req_id --text-header text -o <OUTPUT_NAME> -A
```

Finally, generate the consolidated report using the reporting script:

```
python nalabs_report.py <NABLABS_OUTPUT>
```

#### Output

The report generation produces the following files (where `<output_stem>` is the chosen output name):

- **<output_stem>\_summary.json**: Structured summary with catalog-level aggregate metrics (total N, counts and percentages by smell, clean rate, any-issue rate, statistics on issues per requirement, `security_related` tag rate, and notes).

- **<output_stem>\_report.xlsx**: Excel version of the summary, including sheets for (i) aggregate metrics, (ii) count/percent table by smell, and (iii) per-requirement details (`id`, `text`, detected smells list, smell flags, `issues_count`, and `security_related`).
