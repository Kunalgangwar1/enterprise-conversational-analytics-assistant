---
id: dataset_providers
title: Providers Dataset
node_type: dataset
summary: One row per synthetic clinician, including specialty and primary facility association.
parent: domain_provider_network
domain: provider_network
---
# Providers Dataset

## Grain and relationships

`providers` contains one generated clinician per row. `provider_external_id` and `synthetic_npi`
are unique synthetic identifiers. `facility_id` joins to `facilities.id`.

## Analytics

Use `specialty` for network composition. Supported generated categories include Primary Care,
Cardiology, Orthopedics, Dermatology, Neurology, and Endocrinology.
