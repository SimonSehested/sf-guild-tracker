import csv
import json
import subprocess
from datetime import date
from pathlib import Path

# === PATHS ===

ROOT = Path(__file__).parent

RUST_BINARY = ROOT / "sf_fetcher" / "target" / "release" / "sf_fetcher"

DATA_DIR = ROOT / "data"
CSV_PATH = DATA_DIR / "guild_levels.csv"


# === HJÆLPEFUNKTIONER (DATA) ===

def _load_csv_rows():
    """Læs alle rækker fra CSV-fil, eller returnér tom liste hvis ikke findes/ingen data."""
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _build_levels_by_key(rows, window_dates):
    """Lav mapping (date, name) -> level for de datoer, vi kigger på."""
    levels_by_key = {}
    window_dates_set = set(window_dates)
    for row in rows:
        d = row.get("date")
        if d not in window_dates_set:
            continue
        try:
            lvl = int(row["level"])
        except (ValueError, TypeError, KeyError):
            continue
        name = row.get("name")
        if not name:
            continue
        levels_by_key[(d, name)] = lvl
    return levels_by_key


def _players_with_full_window(levels_by_key, window_dates):
    """Yield (name, [levels i kronologisk rækkefølge]) for spillere med komplette data."""
    players = sorted({name for (_d, name) in levels_by_key.keys()})
    for name in players:
        levels_for_player = [
            levels_by_key.get((d, name)) for d in window_dates
        ]
        if any(lvl is None for lvl in levels_for_player):
            continue
        yield name, levels_for_player


# === HJÆLPEFUNTIONER (OUTPUT) ===

def _format_delta(n: int) -> str:
    """Formatér ændring med fortegn, fx +12 eller -3."""
    return f"{n:+d}"


def _print_table(headers, rows, title=None):
    """Print en simpel tekstanalyse-tabel med justerede kolonner."""
    if title:
        print(title)
        print("-" * len(title))

    if not rows:
        print("(ingen data)\n")
        return

    # Beregn kolonnebredder
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # Header
    header_line = " | ".join(
        f"{headers[i]:<{col_widths[i]}}" for i in range(len(headers))
    )
    separator_line = "-+-".join(
        "-" * col_widths[i] for i in range(len(headers))
    )

    print(header_line)
    print(separator_line)

    # Rækker
    for row in rows:
        print(
            " | ".join(
                f"{str(row[i]):<{col_widths[i]}}" for i in range(len(headers))
            )
        )
    print()  # Tom linje efter tabel


# === FUNKTIONER ===

def fetch_levels():
    """Kør Rust-programmet og få liste af {name, level}."""
    if not RUST_BINARY.exists():
        raise FileNotFoundError(
            f"Rust-binary findes ikke: {RUST_BINARY}\n"
            "Har du kørt `cargo build --release` i sf_fetcher-mappen?"
        )

    result = subprocess.run(
        [str(RUST_BINARY)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Rust-program fejlede.\n"
            f"Exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Kunne ikke parse JSON fra Rust-programmet:\n{e}\nOutput var:\n{result.stdout}"
        )

    levels = []
    for item in data:
        name = item.get("name")
        level = item.get("level")
        if name is None or level is None:
            continue
        try:
            levels.append({"name": name, "level": int(level)})
        except (ValueError, TypeError):
            # Skipper entries, der ikke kan parses som int
            continue

    return levels


def append_today(levels):
    """Append dagens levels til CSV: én række pr. spiller."""
    if not levels:
        print("Ingen levels at gemme i dag.")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    file_exists = CSV_PATH.exists()

    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["date", "name", "level"])

        for m in levels:
            writer.writerow([today, m["name"], m["level"]])

    print(f"[LOG] Gemte {len(levels)} linjer i {CSV_PATH}\n")


def analyze_last_n_days(n_days, top_n):
    """Find hvem der har udviklet sig mest/mindst over de sidste n dage.

    Inkluderer KUN spillere, der har data for ALLE datoer i vinduet.
    """
    rows = _load_csv_rows()
    if not rows:
        if not CSV_PATH.exists():
            print("Ingen CSV-fil endnu - ingen analyse.\n")
        else:
            print("CSV er tom - ingen analyse.\n")
        return

    dates = sorted({row["date"] for row in rows if row.get("date")})
    if len(dates) < 2:
        print("Mindre end 2 dage med data - ikke så meget at analysere endnu.\n")
        return

    window_dates = dates[-n_days:]

    print("=" * 60)
    print(f"ANALYSE: Udvikling over de sidste {len(window_dates)} dage")
    print("=" * 60)
    print(f"Datoer: {', '.join(window_dates)}")

    levels_by_key = _build_levels_by_key(rows, window_dates)

    changes = []
    for name, levels_for_player in _players_with_full_window(levels_by_key, window_dates):
        oldest_level = levels_for_player[0]
        newest_level = levels_for_player[-1]
        delta = newest_level - oldest_level
        changes.append(
            {
                "name": name,
                "from": oldest_level,
                "to": newest_level,
                "delta": delta,
            }
        )

    if not changes:
        print("Ingen spillere med komplette data i perioden.\n")
        return

    changes_sorted = sorted(changes, key=lambda c: c["delta"])

    print(f"Antal spillere i analysen: {len(changes)}\n")

    # Mindst udvikling
    worst = changes_sorted[:top_n]
    worst_rows = [
        [
            i,
            c["name"],
            c["from"],
            c["to"],
            _format_delta(c["delta"]),
        ]
        for i, c in enumerate(worst, start=1)
    ]
    _print_table(
        headers=["#", "Spiller", "Fra", "Til", "Δ"],
        rows=worst_rows,
        title=f"Mindst udvikling (top {len(worst)})",
    )

    # Mest udvikling
    best = list(reversed(changes_sorted))[:top_n]
    best_rows = [
        [
            i,
            c["name"],
            c["from"],
            c["to"],
            _format_delta(c["delta"]),
        ]
        for i, c in enumerate(best, start=1)
    ]
    _print_table(
        headers=["#", "Spiller", "Fra", "Til", "Δ"],
        rows=best_rows,
        title=f"Mest udvikling (top {len(best)})",
    )


def project_levels_next_7_days(top_n=10):
    """Projekter hvilket level spillere er på om 7 dage,
    givet at de udvikler sig som de sidste 7 dage.

    Inkluderer KUN spillere, der har data for ALLE 7 datoer i vinduet.
    """
    rows = _load_csv_rows()
    if not rows:
        if not CSV_PATH.exists():
            print("Ingen CSV-fil endnu - ingen projektion.\n")
        else:
            print("CSV er tom - ingen projektion.\n")
        return

    dates = sorted({row["date"] for row in rows if row.get("date")})
    if len(dates) < 7:
        print("Mindre end 7 dages data - kan ikke lave 7-dages projektion endnu.\n")
        return

    window_dates = dates[-7:]

    print("=" * 60)
    print("PROJEKTION: Forventet level om 7 dage")
    print("=" * 60)
    print(f"Grundlag: Udvikling over disse datoer: {', '.join(window_dates)}")

    levels_by_key = _build_levels_by_key(rows, window_dates)

    projections = []
    for name, levels_for_player in _players_with_full_window(levels_by_key, window_dates):
        oldest_level = levels_for_player[0]
        newest_level = levels_for_player[-1]
        delta = newest_level - oldest_level
        projected_level = newest_level + delta

        projections.append(
            {
                "name": name,
                "from": oldest_level,
                "current": newest_level,
                "delta": delta,
                "projected": projected_level,
            }
        )

    if not projections:
        print("Ingen spillere med komplette 7-dages data - ingen projektion.\n")
        return

    projections_sorted = sorted(projections, key=lambda p: p["projected"])
    worst = projections_sorted[:top_n]

    rows = [
        [
            i,
            p["name"],
            p["from"],
            p["current"],
            _format_delta(p["delta"]),
            p["projected"],
        ]
        for i, p in enumerate(worst, start=1)
    ]

    _print_table(
        headers=["#", "Spiller", "Start", "Nu", "Δ (7 dage)", "Projiceret (7 dage)"],
        rows=rows,
        title=f"De {len(worst)} laveste forventede levels om 7 dage",
    )


def main():
    try:
        levels = fetch_levels()
    except Exception as e:
        print("FEJL ved hentning af levels fra Rust-programmet:\n")
        print(e)
        return

    append_today(levels)

    # 3-dages analyse
    analyze_last_n_days(n_days=3, top_n=10)

    # 7-dages analyse
    analyze_last_n_days(n_days=7, top_n=10)

    # 7-dages projektion
    project_levels_next_7_days(top_n=10)


if __name__ == "__main__":
    main()
