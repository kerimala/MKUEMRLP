# Allgemeine Dokumentation

## Dies ist eine allgemeine Dokumentation die weder strukturiert ist noch eine finale Version der Dokumentation darstellt. Sie dient lediglich zur groben dokumentation meiner gedanklichen und exekutiven Schritte.

### 1. PDFs Downloaden

Da ich die PDF Dateien aller Naturschutzgebiete benötige und mir aktuell nur eine als Beispiel vorliegt muss ich von der Plattform [LANIS](https://geodaten.naturschutz.rlp.de/kartendienste_naturschutz/index.php) alle benötigten PDF Dateien runterladen. Dafür habe ich Anthropics Claude Code mit Claude Sonnet 4 ein Python Skript schreiben lassen um mir alle 526 Dateien automatisch runterzuladen. 

1. [LANIS](https://geodaten.naturschutz.rlp.de/kartendienste_naturschutz/index.php) zur Verfügung gestellte Excel Datei mit allen Natutschutzgebieten untersucht. 

2. Alle Links zu den PDF der Rechtsverordnungen in der Spalte Rechtsverordnungen gefunden, innerhalb eines HTML tags. 

3. Das Skript geht durch diese Links. Durch Regex extrahiert tatsächliche Links aus dem HTML Tags und lädt die PDF Dateien in einen im Code festgelegten Ordner runter.

Das Script befindet sich in diesem Git Repository inkl. Anleitung hier: [PDF Script](scripts/linkDownloadScript)

### 2. Datenmodell extrahieren

Da ich das Datenmodell was von Digitize the Planet zur Verfügung gestellt wurde erweitern soll und mir nur eine PDF vorliegt werde ich das Datenmodell zunächst in ein tatsächliches Datenbankschema extrahieren.

Wenn in den folgenden Schritten ChatGPT erwähnt wird, ist damit ChatGPT 5 Thinking gemeint. Dies ist nach aktuellem Stand (16.08.2025) nur im Pro Abonement verwendbar. 

Extrahiert habe ich das alte Datenmodell von Digitize The Planet, mithilfe von ChatGPT, indem ich die alte PDF zur Verfügung  gestellt habe inkl. 2 Screenshots der PDF. Dann habe ich ChatGPT angewiesen mir das in ein DBML Format zu wandeln, um es in [dbdiagram.io](dbdiagram.io) einfügen zu können.

Das extrahierte originale Datenmodell von Digitize the Planet als DBML und PDF befindet sich hier: [Datenmodelle Digitize the Planet](datenmodelle/digitizeThePlanet/)

Als nächstes habe ich ChatGPT Stichprobenartig einige PDF Dateien der Rechtsschutzverordnungen der Naturschutzgebiete zur Verfügung gestellt. 
Dadurch konnte ChatGPT bereits ein erstes erweitertes Datenmodell erstellen.
Dies bietet nun die Grundlage für alle weitere Versionen und das weitere Vorgehen.

- [Version 1](datenmodelle/nsgVersionen/NSGv1.dbml)

Als nächstes habe ich ChatGPT stichprobenartig 6 weitere PDF Dateien gegeben und es gebeten die aktuelle Version abzugleichen und zu sehen ob es Erweiterung gibt. 
Das hat mir gezeigt ob die bereits existierende Struktur schon genügt oder ob es nötig ist alle 526 Dateien durchzugehen und so alle Felder zu extrahieren. 
Wie zu erwarten fanden sich schnell erweiterungen. Hier die neue Version die ChatGPT nach den 6 Dateien erstellt hat:

- [Version 1.1](datenmodelle/nsgVersionen/NSGv1.1.dbml)



Also ist klar, ich muss ein Skript erstellen welches alle 526 Dateien durchläuft, um so ein sicheres Datenmodell erstellen zu können. Dies habe ich erneut mit Hilfe von ChatGPT 5 Thinking und Claude Code Sonnet 4 erstellt.




