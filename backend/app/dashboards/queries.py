"""Fixed aggregate-only SQL used by the deterministic dashboard repository."""

DATA_AVAILABILITY_SQL = """
/* dashboard:data_availability */
SELECT
    CAST(MIN(event_date) AS date) AS available_start_date,
    CAST(MAX(event_date) AS date) AS data_as_of
FROM (
    SELECT service_date AS event_date FROM claims
    UNION ALL
    SELECT encounter_date AS event_date FROM encounters
    UNION ALL
    SELECT CAST(scheduled_at AS date) AS event_date FROM appointments
) AS available_events
"""

OVERVIEW_SQL = """
/* dashboard:overview */
SELECT
    (SELECT COUNT(*) FROM claims
     WHERE service_date BETWEEN :start_date AND :end_date) AS total_claims,
    (SELECT COALESCE(SUM(paid_amount), 0) FROM claims
     WHERE service_date BETWEEN :start_date AND :end_date) AS total_paid_amount,
    (SELECT COALESCE(SUM(allowed_amount), 0) FROM claims
     WHERE service_date BETWEEN :start_date AND :end_date) AS total_allowed_amount,
    (SELECT COALESCE(AVG(paid_amount), 0) FROM claims
     WHERE service_date BETWEEN :start_date AND :end_date) AS average_paid_amount,
    (SELECT COUNT(DISTINCT member_id) FROM claims
     WHERE service_date BETWEEN :start_date AND :end_date) AS unique_members,
    (SELECT COUNT(*) FROM encounters
     WHERE encounter_date BETWEEN :start_date AND :end_date) AS total_encounters,
    (SELECT COUNT(*) FROM appointments
     WHERE scheduled_at >= CAST(:start_date AS date)
       AND scheduled_at < CAST(:end_date AS date) + INTERVAL '1 day') AS total_appointments,
    (SELECT COUNT(DISTINCT provider_id) FROM (
        SELECT provider_id FROM claims WHERE service_date BETWEEN :start_date AND :end_date
        UNION
        SELECT provider_id FROM encounters WHERE encounter_date BETWEEN :start_date AND :end_date
        UNION
        SELECT provider_id FROM appointments
        WHERE scheduled_at >= CAST(:start_date AS date)
          AND scheduled_at < CAST(:end_date AS date) + INTERVAL '1 day'
    ) AS represented_providers) AS provider_count,
    (SELECT COUNT(DISTINCT facility_id) FROM (
        SELECT facility_id FROM encounters WHERE encounter_date BETWEEN :start_date AND :end_date
        UNION
        SELECT facility_id FROM appointments
        WHERE scheduled_at >= CAST(:start_date AS date)
          AND scheduled_at < CAST(:end_date AS date) + INTERVAL '1 day'
    ) AS represented_facilities) AS facility_count
"""

CLAIMS_TREND_SQL = """
/* dashboard:claims_trend */
SELECT
    CAST(date_trunc('month', service_date) AS date) AS period,
    COUNT(*) AS claim_count,
    COALESCE(SUM(paid_amount), 0) AS paid_amount,
    COALESCE(SUM(allowed_amount), 0) AS allowed_amount
FROM claims
WHERE service_date BETWEEN :start_date AND :end_date
GROUP BY 1
ORDER BY 1
"""

CLAIM_STATUS_SQL = """
/* dashboard:claim_status */
SELECT claim_status AS category, COUNT(*) AS count
FROM claims
WHERE service_date BETWEEN :start_date AND :end_date
GROUP BY claim_status
ORDER BY claim_status
"""

CLAIM_SPECIALTY_SQL = """
/* dashboard:claim_specialty */
SELECT
    p.specialty AS category,
    COUNT(*) AS count,
    COALESCE(SUM(c.paid_amount), 0) AS amount,
    COALESCE(AVG(c.paid_amount), 0) AS average_amount
FROM claims AS c
JOIN providers AS p ON p.id = c.provider_id
WHERE c.service_date BETWEEN :start_date AND :end_date
GROUP BY p.specialty
ORDER BY count DESC, p.specialty
LIMIT :top_n
"""

CLAIM_FACILITY_SQL = """
/* dashboard:claim_facility */
SELECT
    f.facility_type AS category,
    COUNT(*) AS count,
    COALESCE(SUM(c.paid_amount), 0) AS amount,
    COALESCE(AVG(c.paid_amount), 0) AS average_amount
FROM claims AS c
JOIN encounters AS e ON e.id = c.encounter_id
JOIN facilities AS f ON f.id = e.facility_id
WHERE c.service_date BETWEEN :start_date AND :end_date
GROUP BY f.facility_type
ORDER BY count DESC, f.facility_type
LIMIT :top_n
"""

ENCOUNTERS_TREND_SQL = """
/* dashboard:encounters_trend */
SELECT CAST(date_trunc('month', encounter_date) AS date) AS period, COUNT(*) AS value
FROM encounters
WHERE encounter_date BETWEEN :start_date AND :end_date
GROUP BY 1
ORDER BY 1
"""

APPOINTMENTS_TREND_SQL = """
/* dashboard:appointments_trend */
SELECT CAST(date_trunc('month', scheduled_at) AS date) AS period, COUNT(*) AS value
FROM appointments
WHERE scheduled_at >= CAST(:start_date AS date)
  AND scheduled_at < CAST(:end_date AS date) + INTERVAL '1 day'
GROUP BY 1
ORDER BY 1
"""

APPOINTMENT_STATUS_SQL = """
/* dashboard:appointment_status */
SELECT status AS category, COUNT(*) AS count
FROM appointments
WHERE scheduled_at >= CAST(:start_date AS date)
  AND scheduled_at < CAST(:end_date AS date) + INTERVAL '1 day'
GROUP BY status
ORDER BY status
"""

ENCOUNTER_TYPE_SQL = """
/* dashboard:encounter_type */
SELECT encounter_type AS category, COUNT(*) AS count
FROM encounters
WHERE encounter_date BETWEEN :start_date AND :end_date
GROUP BY encounter_type
ORDER BY encounter_type
"""

APPOINTMENT_SPECIALTY_SQL = """
/* dashboard:appointment_specialty */
SELECT p.specialty AS category, COUNT(*) AS count
FROM appointments AS a
JOIN providers AS p ON p.id = a.provider_id
WHERE a.scheduled_at >= CAST(:start_date AS date)
  AND a.scheduled_at < CAST(:end_date AS date) + INTERVAL '1 day'
GROUP BY p.specialty
ORDER BY count DESC, p.specialty
LIMIT :top_n
"""
