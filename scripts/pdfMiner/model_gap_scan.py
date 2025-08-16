#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Model-Gap-Scanner für NSG-PDFs (Schema v1.1)

Zweck
-----
Durchsucht einen Ordner mit NSG-Verordnungen (PDFs) und findet **Kandidaten**,
die im aktuellen Datenmodell v1.1 (Enums/Kataloge) noch **nicht** enthalten sind.

Ausgaben (in --outdir)
----------------------
- candidates_aktivitaet.csv      # unbekannte Aktivitäts-Kandidaten + Häufigkeiten/Beispiele
- candidates_zone.csv            # unbekannte Zonentyp-/Zonenname-Kandidaten
- candidates_dokument_typ.csv    # Hinweise auf Dokumenttypen außerhalb des bekannten Sets
- candidates_ausnahme.csv        # Absatzstellen mit Ausnahmen/Genehmigung/Befreiung
- candidates_ort.csv             # Orts-/Platz-Hinweise außerhalb des bekannten Sets
- candidates_conditions.csv      # extrahierte Zeit-/Abstands-/Mengenkonditionen (Rohdaten)
- audit_report.md                # Kurzbericht mit einfachen Statistiken

Vorgehen (Heuristik)
-------------------
1) Textextraktion je PDF (pdfminer → pypdf → `pdftotext` als Fallback).
2) Segmentierung in Absätze und Erkennung von §-Überschriften.
3) Regex-gestützte Suche nach:
   - Verboten/Erlaubt-Formulierungen → Kandidaten **Aktivitäten** (snake_case-normalisiert)
   - Zonenhinweisen (Altarm, Buhnenfeld, Schutzstreifen, …) → **Zonen**
   - Dokumenttyp-Hinweisen (Befahrensverordnung, Polizeiverordnung, Berichtigung) → **Dokumenttypen**
   - Ausnahmen/Befreiungen/Genehmigungen → **Ausnahme-Marker**
   - Bedingungen (Datumsspannen, Abstände in m, Mengengrenzen) → **Conditions**
4) Abgleich mit den **bekannten Enums** aus Schema v1.1; nur Unbekanntes wird berichtet.

Aufruf
------
python model_gap_scan_de.py --pdfdir ./data/all_pdfs --outdir ./out --limit 0

Hinweise
--------
- Benötigt Python 3.10+. Für bessere Ergebnisse: `pip install pdfminer.six pypdf`
- Der Scanner ist konservativ: Er liefert Vorschläge, **keine** endgültigen Enum-Werte.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple, Dict, Optional

# ------------------------------------
# Bekannte Enums aus NSG-DBML v1.1
# ------------------------------------
KNOWN_DOKUMENT_TYP = {
    "verordnung", "aenderungsverordnung", "ergaenzung", "befahrensverordnung",
    "polizeiverordnung", "berichtigung", "sonstige_verordnung"
}
KNOWN_ZONE_TYP = {
    "gesamtgebiet", "uferzone", "altarm", "buhnenfeld", "gewasserflaeche",
    "schutzstreifen", "waldabteilung", "wiese_acker", "weg_trasse", "ruhezone", "sonstiges"
}
KNOWN_ERLAUBNIS = {
    "erlaubt", "verboten", "nur_mit_behoerdlicher_erlaubnis_erlaubt",
    "nur_mit_grundbesitzererlaubnis_erlaubt", "nicht_empfohlen"
}
KNOWN_ORT = {
    "gesamte_flaeche_des_gebietes", "oeffentlich_gewidmete_strassen_plaetze",
    "ausgewiesene_wege_plaetze", "unbefestigte_land_und_forstwirtschaftliche_wege",
    "pfade", "gewasserflaeche", "uferbereich"
}
KNOWN_KATEGORIE = {
    "bergaktivitaeten", "reitaktivitaeten", "radsportaktivitaeten",
    "motorisierte_aktivitaeten", "laufaktivitaeten", "aufenthaltsaktivitaeten",
    "generelles_verhalten", "luftaktivitaeten", "schneeaktivitaeten",
    "urbane_aktivitaeten", "wasseraktivitaeten", "betretungsverhalten",
    "nutzungs_eingriffs_handlungen"
}
KNOWN_AKTIVITAET = {
    # Freizeit/Verhalten
    "klettern","base_jumping","reiten","bespannte_fahrzeuge","radfahren","kraftfahrzeug",
    "camping_fahrzeug_anhaenger","lagern_biwakieren","feuer","zelten","pflanzen_sammeln",
    "pilze_sammeln","mineralien_fossilien_sammeln","baeume_faellen_oder_verletzen",
    "fotografieren_filmen","laerm_tonband_abspielgeraete","toilettengang","abfall_entsorgen",
    "hunde","hunde_ohne_leine","ballonfahren","drohnen_flugmodelle","panoramafluege",
    "paraglider","segelflieger","ultraleichtflieger","rodeln_schlitten","schneeschuhwandern",
    "ski_und_snowboardfahren","skilanglauf","skitouren","angeln","baden","baden_von_tieren",
    "tauchen","nutzung_von_schwimmhilfe","wasserfahrzeuge_ohne_motor","wasserfahrzeuge_motorisiert",
    "betreten_des_gebietes","betreten_abseits_der_wege","eisklettern","tiere_fuettern","rauchen",
    "luftsport_starten_landen","wintersport","wassersport",
    # NSG-spezifisch
    "bauliche_anlagen_errichten_oder_erweitern","leitungen_verlegen_ueber_unter_erde",
    "einfriedungen_errichten_oder_erweitern","materiallagerplaetze_schrottplaetze_anlegen",
    "abfall_ablegen_verunreinigen","bodengestalt_aendern_abgraben_auffuellen_sprengen_bohren",
    "gewaesser_herstellen_beseitigen_umgestalten_ufer_aendern","aufforstung_erstmalig","waldroden",
    "umwandlung_dauergruenland","duenger_ausbringen","pflanzenbehandlungsmittel_chemische_mittel_verwenden",
    "nichtheimische_arten_einbringen","tiernachstellung_fang_toetung_brutstaetten_stoeren","jagd_ausuebung",
    "fischereiliche_nutzung_fischbesatz","reiten_ausserhalb_ausgewiesener_wege",
    "fahren_parken_ausserhalb_oefentlich_gewidmeter_wege","modellflug_drohnen_betreiben",
    "modellfahrzeuge_betreiben","modellschiffe_betreiben","feuer_anzuenden_unterhalten_grillen",
    "anlegestellen_anglerstege_errichten","segeln_surfen_befahren_ohne_motor","tauchen_mit_ausruestung",
    "bild_oder_schrifttafeln_anbringen","intensive_weidewirtschaft","wildacker_anlegen_oder_unterhalten",
    "wildfuetterungsstellen_anlegen_oder_unterhalten","strassen_und_wege_neu_oder_ausbauen",
    "weihnachtsbaumkultur_anlegen","baumschulkulturen_anlegen","sonderkulturen_anlegen",
    "eissport_auf_gewaessern","geocaching","massensportveranstaltung_durchfuehren"
}

GERMAN_MAP = {
    "ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"
}

def to_snake(s: str) -> str:
    """Einfaches snake_case-Normalisieren für deutschsprachige Phrasen."""
    s = s.strip()
    for k,v in GERMAN_MAP.items():
        s = s.replace(k,v)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_").lower()

# ------------------------------------
# PDF-Text-Extraktion mit Fallbacks
# ------------------------------------

def extract_text_from_pdf(path: Path) -> str:
    """Gibt den extrahierten Text eines PDFs zurück (best effort)."""
    # Erstens: pdfminer
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract
        text = pdfminer_extract(str(path))
        if text and text.strip():
            return text
    except Exception:
        pass
    # Zweitens: pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text and text.strip():
            return text
    except Exception:
        pass
    # Drittens: Systemtool pdftotext
    try:
        result = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return ""

# ------------------------------------
# Muster/Regex für Mining
# ------------------------------------
PROHIBIT_ANCHORS = r"(?:verboten(?:\s+ist|\s+sind)?|ist\s+untersagt|sind\s+untersagt|nicht\s+zul[aä]ssig|nicht\s+erlaubt)"
ALLOW_ANCHORS = r"(?:erlaubt\s+ist|sind\s+erlaubt|zul[aä]ssig\s+ist|zul[aä]ssig\s+sind)"
EXCEPTION_ANCHORS = r"(?:ausgenommen|Ausnahmen|nur\s+mit\s+Genehmigung|mit\s+Zustimmung|Befreiung|Genehmigungspflicht)"
ZONE_HINTS = [
    "Altarm","Buhnen","Buhnenfeld","Uferzone","Schutzstreifen","Kernzone","Ruhezone",
    "Schonbezirk","Laichschonbezirk","Vogelschutzbereich","Rastzone","Sperrzone"
]
DOC_TYPE_HINTS = {
    "befahrensverordnung": ["Befahrensverordnung","Befahren der Gew"],
    "polizeiverordnung": ["Polizeiverordnung","Polizeiliche Verordnung"],
    "berichtigung": ["Berichtigung","berichtig"],
}
# Orts-Hinweise jenseits des Enum-Sets (nur als Kandidaten behandeln)
ORT_HINTS = [
    "Stege", "Wegrainen", "Wege", "Feldwege", "Gewässerrandstreifen", "Uferstreifen",
    "Uferbereiche", "Halden", "Felsen", "Klippen"
]

DATE_RE = re.compile(r"(?:vom|von)\s+(\d{1,2}[\./]\s*[A-Za-zäöüÄÖÜ]+|\d{1,2}[\./]\d{1,2}\.)\s*(?:bis|-|–)\s*(\d{1,2}[\./]\s*[A-Za-zäöüÄÖÜ]+|\d{1,2}[\./]\d{1,2}\.)")
DATE_NUM_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(?:\d{2,4})?")
DIST_RE = re.compile(r"(\d{1,4})\s*(?:m|Meter)\b", re.IGNORECASE)
COUNT_RE = re.compile(r"(max\.?|h[öo]chstens|nicht mehr als)\s*(\d{1,4})\b", re.IGNORECASE)

LIST_ITEM_RE = re.compile(r"^[\s\-–•\*\d\)\.]{0,6}([A-ZÄÖÜa-zäöüß][^\n]{3,120})$")
PARA_SPLIT_RE = re.compile(r"(\n\s*\n|\r\n\r\n)")
PARAGRAPH_HEADER_RE = re.compile(r"^\s*§\s*\d+[^\n]*$")

# ------------------------------------
# Datenstrukturen
# ------------------------------------
@dataclass
class Candidate:
    key: str
    kind: str  # aktivitaet|zone|dokument_typ|ausnahme|ort
    sample: str
    pdf: str
    location: str

# ------------------------------------
# Hilfsfunktionen
# ------------------------------------

def find_pdf_id(name: str) -> str:
    """Extrahiert z. B. "NSG-7100-025" aus dem Dateinamen, sonst Dateistamm."""
    m = re.search(r"(NSG-[0-9]{4}-[0-9]{3})", name, re.IGNORECASE)
    return m.group(1).upper() if m else Path(name).stem


def mine_candidates(text: str, pdf_name: str) -> Tuple[List[Candidate], Dict[str, list]]:
    """Extrahiert Kandidaten und Konditionen aus dem Text eines PDFs."""
    pdf_id = find_pdf_id(pdf_name)
    paras = [p.strip() for p in PARA_SPLIT_RE.split(text) if p and p.strip() and not PARA_SPLIT_RE.fullmatch(p)]
    candidates: List[Candidate] = []
    conditions_rows = []

    # Dokumenttyp-Hinweise (einfacher Wortschatzabgleich)
    low = text.lower()
    for typ, hints in DOC_TYPE_HINTS.items():
        for h in hints:
            if h.lower() in low and typ not in KNOWN_DOKUMENT_TYP:
                candidates.append(Candidate(key=typ, kind="dokument_typ", sample=h, pdf=pdf_id, location="document"))

    # Zonen-Hinweise
    for hint in ZONE_HINTS:
        if re.search(r"\b" + re.escape(hint) + r"\b", text):
            k = to_snake(hint)
            if k not in KNOWN_ZONE_TYP:
                candidates.append(Candidate(key=k, kind="zone", sample=hint, pdf=pdf_id, location="document"))

    # Orts-Hinweise (frei; nur als Kandidaten)
    for hint in ORT_HINTS:
        if re.search(r"\b" + re.escape(hint) + r"\b", text):
            k = to_snake(hint)
            if k not in KNOWN_ORT:
                candidates.append(Candidate(key=k, kind="ort", sample=hint, pdf=pdf_id, location="document"))

    # Absatzweises Mining
    current_para_title = None
    for raw in paras:
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if not lines:
            continue
        if PARAGRAPH_HEADER_RE.match(lines[0]):
            current_para_title = lines[0]
        para_text = " ".join(lines)

        # Aktivitäten aus Listenzeilen (oft Verbots-/Erlaubnislisten)
        for ln in lines:
            if LIST_ITEM_RE.match(ln):
                if re.search(PROHIBIT_ANCHORS + "|" + ALLOW_ANCHORS, ln, re.IGNORECASE):
                    # Aufzählungszeichen/Nummer am Anfang entfernen
                    cleaned = re.sub(r"^[\-–•\*\d\)\.\s]+", "", ln)
                    # Versuch: Nominalphrase hinter Füllwörtern herauslösen
                    m = re.search(r"(?:das|die|der|von|mit|auf|in)\s+(.+)$", cleaned)
                    phrase = m.group(1) if m else cleaned
                    key = to_snake(phrase)[:80]
                    if key and key not in KNOWN_AKTIVITAET and len(key) >= 3:
                        candidates.append(Candidate(key=key, kind="aktivitaet", sample=cleaned[:160], pdf=pdf_id, location=current_para_title or "liste"))
                else:
                    # Heuristik: reine Stichworte als mögliche Aktivität
                    phrase = re.sub(r"^[\-–•\*\d\)\.\s]+", "", ln)
                    key = to_snake(phrase)[:80]
                    if key and key not in KNOWN_AKTIVITAET and len(key) >= 3 and len(phrase.split()) <= 8:
                        candidates.append(Candidate(key=key, kind="aktivitaet", sample=ln[:160], pdf=pdf_id, location=current_para_title or "liste"))

        # Aktivitäten in Fließtext mit Ankern (verboten/erlaubt/zulaessig)
        for m in re.finditer(rf"({PROHIBIT_ANCHORS}|{ALLOW_ANCHORS}).{{0,140}}", para_text, flags=re.IGNORECASE):
            span = para_text[m.start(): m.end()]
            after = para_text[m.end(): m.end()+120]
            m2 = re.search(r"(?:das|die|der|mit|durch|auf|in|am|vom|von)\s+([^\.;:,\n]{3,80})", after)
            if m2:
                phrase = m2.group(1)
                key = to_snake(phrase)[:80]
                if key and key not in KNOWN_AKTIVITAET and len(key) >= 3:
                    candidates.append(Candidate(key=key, kind="aktivitaet", sample=(span + " … " + phrase)[:160], pdf=pdf_id, location=current_para_title or "inline"))

        # Ausnahmen/Befreiungen/Genehmigungen markieren (für manuelle Sichtung)
        if re.search(EXCEPTION_ANCHORS, para_text, re.IGNORECASE):
            excerpt = para_text[:200]
            candidates.append(Candidate(key="exception_marker", kind="ausnahme", sample=excerpt, pdf=pdf_id, location=current_para_title or "absatz"))

        # Bedingungen extrahieren (Rohdaten für spätere Strukturierung)
        for m in DATE_RE.finditer(para_text):
            conditions_rows.append({
                "pdf": pdf_id,
                "where": current_para_title or "absatz",
                "type": "date_span",
                "text": m.group(0)
            })
        for m in DIST_RE.finditer(para_text):
            conditions_rows.append({
                "pdf": pdf_id,
                "where": current_para_title or "absatz",
                "type": "distance_m",
                "value": m.group(1),
                "text": m.group(0)
            })
        for m in COUNT_RE.finditer(para_text):
            conditions_rows.append({
                "pdf": pdf_id,
                "where": current_para_title or "absatz",
                "type": "count_limit",
                "value": m.group(2),
                "text": m.group(0)
            })

    return candidates, {"conditions": conditions_rows}

# ------------------------------------
# CLI / Hauptprogramm
# ------------------------------------

def write_csv(path: Path, rows: List[Dict[str, str]], header: List[str]):
    """Hilfsfunktion zum Schreiben einfacher CSV-Dateien."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfdir", required=True, help="Ordner mit PDFs (rekursiv)")
    ap.add_argument("--outdir", required=True, help="Ausgabeordner für CSV/MD")
    ap.add_argument("--limit", type=int, default=0, help="Erste N PDFs verarbeiten (0 = alle)")
    args = ap.parse_args()

    pdf_paths = sorted([p for p in Path(args.pdfdir).rglob("*.pdf")])
    if args.limit > 0:
        pdf_paths = pdf_paths[:args.limit]
    if not pdf_paths:
        print("Keine PDFs gefunden.")
        return

    all_candidates: List[Candidate] = []
    cond_rows_all: List[Dict[str, str]] = []
    per_file_stats = []

    for i, pdf in enumerate(pdf_paths, 1):
        try:
            text = extract_text_from_pdf(pdf)
        except Exception:
            text = ""
        cand, extra = mine_candidates(text or "", pdf.name)
        all_candidates.extend(cand)
        cond_rows_all.extend(extra["conditions"]) if extra else None

        per_file_stats.append({
            "pdf": pdf.name,
            "pdf_id": find_pdf_id(pdf.name),
            "chars": len(text or ""),
            "candidates": len(cand),
            "conditions": len(extra.get("conditions", [])) if extra else 0,
        })
        if i % 20 == 0:
            print(f"Verarbeitet: {i}/{len(pdf_paths)} PDFs…")

    # Aggregation nach (Art, Schlüssel)
    buckets: Dict[Tuple[str,str], List[Candidate]] = defaultdict(list)
    for c in all_candidates:
        buckets[(c.kind, c.key)].append(c)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # CSV-Zeilen je Kategorie
    def rows_for(kind: str) -> List[Dict[str, str]]:
        rows = []
        for (knd, key), lst in sorted(buckets.items()):
            if knd != kind:
                continue
            cnt = len(lst)
            pdfs = sorted({c.pdf for c in lst})
            ex = lst[0].sample
            loc = lst[0].location
            rows.append({
                "key": key,
                "count": str(cnt),
                "pdf_count": str(len(pdfs)),
                "example": ex,
                "first_pdf": pdfs[0] if pdfs else "",
                "first_location": loc,
                "pdfs": ",".join(pdfs[:20]) + ("…" if len(pdfs) > 20 else "")
            })
        return rows

    write_csv(outdir/"candidates_aktivitaet.csv", rows_for("aktivitaet"),
              ["key","count","pdf_count","example","first_pdf","first_location","pdfs"])
    write_csv(outdir/"candidates_zone.csv", rows_for("zone"),
              ["key","count","pdf_count","example","first_pdf","first_location","pdfs"])
    write_csv(outdir/"candidates_dokument_typ.csv", rows_for("dokument_typ"),
              ["key","count","pdf_count","example","first_pdf","first_location","pdfs"])
    write_csv(outdir/"candidates_ausnahme.csv", rows_for("ausnahme"),
              ["key","count","pdf_count","example","first_pdf","first_location","pdfs"])
    write_csv(outdir/"candidates_ort.csv", rows_for("ort"),
              ["key","count","pdf_count","example","first_pdf","first_location","pdfs"])

    # Rohkonditionen
    write_csv(outdir/"candidates_conditions.csv", cond_rows_all,
              ["pdf","where","type","value","text"])

    # Bericht
    total = sum(x["candidates"] for x in per_file_stats)
    with (outdir/"audit_report.md").open("w", encoding="utf-8") as f:
        f.write(f"# Bericht Model-Gap-Scan\n\n")
        f.write(f"Gescannt: {len(pdf_paths)} PDFs\n\n")
        f.write(f"Gesamtzahl Kandidaten-Hits: {total}\n\n")
        f.write("## Dateiliste (Top 50)\n\n")
        for row in per_file_stats[:50]:
            f.write(f"- {row['pdf']} (Zeichen={row['chars']}, Kandidaten={row['candidates']}, Konditionen={row['conditions']})\n")
        f.write("\n## Nächste Schritte\n\n")
        f.write("1. CSVs sichten; entscheiden, welche Schlüssel offizielle Enum-/Katalogeinträge werden.\n")
        f.write("2. Akzeptierte Schlüssel ins Schema (NSG.dbml) und in enums/*.csv aufnehmen.\n")
        f.write("3. Scan erneut ausführen, bis kaum neue Kandidaten erscheinen.\n")

    print(f"Fertig. Ergebnisse in: {outdir}")


if __name__ == "__main__":
    main()
