"""Apply idempotent schema to explicitly configured DB. Does not start a runtime."""
import os
from aria.persistence.repositories import PostgresEventStore
if __name__=='__main__':
    PostgresEventStore(os.environ['ARIA_HISTORY_DSN']).migrate()
    print('History and local engineering spatial schema applied')
