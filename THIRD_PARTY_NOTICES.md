# Hinweise zu Bibliotheken und Diensten

Das Programm verwendet die folgenden Pakete, die nicht Teil dieses Repositorys sind und bei der Installation über `pip` bezogen werden. Die Angaben zu den Lizenzen entsprechen meinem Kenntnisstand und sollten vor einer Veröffentlichung oder Weitergabe anhand der aktuellen Lizenztexte der Pakete geprüft werden.

| Paket | Zweck | Lizenz (nach Kenntnisstand) |
|---|---|---|
| PySide6 (Qt for Python) | Oberfläche und Fenster | LGPL-3.0 (alternativ GPL oder kommerziell) |
| psutil | Prozessnamen, Akkustand | BSD-3-Clause |
| pycaw | Systemlautstärke | MIT |
| comtypes (von pycaw benötigt) | Windows-COM-Zugriff | MIT |
| winrt-* (pywinrt) | Zugriff auf die Windows-Medienwiedergabe | MIT |

## Hinweis zu PySide6 (LGPL)

Wird nur der Quellcode dieses Projekts weitergegeben und PySide6 vom Nutzer selbst installiert, ergeben sich in der Regel keine zusätzlichen Pflichten. Wird PySide6 dagegen in ein fertiges Programm eingebaut (zum Beispiel als .exe mit PyInstaller), gelten die Bedingungen der LGPL, unter anderem Lizenzhinweise und die Möglichkeit, die Bibliothek auszutauschen. Das sollte in diesem Fall vorher genau geprüft werden.

## Externer Dienst

- **LRCLIB (lrclib.net):** Von der Community betriebener Dienst für synchronisierte Songtexte. Das Programm sendet Titel und Künstler des laufenden Songs an diesen Dienst und zeigt die Antwort an. Die Songtexte selbst gehören nicht zu diesem Projekt und werden nicht mitgeliefert oder gespeichert. Bitte beachte die Regeln des Dienstes.

## Marken

Spotify, Apple Music, Windows und weitere genannte Namen sind Marken ihrer jeweiligen Inhaber. Dieses Projekt ist unabhängig und nicht mit ihnen verbunden.
