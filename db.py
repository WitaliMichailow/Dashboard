# db.py
"""SQLite-Persistenzschicht für das Studien-Dashboard.

Das Modul kapselt den Zugriff auf die Datei-Datenbank ``studium.db``.
Die Tabellenstruktur (DDL) ist so gewählt, dass die Objektstruktur des
Domänenmodells abgebildet wird (Studiengang, Semester, Modul, Belegung,
Prüfungsleistung) und über Fremdschlüssel mit ON DELETE CASCADE konsistent
bleibt.
"""

import sqlite3
from pathlib import Path

# Pfad zur SQLite-Datenbankdatei (wird bei Bedarf neu angelegt)
DB_PATH = Path("studium.db")

# Data Definition Language – legt das komplette Schema an
DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS studiengang (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  gesamt_ects INTEGER NOT NULL,
  regelstudienzeit INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS semester (
  id INTEGER PRIMARY KEY,
  nr INTEGER NOT NULL,
  bezeichnung TEXT NOT NULL,
  studiengang_id INTEGER NOT NULL REFERENCES studiengang(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS modul (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  kuerzel TEXT NOT NULL,
  ects INTEGER NOT NULL,
  pruefungsform TEXT NOT NULL,
  studiengang_id INTEGER NOT NULL REFERENCES studiengang(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS belegung (
  id INTEGER PRIMARY KEY,
  art TEXT NOT NULL CHECK(art IN ('geplant','aktuell')),
  kommentar TEXT,
  semester_id INTEGER NOT NULL REFERENCES semester(id) ON DELETE CASCADE,
  modul_id INTEGER NOT NULL REFERENCES modul(id) ON DELETE CASCADE,
  UNIQUE(semester_id, modul_id, art)
);

CREATE TABLE IF NOT EXISTS pruefungsleistung (
  id INTEGER PRIMARY KEY,
  bezeichnung TEXT NOT NULL,
  datum TEXT,
  note REAL,
  versuch_nr INTEGER NOT NULL DEFAULT 1,
  modul_id INTEGER NOT NULL REFERENCES modul(id) ON DELETE CASCADE
);
"""


def connect() -> sqlite3.Connection:
    """Stellt eine Verbindung zur SQLite-Datenbank her.

    * Aktiviert Fremdschlüssel-Prüfung (PRAGMA foreign_keys).
    * Setzt row_factory auf ``sqlite3.Row``, damit Ergebnisse wie Dicts
      verwendet werden können.
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    return con


def init_if_needed() -> None:
    """Initialisiert die Datenbank, falls sie noch nicht existiert.

    * Führt das DDL-Skript aus (Tabellen anlegen).
    * Legt bei leerer studiengang-Tabelle einen Default-Studiengang an
      ("Bachelor Cybersecurity", 180 ECTS, 8 Semester) sowie 8 Semester
      mit den Bezeichnungen "Semester 1" … "Semester 8".
    """
    con = connect()
    try:
        with con:
            # Schema anlegen (idempotent)
            con.executescript(DDL)
            # Prüfen, ob bereits ein Studiengang existiert
            cur = con.execute("SELECT COUNT(*) AS c FROM studiengang")
            if cur.fetchone()["c"] == 0:
                con.execute(
                    "INSERT INTO studiengang(name, gesamt_ects, regelstudienzeit) VALUES (?,?,?)",
                    ("Bachelor Cybersecurity", 180, 8),
                )
                sg_id = con.execute(
                    "SELECT id FROM studiengang LIMIT 1"
                ).fetchone()["id"]
                for nr in range(1, 9):
                    con.execute(
                        "INSERT INTO semester(nr, bezeichnung, studiengang_id) VALUES (?,?,?)",
                        (nr, f"Semester {nr}", sg_id),
                    )
    finally:
        con.close()
