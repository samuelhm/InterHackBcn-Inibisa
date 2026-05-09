#!/bin/bash
set -e

echo "=== Esperando a que PostgreSQL esté listo..."
until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
    echo "Esperando PostgreSQL..."
    sleep 2
done

echo "PostgreSQL listo. Ejecutando script de ingesta..."
python3 /scripts/ingest_all.py
