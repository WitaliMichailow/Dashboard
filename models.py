# models.py
"""Domänenmodell für das Studien-Dashboard.

Die Klassen in diesem Modul bilden das UML-Entitätsmodell aus Phase 1/2 ab:
* Studiengang
* Semester
* Modul
* Pruefungsleistung
* Pruefungsform (Enum)

Die Beziehungen entsprechen den im UML beschriebenen Kardinalitäten:
* Ein Studiengang aggregiert mehrere Semester und Module.
* Ein Semester verwaltet geplante und (aktuelle/bestandene) Module.
* Ein Modul besitzt mehrere Prüfungsleistungen (Komposition).
"""

from enum import Enum
from typing import List, Optional
from statistics import mean


class Pruefungsform(Enum):
    """Enum mit allen zulässigen Prüfungsformen.

    Die Verwendung eines Enum stellt sicher, dass nur eine feste, endliche Menge
    von Prüfungsformen im System vorkommt (z. B. KLAUSUR oder PROJEKT) und
    direkt den UML-Typ „Prüfungsform“ widerspiegelt.
    """

    KLAUSUR = "KLAUSUR"
    HAUSARBEIT = "HAUSARBEIT"
    PORTFOLIO = "PORTFOLIO"
    MUENDLICH = "MUENDLICH"
    PROJEKT = "PROJEKT"


class Pruefungsleistung:
    """Repräsentiert eine einzelne Prüfungsleistung zu genau einem Modul.

    Eine Prüfungsleistung gehört semantisch immer zu einem Modul
    (Komposition im UML: Modul *-- Pruefungsleistung). Ohne zugehöriges
    Modul wäre eine Prüfungsleistung inhaltlich bedeutungslos.
    """

    def __init__(
        self,
        bezeichnung: str,
        datum: Optional[str],
        note: Optional[float],
        versuch_nr: int = 1,
    ) -> None:
        # Attributnamen sind „gekapselt“ (Konvention: führender Unterstrich)
        self._bezeichnung = bezeichnung
        self._datum = datum  # ISO-Datum „YYYY-MM-DD“ oder None
        self._note = note    # 1.0 .. 5.0 oder None (noch keine Bewertung)
        self._versuch_nr = versuch_nr

    @property
    def note(self) -> Optional[float]:
        """Die Note dieser Prüfungsleistung (oder None, wenn noch nicht bekannt)."""
        return self._note

    @property
    def ist_bestanden(self) -> bool:
        """True, wenn eine Note vorhanden ist und diese ≤ 4,0 ist."""
        return self._note is not None and self._note <= 4.0


class Modul:
    """Repräsentiert ein Studienmodul inkl. zugehöriger Prüfungsleistungen.

    Wichtiger Designpunkt: Ein Modul besitzt KEIN eigenes „note“-Attribut,
    weil die Note fachlich aus den zugehörigen Prüfungsleistungen abgeleitet
    wird. Der Notendurchschnitt wird daher über die Property ``durchschnitt``
    berechnet und ist damit nicht redundant im Modell hinterlegt.
    """

    def __init__(self, name: str, kuerzel: str, ects: int, pruefungsform: Pruefungsform) -> None:
        self._name = name
        self._kuerzel = kuerzel
        self._ects = ects
        self._pruefungsform = pruefungsform
        # Komposition: Ein Modul „besitzt“ seine Prüfungsleistungen
        self._leistungen: List[Pruefungsleistung] = []

    # ---- Fachlich relevante Methoden (UML-Operationen) als Properties ----
    @property
    def durchschnitt(self) -> Optional[float]:
        """Arithmetischer Mittelwert aller vorhandenen Noten dieses Moduls.

        Gibt None zurück, wenn noch keine bewerteten Prüfungsleistungen vorliegen.
        """
        noten = [p.note for p in self._leistungen if p.note is not None]
        return round(mean(noten), 2) if noten else None

    @property
    def ist_bestanden(self) -> bool:
        """True, wenn ein Durchschnitt existiert und dieser ≤ 4,0 ist."""
        d = self.durchschnitt
        return d is not None and d <= 4.0

    @property
    def status(self) -> str:
        """Status des Moduls:

        * "offen"    – Es existieren noch keine Prüfungsleistungen.
        * "laufend" – Es gibt bereits Prüfungsleistungen, das Modul ist aber nicht bestanden.
        * "abgeschlossen" – Der Durchschnitt ist vorhanden und bestanden.
        """
        if not self._leistungen:
            return "offen"
        return "abgeschlossen" if self.ist_bestanden else "laufend"

    # ---- Fachliche Operation ----
    def add_pruefungsleistung(self, leistung: Pruefungsleistung) -> None:
        """Fügt dem Modul eine neue Prüfungsleistung hinzu."""
        self._leistungen.append(leistung)

    # ---- Lesezugriffe für andere Schichten (UI, Repository) ----
    @property
    def name(self) -> str:
        return self._name

    @property
    def kuerzel(self) -> str:
        return self._kuerzel

    @property
    def ects(self) -> int:
        return self._ects

    @property
    def pruefungsform(self) -> Pruefungsform:
        return self._pruefungsform

    @property
    def leistungen(self) -> List[Pruefungsleistung]:
        """Defensiv kopierte Liste der Prüfungsleistungen."""
        return list(self._leistungen)


class Belegung:
    """Hilfsklasse zur Modellierung einer Belegung (geplant/aktuell) im UML.

    In der konkreten Python-Implementierung werden Belegungen primär in der
    Datenbank und im ``Semester``-Objekt abgebildet. Die Klasse ist vor allem
    für das UML-Modell relevant und dokumentiert die Domänenidee.
    """

    def __init__(self, art: str, kommentar: str = "") -> None:
        # art: "geplant" | "aktuell"
        self._art = art
        self._kommentar = kommentar

    @property
    def art(self) -> str:
        return self._art


class Semester:
    """Repräsentiert ein Semester im Studiengang.

    Ein Semester verwaltet die Zuordnung von Modulen, die in diesem Semester
    eingeplant oder aktuell belegt/bestanden sind. Die Kardinalität im UML ist
    damit: Semester 1..* Modul (geplante/bestandene).
    """

    def __init__(self, nummer: int, bezeichnung: str) -> None:
        self._nummer = nummer
        self._bezeichnung = bezeichnung
        self._geplante_module: List[Modul] = []
        self._bestandene_module: List[Modul] = []

    def belege(self, modul: Modul, art: str) -> None:
        """Ordnet ein Modul diesem Semester zu.

        * art == "geplant"  → Modul wird als geplantes Modul geführt.
        * alles andere       → Modul wird in die Liste der (aktuell/bestandenen)
                               Module aufgenommen.

        Dadurch kann ein Modul theoretisch auch mehreren Semestern zugeordnet
        werden (z. B. Planung in einem Semester, Abschluss in einem späteren).
        """
        if art == "geplant":
            self._geplante_module.append(modul)
        else:
            self._bestandene_module.append(modul)

    # ---- Kennzahlen (fachliche Methoden) ----
    @property
    def geplante_ects(self) -> int:
        """Summe der ECTS aller in diesem Semester geplanten Module."""
        return sum(m.ects for m in self._geplante_module)

    @property
    def erreichte_ects(self) -> int:
        """Summe der ECTS aller bestandenen Module in diesem Semester."""
        return sum(m.ects for m in self._bestandene_module if m.ist_bestanden)

    @property
    def fortschritt(self) -> float:
        """Fortschritt des Semesters (erreichte_ects / geplante_ects)."""
        return (self.erreichte_ects / self.geplante_ects) if self.geplante_ects else 0.0

    # ---- Lesezugriffe ----
    @property
    def nummer(self) -> int:
        return self._nummer

    @property
    def bezeichnung(self) -> str:
        return self._bezeichnung


class Studiengang:
    """Aggregatwurzel für alle studienbezogenen Daten.

    Ein Studiengang fasst alle Semester und Module zusammen. Daraus werden
    globale Kennzahlen wie der Gesamtfortschritt und der gewichtete Notenschnitt
    berechnet.
    """

    def __init__(self, name: str, gesamt_ects: int, regelstudienzeit: int) -> None:
        self._name = name
        self._gesamt_ects = gesamt_ects
        self._regelstudienzeit = regelstudienzeit
        self._semester: List[Semester] = []
        self._module: List[Modul] = []

    # ---- Verwaltung von Unterobjekten ----
    def add_semester(self, sem: Semester) -> None:
        """Fügt dem Studiengang ein Semester hinzu."""
        self._semester.append(sem)

    def add_modul(self, modul: Modul) -> None:
        """Fügt dem Studiengang ein Modul hinzu."""
        self._module.append(modul)

    # ---- Kennzahlen über den gesamten Studiengang ----
    @property
    def ects_bestanden(self) -> int:
        """Summe der ECTS aller bestandenen Module im Studiengang."""
        return sum(m.ects for m in self._module if m.ist_bestanden)

    @property
    def fortschritt(self) -> float:
        """Fortschritt des Studiums (bestandene ECTS / Gesamt-ECTS)."""
        return (self.ects_bestanden / self._gesamt_ects) if self._gesamt_ects else 0.0

    @property
    def durchschnitt(self) -> Optional[float]:
        """Gewichteter Notendurchschnitt über alle Module mit Note.

        Gewichtung erfolgt nach ECTS. Module ohne Note gehen nicht in den
        Durchschnitt ein.
        """
        module_mit_note = [m for m in self._module if m.durchschnitt is not None]
        if not module_mit_note:
            return None
        ges_ects = sum(m.ects for m in module_mit_note)
        if ges_ects == 0:
            return None
        gew_sum = sum((m.durchschnitt or 0) * m.ects for m in module_mit_note)
        return round(gew_sum / ges_ects, 2)

    # ---- Lesezugriffe ----
    @property
    def semester(self) -> List[Semester]:
        """Defensiv kopierte Liste der Semester."""
        return list(self._semester)

    @property
    def module(self) -> List[Modul]:
        """Defensiv kopierte Liste der Module."""
        return list(self._module)

    @property
    def name(self) -> str:
        return self._name
