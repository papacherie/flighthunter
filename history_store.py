"""Private FlightHunter flight-result snapshots, SQLite for dev or PostgreSQL in production.

Never store API keys, private access codes, cookie credentials or booking tokens.
A Render Free web service has an EPHEMERAL filesystem. Set DATABASE_URL for
storage that survives web-service redeployments (subject to database plan).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

LOCK = threading.RLock()
ROOT = Path(__file__).parent
LIMIT = 80
ID_LENGTH = 24


def using_postgres() -> bool:
    return bool(os.getenv('DATABASE_URL', '').strip())


def storage_type() -> str:
    if using_postgres():
        return 'postgres'
    if os.getenv('FLIGHTHUNTER_HISTORY_SQLITE', '').strip():
        return 'sqlite'
    return 'temporary'  # This file is lost on Render Free service restarts/deploys.


def _path() -> str:
    return os.getenv('FLIGHTHUNTER_HISTORY_SQLITE', '').strip() or '/tmp/flighthunter-history.sqlite3'


@contextmanager
def connect():
    if using_postgres():
        import psycopg2
        conn = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=8)
        try:
            yield conn, '%s'
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        path = Path(_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=8)
        try:
            yield conn, '?'
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _initialize(conn):
    conn.cursor().execute('''CREATE TABLE IF NOT EXISTS flight_search_history (
        id VARCHAR(24) PRIMARY KEY,
        saved_at VARCHAR(32) NOT NULL,
        origin VARCHAR(85) NOT NULL,
        destination VARCHAR(85) NOT NULL,
        departure VARCHAR(10) NOT NULL,
        return_date VARCHAR(10) NOT NULL,
        offers_count INTEGER NOT NULL,
        min_price DOUBLE PRECISION,
        snapshot TEXT NOT NULL
    )''')
    conn.cursor().execute('CREATE INDEX IF NOT EXISTS idx_fh_history_saved_at ON flight_search_history(saved_at DESC)')


def _safe_snapshot(result: dict) -> dict:
    """Reduce stored data to user-visible search data; no internal booking tokens."""
    criteria = result['criteria']
    return {
        'criteria': {k: criteria[k] for k in ('origin','destination','departure','return',
                      'adults','children_ages','stops')},
        'offers': [
            {k: v for k, v in offer.items() if k not in ('booking_token','departure_token')}
            for offer in (result.get('offers') or [])[:12]
        ],
        'links': result.get('links') or [],
        'checked_at': result['checked_at'],
        'status': result.get('status', ''),
        'warning': result.get('warning', ''),
        'message': result.get('message', '')
    }


def save(result: dict) -> str:
    payload = _safe_snapshot(result)
    serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    if len(serialized.encode('utf8')) > 350_000:
        raise ValueError('Résultats trop volumineux à conserver.')
    saved_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    criteria = payload['criteria']
    prices = [float(o['price']) for o in payload['offers'] if isinstance(o.get('price'), (float,int)) and float(o['price']) > 0]
    row_id = secrets.token_hex(ID_LENGTH // 2)
    with LOCK, connect() as (conn, placeholder):
        _initialize(conn)
        values = (row_id, saved_at, criteria['origin'], criteria['destination'],
                  criteria['departure'], criteria['return'], len(payload['offers']),
                  min(prices) if prices else None, serialized)
        p = ','.join([placeholder]*len(values))
        conn.cursor().execute('INSERT INTO flight_search_history VALUES ('+p+')', values)
        # Keep recent 80 snapshots, bounded quota on free database.
        conn.cursor().execute('''DELETE FROM flight_search_history WHERE id NOT IN (
            SELECT id FROM flight_search_history ORDER BY saved_at DESC, id DESC LIMIT 80
        )''')
    return row_id


def list_recent(limit: int = 40) -> list[dict]:
    limit = max(1,min(limit,80))
    with LOCK, connect() as (conn, placeholder):
        _initialize(conn)
        rows = conn.cursor()
        rows.execute(f'''SELECT id,saved_at,origin,destination,departure,return_date,offers_count,min_price,snapshot
                           FROM flight_search_history ORDER BY saved_at DESC,id DESC LIMIT {limit}''')
        results = []
        for x in rows.fetchall():
            payload = json.loads(x[8])
            results.append({'id':x[0], 'saved_at':x[1], 'origin':x[2], 'destination':x[3],
                            'departure':x[4], 'return':x[5], 'offers_count':x[6],
                            'min_price':x[7], 'adults':payload['criteria']['adults'],
                            'children_ages':payload['criteria']['children_ages'],
                            'stops':payload['criteria']['stops']})
        return results


def get(row_id: str) -> dict | None:
    with LOCK, connect() as (conn, placeholder):
        _initialize(conn)
        cur = conn.cursor()
        cur.execute('SELECT saved_at,snapshot FROM flight_search_history WHERE id='+placeholder, (row_id,))
        row=cur.fetchone()
    if row is None:
        return None
    return {'id': row_id, 'saved_at':row[0], 'snapshot':json.loads(row[1])}


def delete(row_id: str) -> bool:
    with LOCK, connect() as (conn, placeholder):
        _initialize(conn)
        cur=conn.cursor()
        cur.execute('DELETE FROM flight_search_history WHERE id='+placeholder, (row_id,))
        return cur.rowcount > 0
