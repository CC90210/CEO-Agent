import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.db_turso import get_db

def main():
    db = get_db()
    
    statements = [
        "EXPLAIN QUERY PLAN SELECT * FROM lead_interactions WHERE channel = 'email' AND direction = 'outbound' AND type = 'email_queued' AND agent_source IN ('dashboard_drawer', 'dashboard_bulk_email') ORDER BY created_at ASC LIMIT 10"
    ]
    
    for stmt in statements:
        print(f"\nExecuting: {stmt}")
        try:
            results = db.query(stmt, allow_unscoped=True, reason="query plan check")
            for row in results:
                print(row)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
