Lumina-Beta

# Windows Notch

A notch for Windows: a small pill at the top edge of the screen that expands when you hover over it with your mouse. It displays music with album art and lyrics, features a shelf for dropping files, a clipboard history, tasks, a Pomodoro timer, a water reminder, and a customizable mascot.

> **Note:** This is an independent hobby project. It is not affiliated with Spotify, Apple, Microsoft, or any other companies whose products are mentioned here.

## Features

* **Music:** Album art, title, artist, progress bar (drag to scrub), previous, play/pause, and next controls, plus a volume slider. Works with media players that register with Windows media playback (such as Spotify, Apple Music, or web browsers).
* **Lyrics:** Line-by-line synced, smooth scrolling, even in the collapsed pill. Adjustable time offset.
* **Shelf:** Drag and drop files onto the notch, drag them back out later, or open them with a double-click.
* **Clipboard:** History of recently copied texts (stored in RAM only; password managers are skipped).
* **Today:** Weekly bar and to-do list.
* **Pomodoro:** Focus, short break, and long break modes with customizable durations.
* **Water:** Daily goal, bottle size, and reminders spaced throughout the day.
* **HUD:** Brief pop-up indicators inside the pill for volume, Caps Lock, input language, and battery status.
* **Appearance:** Classic (docked to the edge with curved transitions) or Floating, optional glass effect, size presets, and hover or click to open.
* **Mascot:** Customizable color, eye shape, eye color, size, eye spacing, blinking, cheeks, and smile.
* **Additional Options:** Multi-monitor support, auto-hide in specific apps and fullscreen mode, and launch at Windows startup.

## Requirements

* Windows 10 or 11
* Python 3.10 or newer

## Installation

```bash
pip install -r requirements.txt
```

## Usage

Run the application:

```bash
python notch.py
```

Run in the background without a console window:

```bash
pythonw notch.py
```

**To quit:** Right-click the icon in the taskbar notification area (system tray) and select **Exit** (*Beenden*).

**Desktop Shortcut:** Using the `Verknuepfung_erstellen.bat` file (located next to the program), you can create a desktop shortcut with an icon that launches without a console window.

## Settings

Clicking the gear icon in the player or selecting **Settings** (*Einstellungen*) in the tray menu opens the settings directly inside the notch. Everything is saved in `%APPDATA%\MeineNotch\config.json`.

## Data and Privacy

* To fetch lyrics, the **title and artist** of the currently playing song are sent to the [LRCLIB](https://lrclib.net) service. No other data leaves your computer.
* Settings, the shelf (file paths only), tasks, and water progress are stored locally in `config.json`.
* Clipboard history is not saved to disk.
* Errors are logged in `%APPDATA%\MeineNotch\error.log`, if this feature is included in your version.

## Known Limitations

* Windows notifications are not displayed.
* Fullscreen auto-hide detects windows that fill the entire monitor. If the taskbar is set to auto-hide, a maximized window may be falsely detected as fullscreen.
* Lyrics are only available if they exist on LRCLIB.
* The software is provided without warranty (see license).

## License

MIT License, see [LICENSE](LICENSE). Notices regarding third-party libraries used can be found in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
