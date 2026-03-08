"""
Indexer Status Reporter
Usage in indexers:
    from indexer_reporter import IndexerReporter
    
    reporter = IndexerReporter('near_indexer')
    reporter.start()
    try:
        # ... do indexing work ...
        reporter.success(records_processed=100)
    except Exception as e:
        reporter.error(str(e))
"""

import os
import time
import psycopg2
from datetime import datetime

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax')

class IndexerReporter:
    def __init__(self, indexer_name: str):
        self.indexer_name = indexer_name
        self.start_time = None
        self.conn = None
        
    def _get_conn(self):
        if not self.conn or self.conn.closed:
            self.conn = psycopg2.connect(DATABASE_URL)
        return self.conn
    
    def start(self):
        """Mark indexer as running"""
        self.start_time = time.time()
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE indexer_status 
                    SET status = 'running', 
                        last_run_at = NOW(),
                        updated_at = NOW()
                    WHERE indexer_name = %s
                """, (self.indexer_name,))
            conn.commit()
        except Exception as e:
            print(f"Warning: Could not update indexer status: {e}")
    
    def success(self, records_processed: int = 0):
        """Mark indexer as successful"""
        duration = int(time.time() - self.start_time) if self.start_time else 0
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE indexer_status 
                    SET status = 'success',
                        last_success_at = NOW(),
                        records_processed = %s,
                        run_duration_seconds = %s,
                        last_error = NULL,
                        updated_at = NOW()
                    WHERE indexer_name = %s
                """, (records_processed, duration, self.indexer_name))
            conn.commit()
        except Exception as e:
            print(f"Warning: Could not update indexer status: {e}")
        finally:
            if self.conn:
                self.conn.close()
    
    def error(self, error_message: str):
        """Mark indexer as failed"""
        duration = int(time.time() - self.start_time) if self.start_time else 0
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE indexer_status 
                    SET status = 'error',
                        last_error = %s,
                        run_duration_seconds = %s,
                        updated_at = NOW()
                    WHERE indexer_name = %s
                """, (error_message[:1000], duration, self.indexer_name))  # Truncate long errors
            conn.commit()
        except Exception as e:
            print(f"Warning: Could not update indexer status: {e}")
        finally:
            if self.conn:
                self.conn.close()

# Convenience functions for simple scripts
def report_start(indexer_name: str):
    IndexerReporter(indexer_name).start()

def report_success(indexer_name: str, records: int = 0):
    r = IndexerReporter(indexer_name)
    r.start_time = time.time()  # Approximate
    r.success(records)

def report_error(indexer_name: str, error: str):
    r = IndexerReporter(indexer_name)
    r.start_time = time.time()
    r.error(error)
