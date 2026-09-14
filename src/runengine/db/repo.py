# Transactions belong to the caller. Nothing here commits: the importer wraps one
# file's activity, records and laps in a single `with conn:` so a failure anywhere
# leaves no half-imported activity for the UNIQUE constraint to skip on the next run.
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 1

FloatArray = NDArray[np.float64]


# Field order is the schema column order: the INSERTs below bind positionally.
class Activity(NamedTuple):
    source: str
    source_id: str
    sport: str
    start_time: int
    duration_s: float
    distance_m: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    device: str | None = None


class Record(NamedTuple):
    ts: int
    lat: float | None = None
    lon: float | None = None
    distance_m: float | None = None
    speed_mps: float | None = None
    heart_rate: int | None = None
    cadence_spm: int | None = None
    altitude_m: float | None = None
    power_w: int | None = None


class Lap(NamedTuple):
    lap_index: int
    start_ts: int
    duration_s: float
    distance_m: float | None = None
    avg_speed_mps: float | None = None
    avg_hr: int | None = None
    trigger: str | None = None


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    try:
        # Before any statement can open a transaction: inside one this pragma is a no-op.
        conn.execute("PRAGMA foreign_keys = ON")
        (version,) = conn.execute("PRAGMA user_version").fetchone()
        if version == 0:
            # Tables and version stamp commit together, so a crash between them cannot
            # leave a file that the next connect would try to CREATE TABLE on again.
            conn.executescript(
                f"BEGIN;\n{SCHEMA_PATH.read_text()}\n"
                f"PRAGMA user_version = {SCHEMA_VERSION};\nCOMMIT;"
            )
        elif version != SCHEMA_VERSION:
            raise RuntimeError(f"{path}: schema version {version}, expected {SCHEMA_VERSION}")
    except BaseException:
        # A failed connect must not hand back, or leak, a connection holding a write lock.
        conn.close()
        raise
    return conn


def insert_activity(conn: sqlite3.Connection, activity: Activity) -> int | None:
    # DO NOTHING is scoped to the (source, source_id) pair, so a re-import returns None
    # while a NOT NULL violation still raises. INSERT OR IGNORE would swallow both.
    cur = conn.execute(
        "INSERT INTO activities"
        " (source, source_id, sport, start_time, duration_s, distance_m, avg_hr, max_hr, device)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (source, source_id) DO NOTHING",
        activity,
    )
    # lastrowid keeps the previous insert's id after DO NOTHING; rowcount is the signal.
    return cur.lastrowid if cur.rowcount == 1 else None


def insert_records(conn: sqlite3.Connection, activity_id: int, records: Iterable[Record]) -> None:
    conn.executemany(
        "INSERT INTO records"
        " (activity_id, ts, lat, lon, distance_m, speed_mps,"
        " heart_rate, cadence_spm, altitude_m, power_w)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ((activity_id, *record) for record in records),
    )


def insert_laps(conn: sqlite3.Connection, activity_id: int, laps: Iterable[Lap]) -> None:
    conn.executemany(
        "INSERT INTO laps"
        " (activity_id, lap_index, start_ts, duration_s,"
        " distance_m, avg_speed_mps, avg_hr, trigger)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ((activity_id, *lap) for lap in laps),
    )


def upsert_athlete(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO athlete (key, value) VALUES (?, ?)"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_athlete(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM athlete WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row[0])


def get_activity_records(
    conn: sqlite3.Connection, activity_id: int
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    rows = conn.execute(
        "SELECT ts, speed_mps, heart_rate, distance_m FROM records"
        " WHERE activity_id = ? ORDER BY ts",
        (activity_id,),
    ).fetchall()
    # dtype float64 turns NULL (None) into nan; reshape keeps four columns when there
    # are no rows.
    table = np.asarray(rows, dtype=np.float64).reshape(-1, 4)
    ts, speed_mps, heart_rate, distance_m = table.T
    return ts, speed_mps, heart_rate, distance_m
