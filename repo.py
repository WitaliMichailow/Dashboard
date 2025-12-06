# repo.py
"""Repository-/Service-Schicht für das Studien-Dashboard.

Dieses Modul kapselt alle Zugriffe auf die SQLite-Datenbank und bildet daraus
Objekte des Domänenmodells (Studiengang, Semester, Modul, Pruefungsleistung).
Die Streamlit-Oberfläche arbeitet ausschließlich über diese Funktionen und
kennt die Details des Datenbankschemas nicht.
"""

from typing import List, Optional, Dict
from db import connect
from models import Studiengang, Semester, Modul, Pruefungsleistung, Pruefungsform


# ---------------------------------------------------------------------------
# Lesezugriffe – Aufbau des Domänenmodells aus der Datenbank
# ---------------------------------------------------------------------------

def get_ids():
    """Liefert die ID des Studiengangs sowie alle zugehörigen Semesterzeilen.

    Diese Hilfsfunktion wird hauptsächlich für Debugging / Auswertungen genutzt.
    """
    con = connect()
    try:
        sg = con.execute(
            "SELECT id, name, gesamt_ects, regelstudienzeit FROM studiengang"
        ).fetchone()
        sem = con.execute(
            "SELECT id, nr, bezeichnung FROM semester WHERE studiengang_id=?",
            (sg["id"],),
        ).fetchall()
        return sg, sem
    finally:
        con.close()


def load_domain() -> Studiengang:
    """Lädt den gesamten Studiengang in Objektform.

    Aus den Tabellen werden Studiengang, Semester, Module, Belegungen und
    Prüfungsleistungen eingelesen und in die Domain-Objekte überführt.
    """
    con = connect()
    try:
        sg_row = con.execute("SELECT * FROM studiengang LIMIT 1").fetchone()
        sg = Studiengang(
            sg_row["name"],
            sg_row["gesamt_ects"],
            sg_row["regelstudienzeit"],
        )

        # Semester anlegen und in einer Map merken (id → Semester-Objekt)
        sem_map: Dict[int, Semester] = {}
        for r in con.execute(
            "SELECT * FROM semester WHERE studiengang_id=? ORDER BY nr",
            (sg_row["id"],),
        ):
            sem = Semester(r["nr"], r["bezeichnung"])
            sem_map[r["id"]] = sem
            sg.add_semester(sem)

        # Module anlegen (id → Modul-Objekt)
        mod_map: Dict[int, Modul] = {}
        for r in con.execute(
            "SELECT * FROM modul WHERE studiengang_id=?",
            (sg_row["id"],),
        ):
            m = Modul(
                r["name"],
                r["kuerzel"],
                r["ects"],
                Pruefungsform[r["pruefungsform"]],
            )
            mod_map[r["id"]] = m
            sg.add_modul(m)

        # Belegungen Semester ↔ Modul
        for r in con.execute("SELECT * FROM belegung"):
            sem = sem_map[r["semester_id"]]
            mod = mod_map[r["modul_id"]]
            sem.belege(mod, r["art"])

        # Prüfungsleistungen je Modul
        for r in con.execute(
            "SELECT * FROM pruefungsleistung ORDER BY versuch_nr"
        ):
            mod = mod_map[r["modul_id"]]
            mod.add_pruefungsleistung(
                Pruefungsleistung(
                    r["bezeichnung"],
                    r["datum"],
                    r["note"],
                    r["versuch_nr"],
                )
            )

        return sg
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Schreiboperationen – Module, Prüfungsleistungen, Belegungen
# ---------------------------------------------------------------------------

def create_modul(name: str, kuerzel: str, ects: int, pruefungsform: Pruefungsform) -> None:
    """Legt ein neues Modul im aktuellen Studiengang an."""
    con = connect()
    try:
        with con:
            sg_id = con.execute("SELECT id FROM studiengang LIMIT 1").fetchone()["id"]
            con.execute(
                "INSERT INTO modul(name, kuerzel, ects, pruefungsform, studiengang_id)"
                " VALUES (?,?,?,?,?)",
                (name, kuerzel, ects, pruefungsform.name, sg_id),
            )
    finally:
        con.close()


def create_pruefungsleistung(
    modul_kuerzel: str,
    bezeichnung: str,
    datum: Optional[str],
    note: Optional[float],
    versuch_nr: int = 1,
) -> None:
    """Erzeugt eine neue Prüfungsleistung für das Modul mit dem gegebenen Kürzel."""
    con = connect()
    try:
        with con:
            mod_id = con.execute(
                "SELECT id FROM modul WHERE kuerzel=?",
                (modul_kuerzel,),
            ).fetchone()["id"]
            con.execute(
                "INSERT INTO pruefungsleistung(bezeichnung, datum, note, versuch_nr, modul_id)"
                " VALUES (?,?,?,?,?)",
                (bezeichnung, datum, note, versuch_nr, mod_id),
            )
    finally:
        con.close()


def create_belegung(
    semester_nr: int,
    modul_kuerzel: str,
    art: str,
    kommentar: str = "",
) -> None:
    """Ordnet ein Modul einem Semester zu (Belegung).

    art: "geplant" oder "aktuell" (im Dashboard als "geplant"/"bestanden" angezeigt)
    """
    con = connect()
    try:
        with con:
            sem_id = con.execute(
                "SELECT s.id FROM semester s JOIN studiengang g ON g.id=s.studiengang_id"
                " WHERE s.nr=? LIMIT 1",
                (semester_nr,),
            ).fetchone()["id"]
            mod_id = con.execute(
                "SELECT id FROM modul WHERE kuerzel=? LIMIT 1",
                (modul_kuerzel,),
            ).fetchone()["id"]
            con.execute(
                "INSERT OR IGNORE INTO belegung(art, kommentar, semester_id, modul_id)"
                " VALUES (?,?,?,?)",
                (art, kommentar, sem_id, mod_id),
            )
    finally:
        con.close()


def list_module() -> List[dict]:
    """Gibt alle Module (für Drop-downs etc.) als einfache Dicts zurück."""
    con = connect()
    try:
        rows = con.execute(
            "SELECT name, kuerzel, ects, pruefungsform FROM modul ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def list_semester_nrn() -> List[int]:
    """Liste aller existierenden Semesternummern (z. B. [1, 2, ..., 8])."""
    con = connect()
    try:
        rows = con.execute("SELECT nr FROM semester ORDER BY nr").fetchall()
        return [r["nr"] for r in rows]
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Erweiterte Funktionen: CRUD für Module, Leistungen, Belegungen
# ---------------------------------------------------------------------------

def _get_modul_id(kuerzel: str) -> int:
    """Hilfsfunktion: ermittelt die Modul-ID zum Kürzel oder wirft einen Fehler."""
    con = connect()
    try:
        row = con.execute(
            "SELECT id FROM modul WHERE kuerzel=? LIMIT 1", (kuerzel,)
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise ValueError(f"Modul '{kuerzel}' nicht gefunden")
    return row["id"]


def get_modul(kuerzel: str) -> Dict:
    """Liest die Stammdaten eines Moduls als Dict."""
    con = connect()
    try:
        row = con.execute(
            "SELECT name, kuerzel, ects, pruefungsform FROM modul WHERE kuerzel=? LIMIT 1",
            (kuerzel,),
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise ValueError(f"Modul '{kuerzel}' nicht gefunden")
    return dict(row)


def update_modul(
    kuerzel: str,
    *,
    name: Optional[str] = None,
    new_kuerzel: Optional[str] = None,
    ects: Optional[int] = None,
    pruefungsform: Optional[Pruefungsform] = None,
) -> None:
    """Aktualisiert einzelne Felder eines Moduls.

    Nicht übergebene Parameter bleiben unverändert.
    """
    mod_id = _get_modul_id(kuerzel)
    sets, params = [], []
    if name is not None:
        sets.append("name=?"); params.append(name)
    if new_kuerzel is not None:
        sets.append("kuerzel=?"); params.append(new_kuerzel)
    if ects is not None:
        sets.append("ects=?"); params.append(int(ects))
    if pruefungsform is not None:
        sets.append("pruefungsform=?"); params.append(pruefungsform.name)
    if not sets:
        return
    params.append(mod_id)
    con = connect()
    try:
        with con:
            con.execute(
                f"UPDATE modul SET {', '.join(sets)} WHERE id=?",
                params,
            )
    finally:
        con.close()


def delete_modul(kuerzel: str) -> None:
    """Löscht ein Modul (inkl. abhängiger Leistungen/Belegungen per CASCADE)."""
    mod_id = _get_modul_id(kuerzel)
    con = connect()
    try:
        with con:
            con.execute("DELETE FROM modul WHERE id=?", (mod_id,))
    finally:
        con.close()


def list_pruefungsleistungen(kuerzel: str) -> List[Dict]:
    """Liefert alle Prüfungsleistungen eines Moduls als Liste von Dicts."""
    mod_id = _get_modul_id(kuerzel)
    con = connect()
    try:
        rows = con.execute(
            "SELECT id, bezeichnung, datum, note, versuch_nr FROM pruefungsleistung"
            " WHERE modul_id=? ORDER BY versuch_nr, id",
            (mod_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def update_pruefungsleistung(
    pl_id: int,
    *,
    bezeichnung: Optional[str] = None,
    datum: Optional[Optional[str]] = None,
    note: Optional[Optional[float]] = None,
    versuch_nr: Optional[int] = None,
) -> None:
    """Aktualisiert eine vorhandene Prüfungsleistung.

    Besonderheit:
    * datum = None  → Datum auf NULL setzen.
    * note = None   → Note auf NULL setzen.
    """
    sets, params = [], []
    if bezeichnung is not None:
        sets.append("bezeichnung=?"); params.append(bezeichnung)
    if datum is not None:
        sets.append("datum=?"); params.append(datum)  # None → NULL
    if note is not None:
        sets.append("note=?"); params.append(note)    # None → NULL
    if versuch_nr is not None:
        sets.append("versuch_nr=?"); params.append(int(versuch_nr))
    if not sets:
        return
    params.append(pl_id)
    con = connect()
    try:
        with con:
            con.execute(
                f"UPDATE pruefungsleistung SET {', '.join(sets)} WHERE id=?",
                params,
            )
    finally:
        con.close()


def delete_pruefungsleistung(pl_id: int) -> None:
    """Löscht eine Prüfungsleistung."""
    con = connect()
    try:
        with con:
            con.execute(
                "DELETE FROM pruefungsleistung WHERE id=?",
                (pl_id,),
            )
    finally:
        con.close()


def list_belegungen(
    kuerzel: Optional[str] = None,
    semester_nr: Optional[int] = None,
) -> List[Dict]:
    """Listet Belegungen (Semester ↔ Modul) optional gefiltert nach Modul/Semester."""
    q = (
        "SELECT b.id, b.art, b.kommentar, s.nr AS semester_nr, m.kuerzel AS modul"
        " FROM belegung b"
        " JOIN semester s ON s.id=b.semester_id"
        " JOIN modul m ON m.id=b.modul_id"
        " WHERE 1=1"
    )
    args: List[object] = []
    if kuerzel is not None:
        q += " AND m.kuerzel=?"; args.append(kuerzel)
    if semester_nr is not None:
        q += " AND s.nr=?"; args.append(semester_nr)
    q += " ORDER BY s.nr, m.kuerzel, b.art"
    con = connect()
    try:
        rows = con.execute(q, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def update_belegung(
    semester_nr: int,
    modul_kuerzel: str,
    *,
    art: Optional[str] = None,
    kommentar: Optional[str] = None,
) -> None:
    """Aktualisiert eine bestehende Belegung."""
    con = connect()
    try:
        with con:
            sem_id = con.execute(
                "SELECT id FROM semester WHERE nr=? LIMIT 1",
                (semester_nr,),
            ).fetchone()["id"]
            mod_id = con.execute(
                "SELECT id FROM modul WHERE kuerzel=? LIMIT 1",
                (modul_kuerzel,),
            ).fetchone()["id"]
            sets, params = [], []
            if art is not None:
                sets.append("art=?"); params.append(art)
            if kommentar is not None:
                sets.append("kommentar=?"); params.append(kommentar)
            if sets:
                params.extend([sem_id, mod_id])
                con.execute(
                    f"UPDATE belegung SET {', '.join(sets)} WHERE semester_id=? AND modul_id=?",
                    params,
                )
    finally:
        con.close()


def delete_belegung(semester_nr: int, modul_kuerzel: str, art: str) -> None:
    """Löscht eine bestimmte Belegung."""
    con = connect()
    try:
        with con:
            sem_id = con.execute(
                "SELECT id FROM semester WHERE nr=? LIMIT 1",
                (semester_nr,),
            ).fetchone()["id"]
            mod_id = con.execute(
                "SELECT id FROM modul WHERE kuerzel=? LIMIT 1",
                (modul_kuerzel,),
            ).fetchone()["id"]
            con.execute(
                "DELETE FROM belegung WHERE semester_id=? AND modul_id=? AND art=?",
                (sem_id, mod_id, art),
            )
    finally:
        con.close()
