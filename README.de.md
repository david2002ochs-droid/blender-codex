# Blender Codex

**Ein KI-Chat direkt in Blender, mit der aktuellen Szene als Kontext.**

Blender Codex ist ein experimentelles Windows-Add-on. Stelle Fragen zu ausgewählten Objekten, fordere Szenenänderungen an und hänge ausdrücklich ein Bild der aktuellen Ansicht an. Der Chat nutzt deine vorhandene Codex-Anmeldung und die offizielle Blender-Lab-MCP-Anbindung.

Entstanden im Rahmen des **[Cursor x Sandbox Hackathon | Stuttgart](https://luma.com/spacexai-tueh)** am **7. November 2026**, organisiert von Sandbox und CREATORS.

[English](README.md) · [Installation](docs/getting-started.md) · [Entwicklung](docs/development.md)

## Funktionen

- Aktuellen Szenenkontext und Objekt- oder Mesh-Auswahl an Codex übergeben.
- Die geöffnete Szene mit den verbundenen Blender-Werkzeugen untersuchen und bearbeiten.
- Beweglicher, skalierbarer Chat mit Streaming, Werkzeugaktivität und lokalem Verlauf.
- Ansichten mit Blender-Annotationen bewusst als Bild anhängen.
- Optional Referenzbilder über Hi3D in ein GLB-Modell umwandeln.

Erster Test: Würfel auswählen und fragen **„Was ist ausgewählt?“** Danach **„Verdopple die Höhe des ausgewählten Würfels; X und Y unverändert lassen.“** Das Ergebnis im Item-Panel prüfen.

## Start

Zielplattform ist **Windows x64**. Das Add-on deklariert Blender **4.2+**; frühere lokale Integrationstests verwendeten **5.2.3 LTS**. Du brauchst außerdem Git, Python 3.10+, eine angemeldete Codex CLI, WebView2 Runtime und zum Bauen des nativen Hosts den .NET-Framework-C#-Compiler.

```powershell
git clone https://github.com/david2002ochs-droid/blender-codex.git
cd blender-codex
pwsh -NoProfile -File scripts/check-prerequisites.ps1
```

Die [Installationsanleitung](docs/getting-started.md) erklärt MCP-Setup, Host-Build und Installation des Add-on-ZIPs. Die Weboberfläche liegt bereits gebaut im Repository; für einen Neubau sind Node.js und pnpm erforderlich.

## Aktueller Stand

Das Projekt ist ein Hackathon-Prototyp. Der Standardmodus **Full Access** erlaubt dem Codex-Kindprozess Datei-, Befehls- und Netzwerkzugriff ohne einzelne Freigaben. Im Chat stehen auch **On Request** und **Read Only** zur Auswahl.

Szenenkontext und ausdrücklich angehängte Bilder gehen an den konfigurierten Codex-Dienst. Der Chatverlauf bleibt lokal. Die optionale [Hi3D-Anbindung](docs/hi3d.md) lädt ausgewählte Bilder zu einem externen Anbieter hoch und kann kostenpflichtige Credits verbrauchen.

Die automatisierten Tests verwenden simulierte Antworten. Vollständige Modellaktionen und echte kostenpflichtige Generierungen sind dadurch nicht belegt. Details: [CURRENT_UI.md](CURRENT_UI.md).

## Mitmachen und Lizenz

[CONTRIBUTING.md](CONTRIBUTING.md) beschreibt Entwicklung und Beiträge. Eigener Projektcode steht unter **GPL-3.0-or-later**. Herkunft und Lizenzen eingebundener Komponenten bleiben erhalten: [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
