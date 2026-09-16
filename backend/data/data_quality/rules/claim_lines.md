---
id: dq_rules_claim_lines
title: Claim Lines Quality Rules
topic: dataset_rules
dataset: claim_lines
---
# Claim line rules

Each line must reference an existing claim and be unique by claim plus line number. Service units
must be positive. Billed, allowed, and paid values are non-negative; allowed cannot exceed billed,
and paid cannot exceed allowed.
