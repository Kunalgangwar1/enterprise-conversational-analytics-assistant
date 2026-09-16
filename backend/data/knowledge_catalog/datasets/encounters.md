---
id: dataset_encounters
title: Encounters Dataset
node_type: dataset
summary: One row per synthetic care interaction, with date, type, diagnosis, status, and participants.
parent: domain_clinical_encounters
domain: clinical_encounters
---
# Encounters Dataset

## Grain and relationships

`encounters` has one generated interaction per row. It joins members, providers, and facilities
through `member_id`, `provider_id`, and `facility_id`. `encounter_external_id` is unique.

## Classifications

`encounter_type` includes outpatient, inpatient, emergency, and telehealth. `status` includes
completed, cancelled, and in-progress interactions. `primary_diagnosis_code` is a synthetic code.
