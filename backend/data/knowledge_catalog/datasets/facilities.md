---
id: dataset_facilities
title: Facilities Dataset
node_type: dataset
summary: Synthetic hospitals, clinics, urgent care sites, and ambulatory centers.
parent: domain_provider_network
domain: provider_network
---
# Facilities Dataset

## Grain and columns

`facilities` has one generated care location per row. `facility_external_id` is unique. `name`,
`facility_type`, `city`, and two-character `state` describe network geography and setting.

## Relationships

Providers, encounters, and appointments reference the internal `facilities.id` key.
