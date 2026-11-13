"""Atomic peer snapshots plus an audit log, committed before responses leave the process."""
import json
import sqlite3
from pathlib import Path

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS snapshot(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, kind TEXT, number INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    def load(self):
        row = self.db.execute('SELECT data FROM snapshot WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None
    def save(self, data, kind):
        number = data.get('current', {}).get('state', {}).get('number', -1)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO snapshot VALUES(1,?)', (json.dumps(data, sort_keys=True),))
            self.db.execute('INSERT INTO events(kind,number) VALUES(?,?)', (kind, number))
    def close(self): self.db.close()
