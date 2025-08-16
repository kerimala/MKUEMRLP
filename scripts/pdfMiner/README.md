# Model-Gap-Scanner für NSG-PDFs (Schema v1.1)

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
