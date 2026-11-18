# Lokaler Test-Recorder

Unter Windows mit Node.js im PATH aus dem Projektordner starten. `RECORDER_NODE` kann auf eine lokale Node.js-Installation zeigen.

```powershell
& './tools/screen-recorder/start.ps1'
```

1. **Fenster / Bildschirm wählen**: Im Browserdialog Blender oder einen Bildschirm auswählen und freigeben.
2. **Start**: Erst „AUFNAHME LÄUFT“ und der Timer bestätigen die Aufnahme.
3. **Stopp & speichern**: Das WebM wird heruntergeladen. Der Speichern-Link bleibt zusätzlich verfügbar.

Ohne Ton; kein Upload. Der lokale Server liefert nur die Seite und hat keinen Zugriff auf die Videodaten. Die Aufnahme liegt bis zum Download im Browser-Arbeitsspeicher; Seite geöffnet lassen. Bei 512 MB oder 30 Minuten wird gestoppt. Browser-/Betriebssystemfreigaben bleiben erforderlich. Test-Recorder ist unabhängig vom Blender-Plugin und verändert dessen laufende Instanz nicht.

Die Live-Vorschau nach der Quellenwahl ist noch keine Aufnahme. Für eine weitere Aufnahme erneut die Quelle wählen. Chrome oder Edge empfohlen; bei fehlender/gesperrter Bildschirmfreigabe wird der Browserfehler angezeigt.

Implementierungsgrundlage: [Screen Capture](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia), [MediaRecorder](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder).
