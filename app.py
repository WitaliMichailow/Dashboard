# app.py
"""Streamlit-Frontend für das Studien-Dashboard.

Diese Datei bildet die Präsentationsschicht der Anwendung. Die UI ruft ausschließlich
Funktionen aus dem ``repo``-Modul auf und greift nicht direkt auf die Datenbank zu.
Dadurch bleibt die Oberfläche schlank und die Geschäftslogik zentral gebündelt.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from db import init_if_needed
from models import Pruefungsform
import repo


# Grundlegende Konfiguration der Streamlit-App (Titel & Layout)
st.set_page_config(page_title="Studien-Dashboard", layout="wide")

# Initialisiert bei Bedarf die Datenbank (Tabellen + Default-Studiengang/Semester)
init_if_needed()

# Navigation in der Seitenleiste
st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Zu Seite wechseln:",
    ["Dashboard", "Daten eingeben", "Daten bearbeiten/löschen", ]
)

# ---------------------- DASHBOARD ----------------------
# Übersichtsseite mit KPIs, Diagrammen und Tabellen
if page == "Dashboard":
    # Gesamten Studiengang (mit Semestern, Modulen, Leistungen) aus der DB laden
    sg = repo.load_domain()

    st.title("Dashboard")

    # Obere Reihe: Studienfortschritt gesamt + Zeitplan pro Semester
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Studienfortschritt gesamt")
        # Anteil bestandener ECTS an Gesamt-ECTS in Prozent
        fortschritt = round(sg.fortschritt * 100, 1)
        st.metric("Abgeschlossen", f"{fortschritt} %", help="Anteil bestandener ECTS an Gesamt-ECTS")
        # Fortschrittsbalken (0.0–1.0)
        st.progress(min(1.0, sg.fortschritt))

    with col2:
        st.subheader("Zeitplan pro Semester (ECTS)")

        # Ziel-ECTS pro Semester (Planwert)
        ZIEL_PRO_SEMESTER = 25

        # Datenstruktur für das gestapelte Balkendiagramm aufbauen
        daten = []
        for sem in sg.semester:
            erreicht = sem.erreichte_ects
            # "abgeschlossen" kann maximal so groß wie das Ziel sein
            abgeschlossen = min(ZIEL_PRO_SEMESTER, erreicht)
            # "offen" = was bis zum Ziel noch fehlt (nicht negativ werden lassen)
            offen = max(0, ZIEL_PRO_SEMESTER - abgeschlossen)

            daten.append({
                "Semester": sem.nummer,
                "Typ": "bestanden",
                "ECTS": abgeschlossen,
            })
            daten.append({
                "Semester": sem.nummer,
                "Typ": "offen",
                "ECTS": offen,
            })

        # Diagramm: gestapelte Balken pro Semester (bestanden vs. offen)
        df_sem = pd.DataFrame(daten)
        fig_sem = px.bar(
            df_sem,
            x="Semester",
            y="ECTS",
            color="Typ",
            barmode="stack",
            height=320,
            range_y=[0, ZIEL_PRO_SEMESTER],
        )
        st.plotly_chart(fig_sem, use_container_width=True)

    # Untere Reihe: Notenübersicht + Modulstatus
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Notenübersicht und Durchschnitt")
        avg = sg.durchschnitt
        # Gewichteter Notenschnitt über alle Module (gewichtet nach ECTS)
        st.metric("Aktueller Notenschnitt", f"{avg:.2f}" if avg is not None else "—", help="Gewichteter Schnitt über Module (ECTS)")
        # Einzelne Modul-Durchschnitte als Balkendiagramm
        rows = []
        for m in sg.module:
            if m.durchschnitt is not None:
                rows.append({"Modul": m.name, "Durchschnitt": m.durchschnitt})
        if rows:
            df_grades = pd.DataFrame(rows)
            fig_gr = px.bar(df_grades, x="Modul", y="Durchschnitt", range_y=[1,5], height=320)
            # Ziel-Linie bei 2,0 (Notenziel)
            fig_gr.add_hline(y=2.0, line_dash="dash", line_color="red", annotation_text="Ziel 2,0")
            st.plotly_chart(fig_gr, use_container_width=True)
        else:
            st.info("Noch keine benoteten Module vorhanden.")

    with col4:
        st.subheader("Modulstatus")
        # Übersicht aller Module mit Status und Prüfungsform
        rows = []
        for m in sg.module:
            rows.append({
                "Modul": m.name,
                "Kürzel": m.kuerzel,
                "ECTS": m.ects,
                "Prüfungsform": m.pruefungsform.value,
                "Durchschnitt": m.durchschnitt,
                "Status": m.status
            })
        df_mod = pd.DataFrame(rows)
        st.dataframe(df_mod, use_container_width=True, hide_index=True)

# ---------------------- EINGABE ----------------------
# Seite zum Erfassen neuer Daten (Create-Operationen)
elif page == "Daten eingeben":
    st.title("Daten eingeben")
    st.caption("Erfasse Module, Prüfungsleistungen und Belegungen über Formulare.")

    # --- Modul anlegen ------------------------------------------------------
    with st.expander("Modul anlegen"):
        name = st.text_input("Modulname")
        kuerzel = st.text_input("Kürzel", placeholder="z. B. DLBDSOOFPP01_D")
        ects = st.number_input("ECTS", min_value=1, max_value=30, step=1, value=5)
        # Auswahl aus allen Enum-Werten von Pruefungsform
        pruefungsform = st.selectbox("Prüfungsform", [p for p in Pruefungsform])
        if st.button("Modul speichern"):
            if name and kuerzel:
                # Modul in der Datenbank anlegen
                repo.create_modul(name, kuerzel, int(ects), pruefungsform)
                st.success(f"Modul '{name}' gespeichert.")
            else:
                st.error("Bitte Name und Kürzel angeben.")

    # --- Prüfungsleistung hinzufügen ---------------------------------------
    with st.expander("Prüfungsleistung hinzufügen"):
        module = repo.list_module()
        if module:
            # Auswahl eines Moduls per Kürzel
            mod_kz = st.selectbox("Modul (Kürzel)", [m["kuerzel"] for m in module], key="pl_add_mod_kz")

            bezeichnung = st.text_input("Bezeichnung", placeholder="z. B. Klausur")
            datum = st.date_input("Datum", value=None)
            datum_str = datum.isoformat() if datum else None
            # Note kann gesetzt oder über Checkbox bewusst leer gelassen werden
            note = st.number_input("Note (1.0 - 5.0, leer möglich)", min_value=1.0, max_value=5.0, step=0.1, value=2.3)
            note_leer = st.checkbox("Note leer lassen (noch nicht bewertet)", value=False)
            versuch = st.number_input("Versuch-Nr.", min_value=1, max_value=10, step=1, value=1)
            if st.button("Leistung speichern"):
                repo.create_pruefungsleistung(mod_kz, bezeichnung, datum_str, None if note_leer else float(note), int(versuch))
                st.success("Prüfungsleistung gespeichert.")
        else:
            st.info("Bitte zuerst mindestens ein Modul anlegen.")

    # --- Belegung (Semester ↔ Modul) festlegen -----------------------------
    with st.expander("Belegung (Modul ↔ Semester) festlegen"):
        module = repo.list_module()
        sem_nrn = repo.list_semester_nrn()
        if module and sem_nrn:

            mod_kz2 = st.selectbox("Modul (Kürzel)", [m["kuerzel"] for m in module], key="belegung_mod_eingeben")
            sem_nr = st.selectbox("Semester-Nr.", sem_nrn, key="belegung_sem_eingeben")
            # „bestanden“ wird intern als art="aktuell" gespeichert
            art_anzeige = st.selectbox("Art", ["geplant", "bestanden"], key="belegung_art_eingeben")
            kommentar = st.text_input("Kommentar", placeholder="optional", key="belegung_kommentar_eingeben")

            if st.button("Belegung speichern", key="belegung_save_eingeben"):
                art_db = "aktuell" if art_anzeige == "bestanden" else "geplant"
                repo.create_belegung(int(sem_nr), mod_kz2, art_db, kommentar)
                st.success("Belegung gespeichert.")
        else:
            st.info("Es fehlen Module oder Semester.")

# -------- Modul bearbeiten/löschen --------
# Seite zum Aktualisieren und Löschen vorhandener Daten
elif page == "Daten bearbeiten/löschen":
    st.title("Daten bearbeiten oder löschen")

    # --- Module bearbeiten/löschen -----------------------------------------
    st.subheader("Modul bearbeiten / löschen")
    mods = repo.list_module()
    if not mods:
        st.info("Noch keine Module vorhanden.")
    else:
        kz = st.selectbox("Modul (Kürzel) auswählen", [m["kuerzel"] for m in mods])
        if kz:
            # Details zum ausgewählten Modul laden
            m = repo.get_modul(kz)
            colL, colR = st.columns(2)
            with colL:
                new_name = st.text_input("Name", value=m["name"])
                new_kz = st.text_input("Kürzel", value=m["kuerzel"])
            with colR:
                new_ects = st.number_input("ECTS", min_value=1, max_value=30, step=1, value=int(m["ects"]))
                pf_list = [p for p in Pruefungsform]
                idx = [p.name for p in pf_list].index(m["pruefungsform"])
                new_pf = st.selectbox("Prüfungsform", pf_list, index=idx)

            c1, c2 = st.columns(2)
            with c1:
                if st.button("Modul aktualisieren"):
                    # Modul-Stammdaten in der DB aktualisieren
                    repo.update_modul(
                        kz,
                        name=new_name,
                        new_kuerzel=new_kz,
                        ects=int(new_ects),
                        pruefungsform=new_pf
                    )
                    st.success("Modul aktualisiert.")
                    st.experimental_rerun()
            with c2:
                if st.button("Modul löschen", type="primary"):
                    # Löscht Modul inkl. abhängiger Leistungen/Belegungen (ON DELETE CASCADE)
                    repo.delete_modul(kz)
                    st.success("Modul (inkl. Leistungen/Belegungen) gelöscht.")
                    st.experimental_rerun()

    st.markdown("---")

    # -------- Prüfungsleistung bearbeiten/löschen --------
    st.subheader("Prüfungsleistung bearbeiten / löschen")
    mods = repo.list_module()
    if mods:
        kz2 = st.selectbox("Modul (Kürzel) für Leistungen", [m["kuerzel"] for m in mods], key="pl_mod_kz")
        pls = repo.list_pruefungsleistungen(kz2)
        if pls:
            # Lesbare Darstellung für die Auswahlbox zusammensetzen
            label_map = {f"{pl['id']}: {pl['bezeichnung']} | {pl['datum']} | Note={pl['note']} | V{pl['versuch_nr']}": pl for pl in pls}
            sel_label = st.selectbox("Leistung wählen", list(label_map.keys()))
            pl = label_map[sel_label]

            colA, colB, colC = st.columns(3)
            with colA:
                new_bez = st.text_input("Bezeichnung", value=pl["bezeichnung"])
                new_vers = st.number_input("Versuch-Nr.", min_value=1, max_value=10, step=1, value=int(pl["versuch_nr"]))
            with colB:
                # Datum kann optional geleert werden (über Checkbox weiter unten)
                new_date = st.date_input("Datum (leer möglich)", value=pd.to_datetime(pl["datum"]).date() if pl["datum"] else None)
                date_str = new_date.isoformat() if new_date else None
            with colC:
                note_leer = st.checkbox("Note leeren (NULL)", value=(pl["note"] is None))
                new_note = None if note_leer else st.number_input("Note (1.0–5.0)", min_value=1.0, max_value=5.0, step=0.1, value=float(pl["note"]) if pl["note"] is not None else 2.3)

            c3, c4 = st.columns(2)
            with c3:
                if st.button("Leistung aktualisieren"):
                    # Update der ausgewählten Prüfungsleistung in der DB
                    repo.update_pruefungsleistung(
                        pl["id"],
                        bezeichnung=new_bez,
                        datum=date_str,
                        note=new_note,
                        versuch_nr=int(new_vers)
                    )
                    st.success("Prüfungsleistung aktualisiert.")
                    st.experimental_rerun()
            with c4:
                if st.button("Leistung löschen", type="primary"):
                    repo.delete_pruefungsleistung(pl["id"])
                    st.success("Prüfungsleistung gelöscht.")
                    st.experimental_rerun()
        else:
            st.info("Dieses Modul hat noch keine Prüfungsleistungen.")
    else:
        st.info("Noch keine Module vorhanden.")

    st.markdown("---")

    # -------- Belegung bearbeiten/löschen --------
    with st.expander("Belegung (Modul ↔ Semester) festlegen"):
        module = repo.list_module()
        sem_nrn = repo.list_semester_nrn()
        if module and sem_nrn:
            mod_kz2 = st.selectbox(
                "Modul (Kürzel)",
                [m["kuerzel"] for m in module],
                key="belegung_modul",
            )
            sem_nr = st.selectbox(
                "Semester-Nr.",
                sem_nrn,
                key="belegung_semester",
            )

            # Anzeige-Wert ("geplant"/"bestanden"), intern als "geplant"/"aktuell" gespeichert
            art_anzeige = st.selectbox(
                "Art",
                ["geplant", "bestanden"],
                key="belegung_art",
            )
            kommentar = st.text_input(
                "Kommentar",
                placeholder="optional",
                key="belegung_kommentar",
            )

            if st.button("Belegung speichern"):
                art_db = "aktuell" if art_anzeige == "bestanden" else "geplant"
                repo.create_belegung(int(sem_nr), mod_kz2, art_db, kommentar)
                st.success("Belegung gespeichert.")
        else:
            st.info("Es fehlen Module oder Semester.")
