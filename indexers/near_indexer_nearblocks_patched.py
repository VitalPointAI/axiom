# Replace the main block with this:
"""
if __name__ == '__main__':
    import argparse
    from indexer_reporter import IndexerReporter

    parser = argparse.ArgumentParser()
    parser.add_argument('--user', type=int, help='Sync only this user ID')
    args = parser.parse_args()

    reporter = IndexerReporter('near_indexer')
    reporter.start()

    try:
        sync_all(args.user)
        # Count total records
        conn = psycopg2.connect(PG_CONN)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transactions")
        total = cur.fetchone()[0]
        conn.close()
        reporter.success(records_processed=total)
    except Exception as e:
        reporter.error(str(e))
        raise
"""
