"""
Database connection utility.
Reads credentials from environment / .env and returns a SQLAlchemy engine.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()


def get_engine():
    DB_USER = os.getenv("DB_USER", "admin_inibsa")
    DB_PASS = os.getenv("DB_PASSWORD", "inibsa_secret_2024")
    DB_NAME = os.getenv("DB_NAME", "inibsa_smart_signals")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")

    url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)
