# Comparing LLM-Assisted and Human-Authored Privacy Requirements Catalogs: An Exploratory Bilingual Case Study

This repository contains **the execution scripts** for the evaluation pipeline used to analyze the RequiCreator-generated and PDP2019 reference catalogs across four analysis branches: **Ambiguity**, **Consistency**, **Readability**, and **Redundancy**.

## Repository contents

High-level structure:

- `validation/`  
  Evaluation workflow split into four analysis branches:
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
  The scripts implementing the analysis methodology selected for that branch.

- `INSTALL.md`
  Branch-specific setup steps (when required).

- `requirements.txt`  
  Branch-specific Python dependencies (when required).

## Third-party software

The `validation/ambiguity/NALABSpy/` directory contains code derived from the NALABS/NALABSpy project. The upstream software is distributed under the MIT License; the corresponding license notice is preserved in `validation/ambiguity/NALABSpy/LICENSE`.
