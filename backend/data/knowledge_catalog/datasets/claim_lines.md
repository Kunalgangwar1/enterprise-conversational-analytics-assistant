---
id: dataset_claim_lines
title: Claim Lines Dataset
node_type: dataset
summary: Synthetic procedure-level claim details with units, diagnosis, and line financial amounts.
parent: domain_claims
domain: claims
---
# Claim Lines Dataset

## Grain and key

`claim_lines` contains one service line per claim and `line_number`. `claim_id` joins to
`claims.id`; deleting a claim removes its lines.

## Measures and codes

Each line records `procedure_code`, `diagnosis_code`, positive `service_units`, `billed_amount`,
`allowed_amount`, and `paid_amount`. Allowed amount cannot exceed billed amount, and paid amount
cannot exceed allowed amount.
