import csv
import datetime as dt
import json
import subprocess
from pathlib import Path

# === PATHS ===

ROOT = Path(__file__).parent

RUST_BINARY = ROOT / "sf_fetcher" / "target" / "release" / "sf_fetcher"

DATA_DIR = ROOT / "data"
CSV_PATH = DATA_DIR / "guild_levels.csv"

# === FUNKTIONER ===

def fetch_levels():
    """Kør Rust-programmet og få liste af {name, level}."""

    if not RUST_BINARY.exists():
        raise FileNotFoundError(f"Rust-binary findes ikke: {RUST_BINARY}\n"
                                "Har du kørt `cargo build --release` i sf_fetcher-mappen?")

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

    # Forventet format: liste af objekter med "name" og "level"
    levels = []
    for item in data:
        name = item.get("name")
        level = item.get("level")
        if name is None or level is None:
            continue
        levels.append({"name": name, "level": int(level)})

    return levels


def append_today(levels):
    """Append dagens levels til CSV: én række pr. spiller."""
    if not levels:
        print("Ingen levels at gemme i dag.")
        return

    # Sørg for at data-mappen findes
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    today = dt.date.today().isoformat()
    file_exists = CSV_PATH.exists()

    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["date", "name", "level"])

        for m in levels:
            writer.writerow([today, m["name"], m["level"]])

    print(f"Gemte {len(levels)} linjer i {CSV_PATH}")


def analyze_last_n_days(n_days, top_n):
    """Find hvem der har udviklet sig mest/mindst over de sidste n dage.

    Inkluderer KUN spillere, der har data for ALLE datoer i vinduet.
    """
    if not CSV_PATH.exists():
        print("Ingen CSV-fil endnu – ingen analyse.")
        return

    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("CSV er tom – ingen analyse.")
        return

    # Find unikke datoer
    dates = sorted({row["date"] for row in rows})
    if len(dates) < 2:
        print("Mindre end 2 dage med data – ikke så meget at analysere endnu.")
        return

    # Sidste n_days datoer (eller færre, hvis der ikke er så mange endnu)
    window_dates = dates[-n_days:]
    print(f"\nAnalyserer udvikling over disse datoer ({len(window_dates)} dage): {', '.join(window_dates)}")

    # (date, name) -> level
    levels_by_key = {}
    for row in rows:
        d = row["date"]
        if d not in window_dates:
            continue
        try:
            lvl = int(row["level"])
        except ValueError:
            continue
        key = (d, row["name"])
        levels_by_key[key] = lvl

    players = sorted({row["name"] for row in rows if row["date"] in window_dates})

    changes = []
    for name in players:
        # Saml levels i kronologisk rækkefølge for alle datoer i vinduet
        levels_for_player = [
            levels_by_key.get((d, name))
            for d in window_dates
        ]

        # Krav: spilleren skal have data for ALLE datoer i vinduet
        if any(lvl is None for lvl in levels_for_player):
            continue

        oldest_level = levels_for_player[0]
        newest_level = levels_for_player[-1]
        delta = newest_level - oldest_level

        changes.append({
            "name": name,
            "from": oldest_level,
            "to": newest_level,
            "delta": delta,
        })

    if not changes:
        print("Ingen spillere med komplette data i perioden.")
        return

    # Sortér efter udvikling (delta)
    changes_sorted = sorted(changes, key=lambda c: c["delta"])

    worst = changes_sorted[:top_n]
    best = list(reversed(changes_sorted))[:top_n]

    print(f"\n=== Mindst udvikling over de sidste {len(window_dates)} dage (top {len(worst)}) ===")
    for c in worst:
        print(f"{c['name']}: {c['from']} → {c['to']} (Δ {c['delta']})")

    print(f"\n=== Mest udvikling over de sidste {len(window_dates)} dage (top {len(best)}) ===")
    for c in best:
        print(f"{c['name']}: {c['from']} → {c['to']} (Δ {c['delta']})")

def project_levels_next_7_days(top_n=10):
    """Projekter hvilket level spillere er på om 7 dage,
    givet at de udvikler sig som de sidste 7 dage.

    Inkluderer KUN spillere, der har data for ALLE 7 datoer i vinduet.
    """
    if not CSV_PATH.exists():
        print("Ingen CSV-fil endnu – ingen projektion.")
        return

    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("CSV er tom – ingen projektion.")
        return

    # Find unikke datoer
    dates = sorted({row["date"] for row in rows})
    if len(dates) < 7:
        print("Mindre end 7 dages data – kan ikke lave 7-dages projektion endnu.")
        return

    # Sidste 7 datoer
    window_dates = dates[-7:]
    print(f"\nProjekterer level om 7 dage ud fra disse datoer: {', '.join(window_dates)}")

    # (date, name) -> level
    levels_by_key = {}
    for row in rows:
        d = row["date"]
        if d not in window_dates:
            continue
        try:
            lvl = int(row["level"])
        except ValueError:
            continue
        key = (d, row["name"])
        levels_by_key[key] = lvl

    players = sorted({row["name"] for row in rows if row["date"] in window_dates})

    projections = []
    for name in players:
        # Saml levels i kronologisk rækkefølge for alle datoer i vinduet
        levels_for_player = [
            levels_by_key.get((d, name))
            for d in window_dates
        ]

        # Krav: spilleren skal have data for ALLE 7 datoer
        if any(lvl is None for lvl in levels_for_player):
            continue

        oldest_level = levels_for_player[0]
        newest_level = levels_for_player[-1]
        delta = newest_level - oldest_level

        projected_level = newest_level + delta

        projections.append({
            "name": name,
            "from": oldest_level,
            "current": newest_level,
            "delta": delta,
            "projected": projected_level,
        })

    if not projections:
        print("Ingen spillere med komplette 7-dages data – ingen projektion.")
        return

    # Sortér efter projektionsniveau (højeste først)
    projections_sorted = sorted(projections, key=lambda p: p["projected"], reverse=True)

    top = projections_sorted[:top_n]

    print(f"\n=== Projekteret level om 7 dage (top {len(top)}) ===")
    for p in top:
        print(
            f"{p['name']}: {p['current']} nu, Δ sidste 7 dage = {p['delta']}, "
            f"projiceret om 7 dage: {p['projected']}"
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
