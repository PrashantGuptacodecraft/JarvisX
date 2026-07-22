import sqlite3
import datetime

conn = sqlite3.connect(':memory:')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS kg_triples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        predicate TEXT NOT NULL,
        object TEXT NOT NULL,
        weight REAL NOT NULL DEFAULT 1.0,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        UNIQUE(subject, predicate, object)
    );
''')
conn.commit()

def upsert_triple(subject: str, predicate: str, obj: str, weight: float = 1.0, observed_at: str = None) -> int:
    now = observed_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
    # Insert or update
    res = conn.execute(
        """
        INSERT INTO kg_triples (subject, predicate, object, weight, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(subject, predicate, object) DO UPDATE SET
            weight = CASE
                WHEN excluded.last_seen >= kg_triples.last_seen THEN excluded.weight
                ELSE kg_triples.weight
            END,
            first_seen = MIN(kg_triples.first_seen, excluded.first_seen),
            last_seen = MAX(kg_triples.last_seen, excluded.last_seen)
        RETURNING id
        """,
        (subject, predicate, obj, float(weight), now, now)
    ).fetchone()
    conn.commit()
    return res[0]

id1 = upsert_triple('A', 'B', 'C', 1.0, '2023-01-02T10:00:00Z')
print('ID1:', id1)
id2 = upsert_triple('A', 'B', 'C', 2.0, '2023-01-01T10:00:00Z') # Older observation!
print('ID2:', id2)

cursor.execute("SELECT * FROM kg_triples")
print("After older:", dict(cursor.fetchone()))

id3 = upsert_triple('A', 'B', 'C', 3.0, '2023-01-03T10:00:00Z') # Newer observation!
print('ID3:', id3)

cursor.execute("SELECT * FROM kg_triples")
print("After newer:", dict(cursor.fetchone()))
