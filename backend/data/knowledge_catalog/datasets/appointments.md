---
id: dataset_appointments
title: Appointments Dataset
node_type: dataset
summary: One row per synthetic scheduled appointment with participant, time, status, and reason.
parent: domain_scheduling
domain: scheduling
---
# Appointments Dataset

## Grain and relationships

`appointments` contains one generated appointment per row. `appointment_external_id` is unique.
Member, provider, and facility foreign keys identify the scheduled participants and location.

## Scheduling attributes

`scheduled_at` is timezone-aware. `status` is scheduled, completed, cancelled, or no-show.
`reason_category` includes preventive, new symptom, follow-up, chronic care, and procedure.
