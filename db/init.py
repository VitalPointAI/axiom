"""Database initialization and connection management."""

import sqlite3
import os
from pathlib import Path

# Get the project root (where config.py is)
PROJECT_ROOT = Path(__file__).parent.parent

# Import config
import sys
sys.path.insert(0, str(PROJECT_ROOT))
from config import DATABASE_PATH


def get_db_path():
    """Get absolute path to database file."""
    if os.path.isabs(DATABASE_PATH):
        return DATABASE_PATH
    return str(PROJECT_ROOT / DATABASE_PATH)


def get_connection():
    """Get a database connection."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    return conn


def init_db():
    """Initialize database with schema."""
    db_path = get_db_path()
    schema_path = PROJECT_ROOT / "db" / "schema.sql"
    
    print(f"Initializing database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    
    with open(schema_path, 'r') as f:
        schema = f.read()
    
    conn.executescript(schema)
    conn.commit()
    conn.close()
    
    print("Database initialized successfully")
    return db_path


def get_tables():
    """List all tables in the database."""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables


if __name__ == "__main__":
    init_db()
    print(f"Tables: {get_tables()}")
