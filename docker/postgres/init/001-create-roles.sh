#!/usr/bin/env bash
set -Eeuo pipefail

required_variables=(
  POSTGRES_DB
  POSTGRES_USER
  POSTGRES_APP_USER
  POSTGRES_APP_PASSWORD
  POSTGRES_READER_USER
  POSTGRES_READER_PASSWORD
)

for variable_name in "${required_variables[@]}"; do
  if [[ -z "${!variable_name:-}" ]]; then
    echo "Required PostgreSQL bootstrap variable is unset: ${variable_name}" >&2
    exit 1
  fi
done

psql \
  --set=ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --set=database_name="${POSTGRES_DB}" \
  --set=app_user="${POSTGRES_APP_USER}" \
  --set=app_password="${POSTGRES_APP_PASSWORD}" \
  --set=reader_user="${POSTGRES_READER_USER}" \
  --set=reader_password="${POSTGRES_READER_PASSWORD}" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = :'app_user')
\gexec

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'reader_user', :'reader_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = :'reader_user')
\gexec

SELECT format('ALTER ROLE %I PASSWORD %L', :'app_user', :'app_password')
\gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'reader_user', :'reader_password')
\gexec

ALTER DATABASE :"database_name" OWNER TO :"app_user";
ALTER SCHEMA public OWNER TO :"app_user";

GRANT CONNECT ON DATABASE :"database_name" TO :"reader_user";
GRANT USAGE ON SCHEMA public TO :"reader_user";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"reader_user";

ALTER DEFAULT PRIVILEGES FOR ROLE :"app_user" IN SCHEMA public
GRANT SELECT ON TABLES TO :"reader_user";
SQL
