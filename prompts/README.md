# Blender-Agent: aktive Plugin-Anweisungen

Die einzige Laufzeitquelle ist `blender_codex/instructions.txt`. `CodexClient` liest sie beim Laden und übergibt sie bei `thread/start` ausschließlich als `developerInstructions` des Plugin-Chats. Das installierbare ZIP enthält dieselbe Datei. Die normale Codex-Konfiguration und grundlegenden Codex-Anweisungen werden nicht überschrieben. Für eine bereits laufende Verbindung muss ein neuer Chat gestartet werden, damit der neue Text gilt.

Die Struktur ist aus dem lokalen Deepblick-/DSH-Excel-Kern abgeleitet; die Blender-Anweisungen sind neu formuliert. Gelesen wurden `excel/guidance/core/instructions.md` aus dem vorhandenen Checkout `.deepblick-github-b35b204` sowie `excel/skill-guidance.mjs` und `excel/persona.mjs` im lokalen `deepseek-excel-harness`. Dies ist ein Abgleich mit der vorhandenen lokalen Vorlage, keine Behauptung über ihren neuesten Remote-Stand.

| Excel-/VBA-Prinzip | Blender-Umsetzung |
|---|---|
| Native flexible Ausführung über `execute_office_js` | `execute_blender_code(code)` mit bpy/bmesh/mathutils |
| Aktuelle Arbeitsmappe und erfasste Auswahl | Aktueller Prozess, Datei, Objekt-/Mesh-Auswahl |
| Zusammengehörige Operationen bündeln | Ein Code-Aufruf, solange keine Zwischenentscheidung nötig ist |
| Keine zusätzlichen Prüfungen nur für den Abschlussbericht | Vorhandene Ausführungsergebnisse nutzen; gezielt nachlesen oder ansehen |
| Fehler können Teiländerungen hinterlassen | Tatsächlichen Zustand prüfen; unsichere Mutation nicht blind wiederholen |
| Konkreter Ausführungsvertrag | Explizite Imports, frischer Namensraum, `result` als JSON-Dictionary |

`execute_blender_code` bleibt das zentrale flexible Werkzeug. Es werden keine eigenen Spezialtools für Transformationen, Materialien oder Importe eingeführt. Vorhandene offizielle Screenshot-, Dokumentations- und Übersichts-Tools bleiben verfügbar. Der Prompt schreibt keine feste Folge solcher Tools vor und erzeugt keine neue Tool-Suche. Allgemeine Codex-Werkzeuge werden nicht global verändert.

Die CLI-Varianten laufen in einer separaten Blender-Instanz. Der geprüfte offizielle Server kann dabei eine schmutzige offene Datei in eine temporäre Kopie synchronisieren. Deshalb darf der Prompt nicht pauschal behaupten, dass diese Varianten niemals ungespeicherte Daten sehen. Sie ändern jedoch nicht automatisch die sichtbare Szene und können zusätzliche Dateischreibvorgänge verursachen. Sie sind ausdrücklich passenden Offline-Aufgaben vorbehalten.

Geprüfter offizieller Quellstand: `dbbf836ad4b1025f14a2b3b504c43903f39e0b04`. Maßgeblich sind insbesondere `mcp/blmcp/tools/execute_blender_code.py`, `addon/blender_mcp_addon/mcp_to_blender_server.py` und `mcp/blmcp/tools_helpers/blender_cli.py`.

Prüfung: Der Transporttest beobachtet die tatsächlichen Parameter von `thread/start` und stellt sicher, dass Szenendaten als Turn-Kontext getrennt bleiben. Der optionale `tests/smoke_prompt_blender.py` führt das Python-Beispiel aus dem Prompt über den offiziellen Executor in einer frischen Blender-Testszene aus. Dies prüft den Ausführungsvertrag, nicht die Modellqualität über alle kreativen Aufgaben.

Quellen: [Blender Lab MCP](https://www.blender.org/lab/mcp-server/), [offizieller Quellcode](https://projects.blender.org/lab/blender_mcp), [Codex App Server](https://learn.chatgpt.com/docs/app-server). Das Feld `developerInstructions` wurde zusätzlich gegen das lokale App-Server-Protokoll und die Transporttests geprüft.
