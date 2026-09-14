import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from runengine.db import repo
from runengine.db.repo import Activity, Lap, Record

RUN = Activity(
    source="fit",
    source_id="a" * 64,
    sport="running",
    start_time=1_800_000_000,
    duration_s=3600.0,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "run.db"


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = repo.connect(db_path)
    yield conn
    conn.close()


def insert_run(conn: sqlite3.Connection) -> int:
    activity_id = repo.insert_activity(conn, RUN)
    assert activity_id is not None
    return activity_id


def test_fresh_file_gets_schema_version_one_and_foreign_keys_on(
    conn: sqlite3.Connection,
) -> None:
    assert conn.execute("PRAGMA user_version").fetchone() == (1,)
    assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {
        "athlete",
        "activities",
        "records",
        "laps",
        "strength_sessions",
        "performances",
    }


def test_reopen_keeps_data_and_does_not_rerun_schema(
    conn: sqlite3.Connection, db_path: Path
) -> None:
    insert_run(conn)
    conn.commit()
    conn.close()
    again = repo.connect(db_path)
    try:
        assert again.execute("PRAGMA user_version").fetchone() == (1,)
        assert again.execute("SELECT count(*) FROM activities").fetchone() == (1,)
    finally:
        again.close()


def test_unknown_schema_version_is_refused(db_path: Path) -> None:
    raw = sqlite3.connect(db_path)
    raw.execute("PRAGMA user_version = 7")
    raw.close()
    with pytest.raises(RuntimeError, match="schema version 7"):
        repo.connect(db_path)


def test_failed_schema_init_releases_the_file(db_path: Path) -> None:
    raw = sqlite3.connect(db_path)
    raw.execute("CREATE TABLE records (x)")
    raw.commit()
    raw.close()
    with pytest.raises(sqlite3.OperationalError, match="already exists"):
        repo.connect(db_path)
    # 0.2 s so a lock still held by the failed connect fails fast instead of after 5 s.
    other = sqlite3.connect(db_path, timeout=0.2)
    try:
        other.execute("CREATE TABLE probe (x)")
        other.commit()
    finally:
        other.close()


def test_every_activity_column_round_trips_in_schema_order(conn: sqlite3.Connection) -> None:
    full = Activity(
        source="fit",
        source_id="b" * 64,
        sport="running",
        start_time=1_800_000_000,
        duration_s=3600.0,
        distance_m=10_000.0,
        avg_hr=150,
        max_hr=180,
        device="forerunner",
    )
    activity_id = repo.insert_activity(conn, full)
    assert conn.execute("SELECT * FROM activities").fetchall() == [(activity_id, *full)]


def test_records_come_back_in_ts_order_regardless_of_insert_order(
    conn: sqlite3.Connection,
) -> None:
    activity_id = insert_run(conn)
    repo.insert_records(
        conn,
        activity_id,
        [
            Record(ts=30, speed_mps=3.0, heart_rate=150, distance_m=60.0),
            Record(ts=10, speed_mps=1.0, heart_rate=130, distance_m=10.0),
            Record(ts=20, speed_mps=2.0, heart_rate=140, distance_m=30.0),
        ],
    )
    ts, speed_mps, heart_rate, distance_m = repo.get_activity_records(conn, activity_id)
    np.testing.assert_array_equal(ts, [10.0, 20.0, 30.0])
    np.testing.assert_array_equal(speed_mps, [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(heart_rate, [130.0, 140.0, 150.0])
    np.testing.assert_array_equal(distance_m, [10.0, 30.0, 60.0])
    assert all(a.dtype == np.float64 for a in (ts, speed_mps, heart_rate, distance_m))


def test_records_are_scoped_to_their_activity(conn: sqlite3.Connection) -> None:
    first = insert_run(conn)
    second = repo.insert_activity(conn, RUN._replace(source_id="c" * 64))
    assert second is not None
    repo.insert_records(conn, first, [Record(ts=10), Record(ts=30)])
    repo.insert_records(conn, second, [Record(ts=20)])
    np.testing.assert_array_equal(repo.get_activity_records(conn, first)[0], [10.0, 30.0])
    np.testing.assert_array_equal(repo.get_activity_records(conn, second)[0], [20.0])


def test_null_columns_come_back_as_nan(conn: sqlite3.Connection) -> None:
    activity_id = insert_run(conn)
    repo.insert_records(
        conn, activity_id, [Record(ts=1, heart_rate=120), Record(ts=2, speed_mps=2.5)]
    )
    ts, speed_mps, heart_rate, distance_m = repo.get_activity_records(conn, activity_id)
    np.testing.assert_array_equal(ts, [1.0, 2.0])
    np.testing.assert_array_equal(speed_mps, [np.nan, 2.5])
    np.testing.assert_array_equal(heart_rate, [120.0, np.nan])
    np.testing.assert_array_equal(distance_m, [np.nan, np.nan])


def test_activity_with_no_records_gives_empty_float_arrays(conn: sqlite3.Connection) -> None:
    arrays = repo.get_activity_records(conn, insert_run(conn))
    assert [a.shape for a in arrays] == [(0,)] * 4
    assert all(a.dtype == np.float64 for a in arrays)


def test_every_record_column_round_trips_in_schema_order(conn: sqlite3.Connection) -> None:
    activity_id = insert_run(conn)
    full = Record(
        ts=5,
        lat=42.35,
        lon=-71.06,
        distance_m=12.5,
        speed_mps=3.2,
        heart_rate=155,
        cadence_spm=172,
        altitude_m=20.0,
        power_w=250,
    )
    repo.insert_records(conn, activity_id, [full])
    assert conn.execute("SELECT * FROM records").fetchall() == [(activity_id, *full)]


def test_every_lap_column_round_trips_in_schema_order(conn: sqlite3.Connection) -> None:
    activity_id = insert_run(conn)
    laps = [
        Lap(
            lap_index=0,
            start_ts=100,
            duration_s=90.0,
            distance_m=410.0,
            avg_speed_mps=4.5,
            avg_hr=170,
            trigger="manual",
        ),
        Lap(lap_index=1, start_ts=190, duration_s=95.0),
    ]
    repo.insert_laps(conn, activity_id, laps)
    rows = conn.execute("SELECT * FROM laps ORDER BY lap_index").fetchall()
    assert rows == [(activity_id, *lap) for lap in laps]


def test_duplicate_source_id_returns_none_and_keeps_first_row(conn: sqlite3.Connection) -> None:
    first = insert_run(conn)
    assert repo.insert_activity(conn, RUN._replace(sport="strength")) is None
    assert conn.execute("SELECT id, sport FROM activities").fetchall() == [(first, "running")]


def test_same_source_id_under_another_source_is_a_new_activity(
    conn: sqlite3.Connection,
) -> None:
    fit_id = insert_run(conn)
    strava_id = repo.insert_activity(conn, RUN._replace(source="strava"))
    assert strava_id is not None
    assert strava_id != fit_id


def test_other_constraint_violations_still_raise(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
        repo.insert_activity(conn, RUN._replace(sport=cast(str, None)))


def test_orphan_record_is_rejected(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        repo.insert_records(conn, 999, [Record(ts=1)])


def test_orphan_lap_is_rejected(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        repo.insert_laps(conn, 999, [Lap(lap_index=0, start_ts=1, duration_s=1.0)])


def test_writes_leave_the_transaction_open_for_the_caller(conn: sqlite3.Connection) -> None:
    activity_id = insert_run(conn)
    repo.insert_records(conn, activity_id, [Record(ts=t) for t in range(3)])
    repo.insert_laps(conn, activity_id, [Lap(lap_index=0, start_ts=0, duration_s=3.0)])
    repo.upsert_athlete(conn, "hr_rest", "50")
    assert conn.in_transaction
    conn.rollback()
    for table in ("activities", "records", "laps", "athlete"):
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


def test_athlete_upsert_overwrites_and_missing_key_is_none(conn: sqlite3.Connection) -> None:
    repo.upsert_athlete(conn, "hr_rest", "50")
    repo.upsert_athlete(conn, "hr_rest", "48")
    assert repo.get_athlete(conn, "hr_rest") == "48"
    assert repo.get_athlete(conn, "hr_max") is None
    assert conn.execute("SELECT count(*) FROM athlete").fetchone() == (1,)
