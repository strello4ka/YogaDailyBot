from contextlib import contextmanager
import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS receipt_jobs (
    payment_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    paid_at TEXT NOT NULL,
    service_name TEXT NOT NULL,
    customer_email TEXT,
    state TEXT NOT NULL CHECK(state IN
      ('ready', 'creating', 'unknown', 'registered', 'email_pending', 'emailed', 'manual_review')),
    receipt_uuid TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS service_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class StateStore:
    def __init__(self, path):
        self.path = path
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def add_payment(self, payment):
        metadata = payment['metadata']
        with self.connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO receipt_jobs
                   (payment_id, order_id, amount, paid_at, service_name, customer_email, state)
                   VALUES (?, ?, ?, ?, ?, ?, 'ready')""",
                (payment['id'], metadata['order_id'], payment['amount']['value'],
                 payment['captured_at'], metadata['service_name'], metadata['customer_email']),
            )

    def jobs(self, *states):
        placeholders = ','.join('?' for _ in states)
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                f'SELECT * FROM receipt_jobs WHERE state IN ({placeholders}) ORDER BY paid_at', states)]

    def job(self, payment_id):
        with self.connect() as connection:
            row = connection.execute(
                'SELECT * FROM receipt_jobs WHERE payment_id = ?', (payment_id,)).fetchone()
            return dict(row) if row else None

    def counts(self):
        with self.connect() as connection:
            return {row['state']: row['total'] for row in connection.execute(
                'SELECT state, COUNT(*) AS total FROM receipt_jobs GROUP BY state')}

    def recover_interrupted_writes(self):
        """A crash in `creating` may happen after the POST reached My Nalog.

        Such jobs must be reconciled by reading receipts, never posted again.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                """UPDATE receipt_jobs
                   SET state = 'unknown',
                       last_error = 'Service stopped during My Nalog write; reconciliation required',
                       updated_at = CURRENT_TIMESTAMP
                   WHERE state = 'creating'""")
            return cursor.rowcount

    def transition(self, payment_id, expected, state, **fields):
        assignments = ['state = ?', 'updated_at = CURRENT_TIMESTAMP']
        values = [state]
        for name in ('receipt_uuid', 'last_error', 'customer_email'):
            if name in fields:
                assignments.append(f'{name} = ?')
                values.append(fields[name])
        values.extend([payment_id, expected])
        with self.connect() as connection:
            cursor = connection.execute(
                f"UPDATE receipt_jobs SET {', '.join(assignments)} WHERE payment_id = ? AND state = ?",
                values,
            )
            return cursor.rowcount == 1

    def get_value(self, key):
        with self.connect() as connection:
            row = connection.execute('SELECT value FROM service_state WHERE key = ?', (key,)).fetchone()
            return row['value'] if row else None

    def set_value(self, key, value):
        with self.connect() as connection:
            connection.execute(
                'INSERT INTO service_state(key, value) VALUES (?, ?) '
                'ON CONFLICT(key) DO UPDATE SET value = excluded.value', (key, value))
