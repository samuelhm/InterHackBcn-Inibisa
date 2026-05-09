FROM postgres:latest

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip && \
    pip3 install --break-system-packages pandas openpyxl sqlalchemy psycopg2-binary && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/lib/postgresql && chown -R postgres:postgres /var/lib/postgresql

COPY data/Datasets.xlsx /data/Datasets.xlsx
COPY database/ingest_all.py /scripts/ingest_all.py
COPY database/01-run-ingest.sh /docker-entrypoint-initdb.d/01-run-ingest.sh

RUN chmod +x /docker-entrypoint-initdb.d/01-run-ingest.sh
