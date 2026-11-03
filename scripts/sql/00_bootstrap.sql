-- Bootstrap DDL executed by scripts/bootstrap_databricks.sh (idempotent).
CREATE CATALOG IF NOT EXISTS datathon;

CREATE SCHEMA IF NOT EXISTS datathon.emerson;

CREATE VOLUME IF NOT EXISTS datathon.emerson.raw;

-- Expect 33 files once uploaded.
LIST '/Volumes/datathon/emerson/raw/pdfs/';
