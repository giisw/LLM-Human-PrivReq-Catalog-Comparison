# Empirical Validation of AI-Driven Automated Generation for Privacy Requirements Reuse

This repository contains **the execution scripts** for the empirical validation pipeline used to analyze privacy requirements catalogs across four branches: **Ambiguity**, **Consistency**, **Readability**, and **Redundancy**.

## Repository contents

High-level structure:

- `validation/`  
  Validation workflow split into four branches:
  - `ambiguity/`
  - `consistency/`
  - `readability/`
  - `redundancy/`

Inside each branch:

- `README.md`  
  Branch-specific documentation covering:
  - purpose of each script
  - how to run it (commands)
  - expected inputs/outputs
  - relevant parameters and configuration notes

- `*.py`  
  The scripts implementing the selected methodology for that branch.

- `INSTALL.md`
  Branch-specific setup steps (when required).

- `requirements.txt`  
  Branch-specific Python dependencies (when required).
