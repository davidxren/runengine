CREATE TABLE athlete (
  key TEXT PRIMARY KEY,           -- hr_rest, hr_max, sex, mass_kg, lift_scale
  value TEXT NOT NULL
);
CREATE TABLE activities (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,           -- 'fit' | 'strava'
  source_id TEXT NOT NULL,        -- sha256 of the file, or strava activity id
  sport TEXT NOT NULL,            -- 'running' | 'strength' | other FIT sport names
  start_time INTEGER NOT NULL,    -- unix seconds UTC
  duration_s REAL NOT NULL,
  distance_m REAL,
  avg_hr INTEGER,
  max_hr INTEGER,
  device TEXT,
  UNIQUE (source, source_id)
);
CREATE INDEX activities_start ON activities (start_time);
CREATE TABLE records (
  activity_id INTEGER NOT NULL REFERENCES activities (id),
  ts INTEGER NOT NULL,            -- unix seconds UTC
  lat REAL, lon REAL,
  distance_m REAL,
  speed_mps REAL,
  heart_rate INTEGER,
  cadence_spm INTEGER,            -- steps per minute, both feet
  altitude_m REAL,
  power_w INTEGER,
  PRIMARY KEY (activity_id, ts)
);
CREATE TABLE laps (
  activity_id INTEGER NOT NULL REFERENCES activities (id),
  lap_index INTEGER NOT NULL,
  start_ts INTEGER NOT NULL,
  duration_s REAL NOT NULL,
  distance_m REAL,
  avg_speed_mps REAL,
  avg_hr INTEGER,
  trigger TEXT,                   -- 'manual' | 'distance' | 'time' | other
  PRIMARY KEY (activity_id, lap_index)
);
CREATE TABLE strength_sessions (
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,             -- YYYY-MM-DD
  minutes INTEGER NOT NULL,
  rpe REAL NOT NULL,              -- Foster CR10 scale, 0 to 10
  notes TEXT
);
CREATE TABLE performances (
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,
  kind TEXT NOT NULL,             -- 'race' | 'time_trial'
  distance_m REAL NOT NULL,
  time_s REAL NOT NULL,
  activity_id INTEGER REFERENCES activities (id),
  notes TEXT
);
