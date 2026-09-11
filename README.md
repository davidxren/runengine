# runengine

runengine imports the FIT files a Garmin watch records and produces one HTML report with four answers: whether aerobic fitness is improving, what each week's training load was with running and lifting combined, what half marathon pace is sustainable and with what error, and how consistent track repeats are.

I built it because those answers were spread across Garmin Connect, Strava and a spreadsheet, and none of them show their math. Every model in the report is a published formula implemented from the source, with a page under docs/models/ that states the formula, its assumptions, where it fails, and the paper it comes from.

## Design

Python 3.12. garmin-fit-sdk decodes the files into SQLite (activities, 1 Hz records, laps) through the standard library sqlite3 module, with no ORM. The models are pure numpy functions, each with an oracle test: a synthetic input whose correct output is known in closed form. matplotlib and jinja2 render the report, typer provides the CLI, dependencies are locked with uv, and CI runs the same make targets used locally.

## Data

No personal data is in this repository. FIT files live in data/, which is gitignored. Test fixtures are Garmin's public FIT SDK samples. Credentials for any API adapter come from environment variables only.

## Running it

```bash
make setup
make test
make lint
```

## Status

Nothing runs yet. Design notes land in docs/DESIGN.md as each part is built. Every number that appears in this README will be pasted from `make report` output, not typed.
