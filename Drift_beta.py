"""
Meine Notch v6 - Notch für Windows (Musik, Songtexte, Shelf, Zwischenablage, Aufgaben,
Pomodoro, Wasser, Maskottchen)

Neu in v6:
  - Maskottchen-Editor (Farbe, Augenform, Augenfarbe, Größe, Wangen, Lächeln ...)
  - Seiten Pomodoro und Wasser, Erinnerungstöne
  - HUD in der Pille: Lautstärke, Caps Lock, Eingabesprache, Akku
  - Einstellungen: Größe, Öffnen per Klick, Animationsgeschwindigkeit, Datum neben der Uhr,
    Ring (Sekunden/Wasser/Aufgaben), Ausblenden im Vollbild, Zwischenablage-Limit

Neu in v5:
  - Klassische Notch mit kleinen geschwungenen Rundungen am Bildschirmrand
  - Songtexte scrollen weich (Federn) statt abrupt zu wechseln, Text in der Pille blendet über
  - Seiten "Heute" und "Shelf" haben mehr Platz
  - Einstellung "Songtext früher anzeigen" (Aus / 0,3 s / 0,6 s / 1 s)

Einmalig installieren (Eingabeaufforderung):
  pip install PySide6 psutil pycaw winrt-runtime winrt-Windows.Media winrt-Windows.Media.Control winrt-Windows.Storage.Streams winrt-Windows.Foundation winrt-Windows.Foundation.Collections

Starten:
  python notch_v6.py        (mit Konsole, zum Fehler suchen)
  pythonw notch_v6.py       (ohne Konsole, nur im Hintergrund)

Bedienung:
  - Maus auf die Notch: sie klappt auf
  - Pfeile links/rechts: zwischen Player, Shelf und Heute wechseln
  - Datei auf die Notch ziehen: landet im Shelf (wieder herausziehen oder Doppelklick zum Öffnen)
  - Sprechblase: Songtexte, Zahnrad: Einstellungen (dort Stil Classic/Floating wählen)
  - Tray-Icon unten rechts: Einstellungen / Beenden
"""
import asyncio
import bisect
import ctypes
import datetime
import json
import math
import os
import queue
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from ctypes import wintypes

import psutil
from PySide6.QtCore import QFileInfo, QMimeData, QObject, QPointF, QRectF, QSize, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QCursor, QDrag, QFont, QFontMetrics, QIcon,
                           QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
                           QRadialGradient)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QColorDialog, QComboBox, QFileIconProvider,
                               QInputDialog, QLabel, QListView, QListWidget, QListWidgetItem,
                               QMenu, QPushButton, QSlider, QSystemTrayIcon, QWidget)

PAGE_PLAYER, PAGE_LYRICS, PAGE_SETTINGS, PAGE_SHELF, PAGE_TODAY, PAGE_POMO, PAGE_WATER = 0, 1, 2, 3, 4, 5, 6
PAGES = [(520, 206), (520, 206), (700, 440), (600, 240), (620, 262), (600, 240), (600, 240)]
CORNER = 10          # Radius der geschwungenen Übergänge am Bildschirmrand (Classic)

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", "."), "MeineNotch")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_CONFIG = {
    "language": "de",
    "hidden_apps": [],
    "peek_on_change": True,
    "idle": "time",            # time | face | none
    "minimal": False,
    "lyric_in_pill": True,
    "lyric_offset": 0.3,       # Sekunden, um die der Songtext früher erscheint
    "monitor": "",
    "style": "classic",        # classic | floating
    "glass": False,
    "pages_shelf": True,
    "pages_today": True,
    "shelf": [],
    "tasks": [],
    "size": "auto",            # auto | 100 | 115 | 130 | 150 (Neustart nötig)
    "open_mode": "hover",      # hover | click
    "anim_fast": False,
    "show_date": False,
    "ring": "auto",            # auto (Sekunden) | water | todo | off
    "sounds": True,
    "hide_fullscreen": True,
    "pages_pomo": True,
    "pages_water": True,
    "pomo": {"focus": 25, "short": 5, "long": 15},
    "water": {"goal": 1.5, "bottle": 500, "from": 8, "until": 17, "reminders": True,
              "ml": 0, "date": ""},
    "hud": {"volume": True, "caps": True, "lang": True, "battery": True},
    "mascot": {"body": "#2846c8", "eye_shape": "oval", "eye_color": "#ffffff", "eye_size": 1.0,
               "eye_gap": 1.0, "blink": True, "follow": True, "glow": True, "blush": False,
               "mouth": False},
    "clip_limit": 30,
    "shelf_empty_start": False,
    "stats": {"date": "", "sessions": 0, "focus_min": 0},
}

DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

BTN_STYLE = ("QPushButton{background:rgba(255,255,255,0.10);color:white;border:none;"
             "border-radius:%dpx;font-size:13px;}"
             "QPushButton:hover{background:rgba(255,255,255,0.22);}"
             "QPushButton:checked{background:rgba(255,255,255,0.36);}"
             "QPushButton:disabled{color:#666;}")
DANGER_STYLE = ("QPushButton{background:rgba(220,60,60,0.22);color:#ff8a8a;border:none;"
                "border-radius:10px;font-size:12px;}"
                "QPushButton:hover{background:rgba(220,60,60,0.40);}")
SLIDER_STYLE = ("QSlider::groove:horizontal{height:4px;background:rgba(255,255,255,0.25);border-radius:2px;}"
                "QSlider::sub-page:horizontal{background:white;border-radius:2px;}"
                "QSlider::handle:horizontal{background:white;width:8px;height:8px;margin:-2px 0;border-radius:4px;}")
CHECK_STYLE = ("QCheckBox{color:white;font-size:12px;background:transparent;}"
               "QCheckBox::indicator{width:14px;height:14px;border:1px solid #888;border-radius:3px;background:#222;}"
               "QCheckBox::indicator:checked{background:#4da3ff;border-color:#4da3ff;}")
LIST_STYLE = ("QListWidget{background:rgba(255,255,255,0.06);color:white;border:none;border-radius:8px;font-size:12px;}"
              "QListWidget::item{padding:3px;}"
              "QListWidget::item:selected{background:rgba(255,255,255,0.18);border-radius:8px;color:white;}"
              "QListWidget::indicator{width:14px;height:14px;border:1px solid #888;border-radius:3px;background:#222;}"
              "QListWidget::indicator:checked{background:#4da3ff;border-color:#4da3ff;}"
              "QScrollBar:horizontal{height:6px;background:transparent;}"
              "QScrollBar::handle:horizontal{background:rgba(255,255,255,0.3);border-radius:3px;}"
              "QScrollBar::add-line,QScrollBar::sub-line{width:0px;height:0px;}"
              "QScrollBar:vertical{width:6px;background:transparent;}"
              "QScrollBar::handle:vertical{background:rgba(255,255,255,0.3);border-radius:3px;}")
TASK_LIST_STYLE = LIST_STYLE + "QListWidget::item{padding:6px 4px;}"


# ---------------------------------------------------------------- Allgemeines
def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def fmt_time(sec):
    sec = int(max(0, sec))
    return "%d:%02d" % (sec // 60, sec % 60)


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ---------------------------------------------------------------- Windows-Helfer
user32 = ctypes.windll.user32


def exe_of_hwnd(hwnd):
    try:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return psutil.Process(pid.value).name().lower()
    except Exception:
        return ""


def foreground_exe():
    return exe_of_hwnd(user32.GetForegroundWindow())


def own_exe():
    try:
        return psutil.Process(os.getpid()).name().lower()
    except Exception:
        return ""


def visible_apps():
    names = set()
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            n = exe_of_hwnd(hwnd)
            if n:
                names.add(n)
        return True

    user32.EnumWindows(proc_type(cb), 0)
    names.discard(own_exe())
    return names


def autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, "MeineNotch")
            return True
    except Exception:
        return False


def set_autostart(on):
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                exe = sys.executable
                pyw = exe.replace("python.exe", "pythonw.exe")
                if os.path.exists(pyw):
                    exe = pyw
                winreg.SetValueEx(k, "MeineNotch", 0, winreg.REG_SZ,
                                  '"%s" "%s"' % (exe, os.path.abspath(__file__)))
            else:
                try:
                    winreg.DeleteValue(k, "MeineNotch")
                except FileNotFoundError:
                    pass
    except Exception:
        pass


class Volume:
    def __init__(self):
        self.ep = None
        try:
            from pycaw.pycaw import AudioUtilities
            dev = AudioUtilities.GetSpeakers()
            ep = getattr(dev, "EndpointVolume", None)
            if ep is None:
                from ctypes import POINTER, cast
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import IAudioEndpointVolume
                iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                ep = cast(iface, POINTER(IAudioEndpointVolume))
            self.ep = ep
        except Exception:
            self.ep = None

    def available(self):
        return self.ep is not None

    def get(self):
        try:
            return int(round(self.ep.GetMasterVolumeLevelScalar() * 100))
        except Exception:
            return 50

    def set(self, v):
        try:
            self.ep.SetMasterVolumeLevelScalar(clamp(v, 0, 100) / 100.0, None)
        except Exception:
            pass


# ---------------------------------------------------------------- Musik (Windows Media Control)
class MediaWorker(QObject):
    changed = Signal(dict)
    timeline = Signal(float, float, bool)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.cmds = queue.Queue()

    def start(self):
        threading.Thread(target=lambda: asyncio.run(self._loop()), daemon=True).start()

    def send(self, cmd, arg=None):
        self.cmds.put((cmd, arg))

    async def _read_cover(self, info):
        try:
            from winrt.windows.storage.streams import DataReader
            ref = info.thumbnail
            if ref is None:
                return None
            stream = await ref.open_read_async()
            size = stream.size
            if not size:
                return None
            reader = DataReader(stream.get_input_stream_at(0))
            await reader.load_async(size)
            buf = bytearray(size)
            reader.read_bytes(buf)
            return bytes(buf)
        except Exception:
            return None

    async def _loop(self):
        try:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as Manager)
            manager = await Manager.request_async()
        except Exception as e:
            self.error.emit("Musik-Erkennung nicht verfügbar: " + str(e))
            return

        last_sig, last_key, cover, attempts = None, None, None, 0
        while True:
            try:
                session = manager.get_current_session()
                while not self.cmds.empty():
                    cmd, arg = self.cmds.get_nowait()
                    if not session:
                        continue
                    if cmd == "toggle":
                        await session.try_toggle_play_pause_async()
                    elif cmd == "next":
                        await session.try_skip_next_async()
                    elif cmd == "prev":
                        await session.try_skip_previous_async()
                    elif cmd == "seek":
                        await session.try_change_playback_position_async(int(arg * 10000000))

                if session is None:
                    key, cover = None, None
                    data = dict(has_session=False, title="", artist="", album="", playing=False, cover=None)
                else:
                    info = await session.try_get_media_properties_async()
                    playing = int(session.get_playback_info().playback_status) == 4
                    key = (info.title, info.artist)
                    if key != last_key:
                        cover, attempts = None, 0
                    if cover is None and attempts < 6:
                        cover = await self._read_cover(info)
                        attempts += 1
                    data = dict(has_session=True, title=info.title or "", artist=info.artist or "",
                                album=info.album_title or "", playing=playing, cover=cover)
                    self._emit_timeline(session, playing)

                sig = (data["has_session"], data["title"], data["artist"], data["album"],
                       data["playing"], data["cover"] is not None)
                if sig != last_sig:
                    self.changed.emit(data)
                    last_sig = sig
                last_key = key
            except Exception:
                pass
            await asyncio.sleep(0.6)

    def _emit_timeline(self, session, playing):
        try:
            tl = session.get_timeline_properties()
            start = tl.start_time.total_seconds()
            dur = max(0.0, tl.end_time.total_seconds() - start)
            pos = tl.position.total_seconds() - start
            last = tl.last_updated_time
            if getattr(last, "tzinfo", None):
                now = datetime.datetime.now(datetime.timezone.utc)
            else:
                now = datetime.datetime.utcnow()
            if playing:
                pos += max(0.0, (now - last).total_seconds())
            self.timeline.emit(float(clamp(pos, 0, dur if dur else pos)), float(dur), bool(playing))
        except Exception:
            pass


# ---------------------------------------------------------------- Songtexte (LRCLIB)
def parse_lrc(text):
    out = []
    for raw in text.splitlines():
        tags = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", raw)
        txt = re.sub(r"\[[^\]]*\]", "", raw).strip()
        for m, s in tags:
            out.append((int(m) * 60 + float(s), txt))
    out.sort(key=lambda x: x[0])
    return out


class Lyrics(QObject):
    ready = Signal(object, list)

    def fetch(self, key, title, artist, duration):
        threading.Thread(target=self._run, args=(key, title, artist, duration), daemon=True).start()

    @staticmethod
    def _search(params):
        url = "https://lrclib.net/api/search?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "MeineNotch/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))

    def _run(self, key, title, artist, duration):
        lines = []
        try:
            results = self._search({"track_name": title, "artist_name": artist})
            if not results:
                results = self._search({"q": "%s %s" % (title, artist)})
            results = [r for r in results if r.get("syncedLyrics")]
            if results:
                if duration:
                    results.sort(key=lambda r: abs((r.get("duration") or 0) - duration))
                lines = parse_lrc(results[0]["syncedLyrics"])
        except Exception:
            lines = []
        self.ready.emit(key, lines)


# ---------------------------------------------------------------- Gezeichnete Icons
def _draw_icon_base(p, kind, rect, color):
    """Zeichnet ein Icon in einem 24x24-Raster, skaliert auf rect."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(rect.center())
    s = min(rect.width(), rect.height()) / 24.0
    p.scale(s, s)
    fill = QBrush(color)

    def stroke(width=1.9):
        return QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    if kind == "play":
        p.setPen(stroke(2.4))
        p.setBrush(fill)
        p.drawPolygon(QPolygonF([QPointF(-5, -8), QPointF(-5, 8), QPointF(8, 0)]))
    elif kind == "pause":
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(-7, -8, 5, 16), 1.6, 1.6)
        p.drawRoundedRect(QRectF(2, -8, 5, 16), 1.6, 1.6)
    elif kind in ("next", "prev"):
        if kind == "prev":
            p.scale(-1, 1)
        p.setPen(stroke(2.2))
        p.setBrush(fill)
        p.drawPolygon(QPolygonF([QPointF(-8, -7), QPointF(-8, 7), QPointF(4, 0)]))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(6, -8, 2.8, 16), 1.2, 1.2)
    elif kind == "bubble":
        rr = QPainterPath()
        rr.addRoundedRect(QRectF(-9, -8.5, 18, 13), 4.5, 4.5)
        tail = QPainterPath()
        tail.moveTo(-5.5, 3.5)
        tail.lineTo(-5.5, 9)
        tail.lineTo(0, 4)
        tail.closeSubpath()
        p.setPen(stroke(1.9))
        p.setBrush(Qt.NoBrush)
        p.drawPath(rr.united(tail))
        p.drawLine(QPointF(-4.5, -4), QPointF(4.5, -4))
        p.drawLine(QPointF(-4.5, 0), QPointF(1.5, 0))
    elif kind == "gear":
        pts = []
        for k in range(8):
            a = math.radians(k * 45)
            for da, r in ((-15, 6.8), (-9, 9.8), (9, 9.8), (15, 6.8)):
                ang = a + math.radians(da)
                pts.append(QPointF(r * math.cos(ang), r * math.sin(ang)))
        path = QPainterPath()
        path.setFillRule(Qt.OddEvenFill)
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
        path.addEllipse(QPointF(0, 0), 3.2, 3.2)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(path)
    elif kind == "speaker":
        p.translate(1.5, 0)
        body = QPainterPath()
        body.moveTo(-10, -3.2)
        body.lineTo(-6.5, -3.2)
        body.lineTo(-1.5, -7.5)
        body.lineTo(-1.5, 7.5)
        body.lineTo(-6.5, 3.2)
        body.lineTo(-10, 3.2)
        body.closeSubpath()
        p.setPen(stroke(1.4))
        p.setBrush(fill)
        p.drawPath(body)
        p.setBrush(Qt.NoBrush)
        p.setPen(stroke(1.9))
        p.drawArc(QRectF(-6.5, -5, 10, 10), -50 * 16, 100 * 16)
        p.drawArc(QRectF(-10.5, -9, 18, 18), -50 * 16, 100 * 16)
    elif kind == "folder":
        body = QPainterPath()
        body.addRoundedRect(QRectF(-9, -3.5, 18, 12.5), 2.8, 2.8)
        tab = QPainterPath()
        tab.addRoundedRect(QRectF(-9, -8, 8, 6), 2, 2)
        p.setPen(stroke(1.9))
        p.setBrush(Qt.NoBrush)
        p.drawPath(body.united(tab))
    elif kind == "clipboard":
        p.setPen(stroke(1.9))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(-7, -7.5, 14, 17), 2.8, 2.8)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(-3.6, -10, 7.2, 4.6), 1.6, 1.6)
        p.drawLine(QPointF(-3.5, 0), QPointF(3.5, 0))
        p.drawLine(QPointF(-3.5, 4), QPointF(1.5, 4))
    elif kind in ("chev_l", "chev_r"):
        if kind == "chev_r":
            p.scale(-1, 1)
        p.setPen(stroke(2.6))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(3, -7), QPointF(-3, 0), QPointF(3, 7)]))
    elif kind == "note":
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawEllipse(QPointF(-5, 6.5), 3.3, 2.6)
        p.drawEllipse(QPointF(4, 4.5), 3.3, 2.6)
        p.drawRect(QRectF(-2.1, -7, 1.7, 13.5))
        p.drawRect(QRectF(6.9, -9, 1.7, 13.5))
        p.drawPolygon(QPolygonF([QPointF(-2.1, -7), QPointF(8.6, -9), QPointF(8.6, -5.5), QPointF(-2.1, -3.5)]))
    p.restore()


class IconButton(QPushButton):
    """Runder Button mit gezeichnetem Icon."""

    def __init__(self, parent, kind, radius=14):
        super().__init__(parent)
        self.kind = kind
        self.radius = radius
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def set_kind(self, kind):
        if kind != self.kind:
            self.kind = kind
            self.update()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        enabled = self.isEnabled()
        if not enabled:
            a = 0.05
        elif self.isDown():
            a = 0.32
        elif self.isChecked():
            a = 0.36
        elif self.underMouse():
            a = 0.22
        else:
            a = 0.10
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, int(255 * a)))
        p.drawRoundedRect(QRectF(self.rect()), self.radius, self.radius)
        size = min(self.width(), self.height()) * 0.58
        c = self.rect().center()
        r = QRectF(c.x() - size / 2.0 + 0.5, c.y() - size / 2.0 + 0.5, size, size)
        draw_icon(p, self.kind, r, QColor(255, 255, 255) if enabled else QColor(255, 255, 255, 90))


class IconLabel(QWidget):
    """Nur ein Icon ohne Hintergrund."""

    def __init__(self, parent, kind, color=QColor(200, 205, 220)):
        super().__init__(parent)
        self.kind, self.color = kind, color

    def paintEvent(self, _):
        p = QPainter(self)
        size = min(self.width(), self.height())
        c = self.rect().center()
        draw_icon(p, self.kind, QRectF(c.x() - size / 2.0, c.y() - size / 2.0, size, size), self.color)


# ---------------------------------------------------------------- Zeichen-Helfer
def rounded_pixmap(pix, size, radius):
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    p.setClipPath(path)
    if pix is not None and not pix.isNull():
        scaled = pix.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        p.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    else:
        p.fillRect(0, 0, size, size, QColor(45, 45, 50))
        draw_icon(p, "note", QRectF(size * 0.28, size * 0.28, size * 0.44, size * 0.44),
                  QColor(150, 150, 160))
    p.end()
    return out


def accent_from(pix):
    default = QColor(24, 52, 130)
    if pix is None or pix.isNull():
        return default
    c = pix.toImage().scaled(1, 1, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).pixelColor(0, 0)
    h, s, v, _ = c.getHsv()
    if h < 0:
        return QColor(50, 55, 70)
    return QColor.fromHsv(h, min(255, int(s * 1.15) + 20), clamp(v, 80, 150))


def elide(text, font, width, mode=Qt.ElideRight):
    return QFontMetrics(font).elidedText(text, mode, int(width))


def make_label(parent, x, y, w, h, text="", size=10, bold=False, color="white", align=None):
    lab = QLabel(text, parent)
    lab.setGeometry(x, y, w, h)
    f = QFont("Segoe UI", size)
    f.setBold(bold)
    lab.setFont(f)
    lab.setStyleSheet("color:%s;background:transparent;" % color)
    lab.setAlignment(align if align is not None else (Qt.AlignLeft | Qt.AlignVCenter))
    return lab


def make_button(parent, x, y, w, h, text="", radius=14, checkable=False, icon=None):
    if icon:
        b = IconButton(parent, icon, radius)
    else:
        b = QPushButton(text, parent)
        b.setFont(QFont("Segoe UI", 10))
        b.setStyleSheet(BTN_STYLE % radius)
        b.setCursor(Qt.PointingHandCursor)
        b.setFocusPolicy(Qt.NoFocus)
    b.setGeometry(x, y, w, h)
    b.setCheckable(checkable)
    return b


def make_check(parent, x, y, w, text):
    c = QCheckBox(text, parent)
    c.setGeometry(x, y, w, 24)
    c.setStyleSheet(CHECK_STYLE)
    return c


def make_tray_icon():
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(0, 0, 0))
    p.setPen(QColor(120, 120, 130))
    p.drawRoundedRect(4, 18, 56, 28, 12, 12)
    p.setBrush(QColor(255, 255, 255))
    p.setPen(Qt.NoPen)
    p.drawEllipse(40, 27, 10, 10)
    p.end()
    return QIcon(pix)


# ---------------------------------------------------------------- Animation (Federn)
class Spring:
    """Gedämpfte Feder: weich, unterbrechbar, behält die Geschwindigkeit beim Richtungswechsel."""

    def __init__(self, value, k=380.0, zeta=1.0, eps=0.3):
        self.x = float(value)
        self.v = 0.0
        self.target = float(value)
        self.k = k
        self.zeta = zeta
        self.c = 2.0 * zeta * math.sqrt(k)
        self.eps = eps

    def step(self, dt):
        n = max(1, int(dt / 0.004))
        h = dt / n
        for _ in range(n):
            a = -self.k * (self.x - self.target) - self.c * self.v
            self.v += a * h
            self.x += self.v * h

    def settled(self):
        return abs(self.x - self.target) < self.eps and abs(self.v) < self.eps * 8

    def snap(self):
        self.x, self.v = self.target, 0.0

    def retune(self, k, zeta=None):
        if zeta is not None:
            self.zeta = zeta
        self.k = k
        self.c = 2.0 * self.zeta * math.sqrt(k)


class SizeSpring:
    def __init__(self, w, h, k=320.0):
        self.sw = Spring(w, k, 1.0, 0.3)
        self.sh = Spring(h, k, 1.0, 0.3)

    @property
    def w(self):
        return self.sw.x

    @property
    def h(self):
        return self.sh.x

    def go(self, w, h):
        if (float(w), float(h)) == (self.sw.target, self.sh.target):
            return False
        self.sw.target, self.sh.target = float(w), float(h)
        return True

    def step(self, dt):
        self.sw.step(dt)
        self.sh.step(dt)

    def settled(self):
        return self.sw.settled() and self.sh.settled()

    def snap(self):
        self.sw.snap()
        self.sh.snap()


# ---------------------------------------------------------------- Kleine Widgets
class StyleCard(QWidget):
    """Vorschau-Karte für den Notch-Stil (Classic / Floating)."""
    clicked = Signal()

    def __init__(self, parent, x, y, kind, text):
        super().__init__(parent)
        self.setGeometry(x, y, 220, 128)
        self.kind, self.text, self.selected = kind, text, False
        self.setCursor(Qt.PointingHandCursor)

    def set_selected(self, on):
        self.selected = on
        self.update()

    def mousePressEvent(self, _):
        self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(255, 255, 255, 14))
        p.setPen(QPen(QColor(77, 163, 255), 2) if self.selected else Qt.NoPen)
        p.drawRoundedRect(QRectF(1, 1, 218, 126), 12, 12)
        inner = QRectF(14, 12, 192, 76)
        g = QLinearGradient(inner.topLeft(), inner.bottomRight())
        g.setColorAt(0, QColor(170, 150, 235))
        g.setColorAt(1, QColor(110, 110, 230))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(inner, 10, 10)
        p.setBrush(QColor(0, 0, 0))
        cx = inner.center().x()
        if self.kind == "classic":
            cr = 5.0
            l, r, t, b, rad = cx - 30, cx + 30, inner.top(), inner.top() + 14, 6
            path = QPainterPath()
            path.moveTo(l - cr, t)
            path.lineTo(r + cr, t)
            path.quadTo(r, t, r, t + cr)
            path.lineTo(r, b - rad)
            path.quadTo(r, b, r - rad, b)
            path.lineTo(l + rad, b)
            path.quadTo(l, b, l, b - rad)
            path.lineTo(l, t + cr)
            path.quadTo(l, t, l - cr, t)
            path.closeSubpath()
            p.drawPath(path)
        else:
            p.drawRoundedRect(QRectF(cx - 30, inner.top() + 8, 60, 14), 7, 7)
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(QRectF(14, 94, 190, 26), Qt.AlignVCenter | Qt.AlignLeft, self.text)


class WeekStrip(QWidget):
    """Wochenleiste mit hervorgehobenem heutigen Tag."""

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        today = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())
        w = self.width() / 7.0
        for i in range(7):
            d = monday + datetime.timedelta(days=i)
            cx = w * i + w / 2
            p.setPen(QColor(140, 148, 170))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(QRectF(cx - w / 2, 0, w, 16), Qt.AlignCenter, DAYS[i][0])
            if d == today:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(55, 120, 255))
                p.drawEllipse(QRectF(cx - 12, 22, 24, 24))
            f = QFont("Segoe UI", 10)
            f.setBold(d == today)
            p.setFont(f)
            p.setPen(QColor(255, 255, 255) if d == today else QColor(200, 205, 220))
            p.drawText(QRectF(cx - 12, 22, 24, 24), Qt.AlignCenter, str(d.day))


class ShelfList(QListWidget):
    """Horizontale Dateiliste, aus der man Dateien wieder herausziehen kann."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListView.Static)
        self.setIconSize(QSize(52, 52))
        self.setGridSize(QSize(104, 100))
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setStyleSheet(LIST_STYLE)

    def _mime(self, items):
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(i.data(Qt.UserRole)) for i in items])
        return md

    def startDrag(self, _actions):
        items = self.selectedItems()
        if not items:
            return
        drag = QDrag(self)
        drag.setMimeData(self._mime(items))
        drag.setPixmap(items[0].icon().pixmap(48, 48))
        drag.exec(Qt.CopyAction)

    def wheelEvent(self, e):
        sb = self.horizontalScrollBar()
        sb.setValue(sb.value() - e.angleDelta().y())
        e.accept()


class LyricsView(QWidget):
    """Songtext mit weichem Scrollen: Zeilen gleiten, wechseln Größe und blenden über."""
    LINE_H = 28

    def __init__(self, parent):
        super().__init__(parent)
        self.lines = []
        self.status = ""
        self.disp = Spring(0.0, k=150.0, zeta=1.0, eps=0.002)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self._step)
        self._last = time.perf_counter()

    def set_lines(self, lines, status=""):
        self.lines = lines
        self.status = status
        self.jump(0)

    def jump(self, idx):
        self.disp.target = float(max(idx, 0))
        self.disp.snap()
        self.timer.stop()
        self.update()

    def set_index(self, idx):
        target = float(max(idx, 0))
        if target != self.disp.target:
            self.disp.target = target
            if not self.timer.isActive():
                self._last = time.perf_counter()
                self.timer.start()

    def _step(self):
        now = time.perf_counter()
        dt = min(now - self._last, 0.05)
        self._last = now
        self.disp.step(dt)
        if self.disp.settled():
            self.disp.snap()
            self.timer.stop()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        w = self.width()
        if not self.lines:
            f = QFont("Segoe UI", 10)
            p.setFont(f)
            p.setPen(QColor(184, 188, 200))
            p.drawText(QRectF(0, 0, w, 36), Qt.AlignVCenter | Qt.AlignLeft, self.status)
            return
        d = self.disp.x
        base = int(math.floor(d))
        for i in range(max(0, base - 1), min(len(self.lines) - 1, base + 4) + 1):
            rel = i - d
            ad = abs(rel)
            if rel < 0:
                alpha = clamp(1.0 - ad * 1.5, 0.0, 1.0)
            else:
                alpha = clamp(1.0 - 0.27 * ad, 0.18, 1.0)
            if alpha <= 0.01:
                continue
            size_px = 17.0 - 4.0 * clamp(ad, 0.0, 1.0)
            f = QFont("Segoe UI")
            f.setPointSizeF(size_px * 0.75)
            f.setBold(ad < 0.5)
            p.setFont(f)
            tint = 255 if ad < 0.5 else 214
            p.setPen(QColor(tint, tint, 255 if ad < 0.5 else 235, int(255 * alpha)))
            text = self.lines[i][1] or "…"
            text = QFontMetrics(f).elidedText(text, Qt.ElideRight, w - 4)
            cy = 18 + rel * self.LINE_H
            p.drawText(QRectF(0, cy - 15, w, 30), Qt.AlignVCenter | Qt.AlignLeft, text)


class Veil(QWidget):
    """Liegt über dem Inhalt und blendet ihn weich ein (ersetzt den teuren Opacity-Effekt)."""

    def __init__(self, notch):
        super().__init__(notch)
        self.notch = notch
        self.alpha = 1.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _):
        if self.alpha <= 0.004:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self.notch._paint_background(p, self.width(), self.height(), self.alpha)


# ---------------------------------------------------------------- Neu in v6: Hilfen
APP_NAME = "Meine Notch"        # <- hier den Namen ändern (Tray-Tooltip und Meldungen)
POMO_NAMES = {"focus": "Fokus", "short": "Kurze Pause", "long": "Lange Pause"}
LANG_NAMES = {0x0407: "DE", 0x0409: "EN", 0x0809: "EN-GB", 0x040C: "FR", 0x040A: "ES", 0x0C0A: "ES",
              0x0410: "IT", 0x0419: "RU", 0x041F: "TR", 0x0415: "PL", 0x0411: "JA", 0x0412: "KO",
              0x0804: "ZH", 0x0816: "PT", 0x0416: "PT-BR", 0x0413: "NL", 0x041D: "SV"}
MASCOT_COLORS = ["#2846c8", "#7a3cf0", "#d6283b", "#1fa971", "#f08a24", "#e04aa0", "#18a8c8", "#8a8f9c"]
EYE_COLORS = ["#ffffff", "#7fe3ff", "#ffe27a", "#ff9ad5", "#9dffb0", "#ff7a7a"]
EYE_SHAPES = (("oval", "Oval"), ("round", "Rund"), ("wide", "Breit"), ("sleepy", "Müde"), ("happy", "Froh"))
CAT_STYLE = ("QListWidget{background:transparent;border:none;font-size:13px;color:#cfd3e0;}"
             "QListWidget::item{padding:7px 12px;border-radius:9px;margin:1px 0;}"
             "QListWidget::item:hover{background:rgba(255,255,255,0.08);}"
             "QListWidget::item:selected{background:rgba(255,255,255,0.18);color:white;}")


def cget(cfg, *path):
    """Liest einen (verschachtelten) Wert, fehlende Werte kommen aus DEFAULT_CONFIG."""
    cur, dflt = cfg, DEFAULT_CONFIG
    for key in path:
        cur = cur.get(key) if isinstance(cur, dict) else None
        dflt = dflt.get(key) if isinstance(dflt, dict) else None
    return dflt if cur is None else cur


def cset(cfg, path, value):
    cur = cfg
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[path[-1]] = value


def play_sound(cfg):
    if not cget(cfg, "sounds"):
        return
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]


def foreground_fullscreen():
    """True, wenn das aktive Fenster den ganzen Monitor ausfüllt (Spiele, Videos, Folien)."""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return False
        r = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        mon = user32.MonitorFromWindow(hwnd, 2)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return False
        m = mi.rcMonitor
        return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom
    except Exception:
        return False


def foreground_lang():
    try:
        hwnd = user32.GetForegroundWindow()
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        lid = user32.GetKeyboardLayout(tid) & 0xFFFF
        return hwnd, LANG_NAMES.get(lid, "%04X" % lid)
    except Exception:
        return 0, ""


def caps_on():
    try:
        return bool(user32.GetKeyState(0x14) & 1)
    except Exception:
        return False


def volume_muted(vol):
    try:
        return bool(vol.ep.GetMute())
    except Exception:
        return False


# ---------------------------------------------------------------- Zusätzliche Icons
EXTRA_ICONS = ("reset", "plus", "minus", "timer", "droplet", "caps", "lang", "battery", "mute")


def draw_icon(p, kind, rect, color):
    if kind not in EXTRA_ICONS:
        _draw_icon_base(p, kind, rect, color)
        return
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(rect.center())
    s = min(rect.width(), rect.height()) / 24.0
    p.scale(s, s)
    fill = QBrush(color)
    pen = QPen(color, 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    if kind in ("plus", "minus"):
        p.setPen(QPen(color, 2.4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(-7, 0), QPointF(7, 0))
        if kind == "plus":
            p.drawLine(QPointF(0, -7), QPointF(0, 7))
    elif kind == "reset":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(-8, -8, 16, 16), 40 * 16, 280 * 16)
        p.setBrush(fill)
        p.drawPolygon(QPolygonF([QPointF(2.6, -6.8), QPointF(10, -7.4), QPointF(7.6, 0)]))
    elif kind == "timer":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(0, 1.5), 8, 8)
        p.drawLine(QPointF(0, 1.5), QPointF(0, -3.5))
        p.drawLine(QPointF(-2.5, -9.5), QPointF(2.5, -9.5))
    elif kind == "droplet":
        path = QPainterPath()
        path.moveTo(0, -10)
        path.cubicTo(2, -6, 8, -1, 8, 4.5)
        path.cubicTo(8, 8.5, 4.5, 11, 0, 11)
        path.cubicTo(-4.5, 11, -8, 8.5, -8, 4.5)
        path.cubicTo(-8, -1, -2, -6, 0, -10)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(path)
    elif kind == "caps":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(QPolygonF([QPointF(0, -10), QPointF(8, -1), QPointF(3.5, -1), QPointF(3.5, 4.5),
                                 QPointF(-3.5, 4.5), QPointF(-3.5, -1), QPointF(-8, -1)]))
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(-3.5, 7.5, 7, 2.4), 1.1, 1.1)
    elif kind == "lang":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(-10, -6.5, 20, 13), 3, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        for k in range(4):
            p.drawRoundedRect(QRectF(-7 + k * 4.2, -3.2, 2.4, 2.2), 0.6, 0.6)
        for k in range(3):
            p.drawRoundedRect(QRectF(-5 + k * 4.2, 0.4, 2.4, 2.2), 0.6, 0.6)
        p.drawRoundedRect(QRectF(-4, 3.6, 8, 1.8), 0.8, 0.8)
    elif kind == "battery":
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(-10, -5.5, 18, 11), 2.4, 2.4)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(8.8, -2, 2.4, 4), 0.8, 0.8)
        p.drawRoundedRect(QRectF(-8, -3.5, 12, 7), 1.2, 1.2)
    elif kind == "mute":
        p.translate(-1.5, 0)
        body = QPainterPath()
        body.moveTo(-10, -3.2)
        body.lineTo(-6.5, -3.2)
        body.lineTo(-1.5, -7.5)
        body.lineTo(-1.5, 7.5)
        body.lineTo(-6.5, 3.2)
        body.lineTo(-10, 3.2)
        body.closeSubpath()
        p.setPen(QPen(color, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(fill)
        p.drawPath(body)
        p.setPen(QPen(color, 1.9, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(3, -4), QPointF(9.5, 4))
        p.drawLine(QPointF(9.5, -4), QPointF(3, 4))
    p.restore()


# ---------------------------------------------------------------- Maskottchen
def mascot_cfg(cfg):
    return {k: cget(cfg, "mascot", k) for k in DEFAULT_CONFIG["mascot"]}


def draw_mascot(p, w, h, m, now, eye_dx=0.0):
    """Zeichnet das Maskottchen (Schimmer, Augen, Wangen, Lächeln) in eine Pille der Größe w x h."""
    p.save()
    body = QColor(m["body"])
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0.35, QColor(0, 0, 0, 0))
    c = QColor(body)
    c.setAlpha(215)
    g.setColorAt(1.0, c)
    p.fillRect(QRectF(0, 0, w, h), QBrush(g))
    s = min(1.0, h / 34.0)
    size = float(m["eye_size"]) * s
    gap = 13.0 * float(m["eye_gap"]) * s
    cy = h / 2.0 - (3.0 * s if m["mouth"] else 1.0)
    cx = w / 2.0
    blink = bool(m["blink"]) and (now % 4.5) < 0.14
    follow = eye_dx if m["follow"] else 0.0
    col = QColor(m["eye_color"])
    shape = m["eye_shape"]
    ew, eh = {"oval": (9, 14), "round": (11, 11), "wide": (14, 9),
              "sleepy": (11, 6.5), "happy": (11, 7)}.get(shape, (9, 14))
    ew, eh = ew * size, eh * size
    if blink and shape != "happy":
        eh = max(1.5, eh * 0.15)
    for sign in (-1, 1):
        ex = cx + sign * gap + follow
        if m["glow"]:
            rad = max(ew, eh) * 1.5
            rg = QRadialGradient(QPointF(ex, cy), rad)
            g1 = QColor(col)
            g1.setAlpha(110)
            g2 = QColor(col)
            g2.setAlpha(0)
            rg.setColorAt(0.0, g1)
            rg.setColorAt(1.0, g2)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(rg))
            p.drawEllipse(QPointF(ex, cy), rad, rad)
        if shape == "happy":
            p.setPen(QPen(col, 2.4 * size, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(ex - ew / 2, cy - eh / 2, ew, ew), 20 * 16, 140 * 16)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QRectF(ex - ew / 2, cy - eh / 2, ew, eh))
    if m["blush"]:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 120, 160, 120))
        for sign in (-1, 1):
            p.drawEllipse(QPointF(cx + sign * (gap + 15 * s) + follow, cy + 6 * s), 4.5 * s, 2.8 * s)
    if m["mouth"]:
        p.setPen(QPen(col, 1.6 * s, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - 4 * s + follow * 0.5, cy + 5 * s, 8 * s, 5 * s), 200 * 16, 140 * 16)
    p.restore()


class MascotPreview(QWidget):
    """Live-Vorschau des Maskottchens in den Einstellungen."""

    def __init__(self, parent, notch):
        super().__init__(parent)
        self.notch = notch
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)

    def showEvent(self, e):
        self.timer.start(33)
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF((self.width() - 240) / 2.0, 6, 240, 42)
        path = QPainterPath()
        path.addRoundedRect(r, 21, 21)
        p.fillPath(path, QColor(0, 0, 0))
        p.setClipPath(path)
        p.translate(r.topLeft())
        draw_mascot(p, r.width(), r.height(), mascot_cfg(self.notch.cfg), time.time(), self.notch.eye_dx)


class Swatch(QPushButton):
    """Runder Farbknopf."""

    def __init__(self, parent, color):
        super().__init__(parent)
        self.color = QColor(color)
        self.sel = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        p.setPen(QPen(QColor(255, 255, 255), 2) if self.sel else QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(self.color)
        p.drawEllipse(r)


LANGUAGE_TEXT = {'en': {'Allgemein': 'General', 'Aussehen': 'Appearance', 'Maskottchen': 'Mascot', 'Musik': 'Music', 'Seiten': 'Pages', 'HUD & Töne': 'HUD & Sounds', 'Wasser': 'Water', 'Apps': 'Apps', 'Fertig': 'Done', 'Beenden': 'Quit', 'Sprache': 'Language', 'Mit Windows starten': 'Start with Windows', 'Größe (Neustart nötig)': 'Size (restart required)', 'Notch öffnen': 'Open Notch', 'Animationen': 'Animations', 'Wenn nichts läuft': 'When idle', 'Ring neben der Uhr': 'Ring next to clock', 'Datum neben der Uhr anzeigen': 'Show date next to clock', 'Minimale Notch (kleiner, wenn nichts läuft)': 'Minimal Notch (smaller when idle)', 'Im Vollbild ausblenden (Spiele, Videos, Folien)': 'Hide in fullscreen (games, videos, slides)', 'Monitor': 'Monitor', 'Uhrzeit': 'Clock', 'Gesicht': 'Face', 'Sekunden': 'Seconds', 'Aufgaben': 'Tasks', 'Klassisch (am Rand)': 'Classic (at edge)', 'Schwebend (Pille)': 'Floating (pill)', 'Notch-Stil': 'Notch style', 'Glas (leicht durchscheinend)': 'Glass (slightly translucent)', 'Körperfarbe': 'Body color', 'Augenform': 'Eye shape', 'Augenfarbe': 'Eye color', 'Augengröße': 'Eye size', 'Augenabstand': 'Eye spacing', 'Blinzeln': 'Blink', 'Folgt der Maus': 'Follow mouse', 'Leuchtende Augen': 'Glowing eyes', 'Wangen': 'Blush', 'Lächeln': 'Smile', 'Als Anzeige für den Leerlauf verwenden': 'Use as idle display', 'Songtext in der eingeklappten Notch': 'Lyrics in collapsed Notch', 'Bei Songwechsel kurz aufklappen': 'Briefly expand when song changes', 'Songtext früher anzeigen': 'Show lyrics earlier', 'Diese Seiten zeigt die Notch': 'Pages shown in Notch', 'Shelf & Zwischenablage': 'Shelf & clipboard', 'Heute (Woche & Aufgaben)': 'Today (week & tasks)', 'Anzeigen in der Notch': 'Indicators in Notch', 'Lautstärke': 'Volume', 'Eingabesprache': 'Input language', 'Erinnerungstöne (Pomodoro und Wasser)': 'Reminder sounds (Pomodoro and water)', 'Dauer': 'Duration', 'Fokus': 'Focus', 'Kurze Pause': 'Short break', 'Lange Pause': 'Long break', 'Tagesziel': 'Daily goal', 'Flaschengröße': 'Bottle size', 'Aktiv ab': 'Active from', 'Aktiv bis': 'Active until', 'Heutigen Fortschritt zurücksetzen': "Reset today's progress", 'In diesen Apps ausblenden': 'Hide in these apps', 'Liste aktualisieren': 'Refresh list', 'Alles löschen': 'Clear all', 'Heute': 'Today', '+ Aufgabe': '+ Task', 'Erledigte löschen': 'Delete completed', 'Zeit zu trinken': 'Time to drink'}, 'es': {'Allgemein': 'General', 'Aussehen': 'Apariencia', 'Maskottchen': 'Mascota', 'Musik': 'Música', 'Seiten': 'Páginas', 'HUD & Töne': 'HUD y sonidos', 'Wasser': 'Agua', 'Apps': 'Aplicaciones', 'Fertig': 'Listo', 'Beenden': 'Salir', 'Sprache': 'Idioma', 'Mit Windows starten': 'Iniciar con Windows', 'Größe (Neustart nötig)': 'Tamaño (requiere reinicio)', 'Notch öffnen': 'Abrir Notch', 'Animationen': 'Animaciones', 'Wenn nichts läuft': 'En reposo', 'Ring neben der Uhr': 'Anillo junto al reloj', 'Datum neben der Uhr anzeigen': 'Mostrar fecha junto al reloj', 'Minimale Notch (kleiner, wenn nichts läuft)': 'Notch mínima (más pequeña en reposo)', 'Im Vollbild ausblenden (Spiele, Videos, Folien)': 'Ocultar en pantalla completa', 'Monitor': 'Monitor', 'Uhrzeit': 'Hora', 'Gesicht': 'Cara', 'Sekunden': 'Segundos', 'Aufgaben': 'Tareas', 'Klassisch (am Rand)': 'Clásico (en el borde)', 'Schwebend (Pille)': 'Flotante (píldora)', 'Notch-Stil': 'Estilo de Notch', 'Glas (leicht durchscheinend)': 'Cristal translúcido', 'Körperfarbe': 'Color del cuerpo', 'Augenform': 'Forma de ojos', 'Augenfarbe': 'Color de ojos', 'Augengröße': 'Tamaño de ojos', 'Augenabstand': 'Separación de ojos', 'Blinzeln': 'Parpadear', 'Folgt der Maus': 'Seguir el ratón', 'Leuchtende Augen': 'Ojos brillantes', 'Wangen': 'Mejillas', 'Lächeln': 'Sonrisa', 'Als Anzeige für den Leerlauf verwenden': 'Usar como pantalla en reposo', 'Songtext in der eingeklappten Notch': 'Letra en Notch plegada', 'Bei Songwechsel kurz aufklappen': 'Expandir al cambiar de canción', 'Songtext früher anzeigen': 'Mostrar letra antes', 'Diese Seiten zeigt die Notch': 'Páginas que muestra Notch', 'Shelf & Zwischenablage': 'Estante y portapapeles', 'Heute (Woche & Aufgaben)': 'Hoy (semana y tareas)', 'Anzeigen in der Notch': 'Indicadores en Notch', 'Lautstärke': 'Volumen', 'Eingabesprache': 'Idioma de entrada', 'Erinnerungstöne (Pomodoro und Wasser)': 'Sonidos de recordatorio', 'Dauer': 'Duración', 'Fokus': 'Concentración', 'Kurze Pause': 'Pausa corta', 'Lange Pause': 'Pausa larga', 'Tagesziel': 'Objetivo diario', 'Flaschengröße': 'Tamaño de botella', 'Aktiv ab': 'Activo desde', 'Aktiv bis': 'Activo hasta', 'Heutigen Fortschritt zurücksetzen': 'Restablecer progreso de hoy', 'In diesen Apps ausblenden': 'Ocultar en estas aplicaciones', 'Liste aktualisieren': 'Actualizar lista', 'Alles löschen': 'Borrar todo', 'Heute': 'Hoy', '+ Aufgabe': '+ Tarea', 'Erledigte löschen': 'Eliminar completadas', 'Zeit zu trinken': 'Hora de beber'}, 'fr': {'Allgemein': 'Général', 'Aussehen': 'Apparence', 'Maskottchen': 'Mascotte', 'Musik': 'Musique', 'Seiten': 'Pages', 'HUD & Töne': 'HUD et sons', 'Wasser': 'Eau', 'Apps': 'Applications', 'Fertig': 'Terminé', 'Beenden': 'Quitter', 'Sprache': 'Langue', 'Mit Windows starten': 'Démarrer avec Windows', 'Größe (Neustart nötig)': 'Taille (redémarrage requis)', 'Notch öffnen': 'Ouvrir la Notch', 'Animationen': 'Animations', 'Wenn nichts läuft': 'Au repos', 'Ring neben der Uhr': "Anneau près de l'horloge", 'Datum neben der Uhr anzeigen': "Afficher la date près de l'horloge", 'Minimale Notch (kleiner, wenn nichts läuft)': 'Notch minimale (plus petite au repos)', 'Im Vollbild ausblenden (Spiele, Videos, Folien)': 'Masquer en plein écran', 'Monitor': 'Écran', 'Uhrzeit': 'Heure', 'Gesicht': 'Visage', 'Sekunden': 'Secondes', 'Aufgaben': 'Tâches', 'Klassisch (am Rand)': 'Classique (au bord)', 'Schwebend (Pille)': 'Flottante (pilule)', 'Notch-Stil': 'Style de Notch', 'Glas (leicht durchscheinend)': 'Verre translucide', 'Körperfarbe': 'Couleur du corps', 'Augenform': 'Forme des yeux', 'Augenfarbe': 'Couleur des yeux', 'Augengröße': 'Taille des yeux', 'Augenabstand': 'Écart des yeux', 'Blinzeln': 'Cligner des yeux', 'Folgt der Maus': 'Suit la souris', 'Leuchtende Augen': 'Yeux lumineux', 'Wangen': 'Joues', 'Lächeln': 'Sourire', 'Als Anzeige für den Leerlauf verwenden': 'Utiliser comme affichage au repos', 'Songtext in der eingeklappten Notch': 'Paroles dans la Notch repliée', 'Bei Songwechsel kurz aufklappen': 'Déployer au changement de chanson', 'Songtext früher anzeigen': 'Afficher les paroles plus tôt', 'Diese Seiten zeigt die Notch': 'Pages affichées dans la Notch', 'Shelf & Zwischenablage': 'Étagère et presse-papiers', 'Heute (Woche & Aufgaben)': "Aujourd'hui (semaine et tâches)", 'Anzeigen in der Notch': 'Indicateurs dans la Notch', 'Lautstärke': 'Volume', 'Eingabesprache': 'Langue de saisie', 'Erinnerungstöne (Pomodoro und Wasser)': 'Sons de rappel', 'Dauer': 'Durée', 'Fokus': 'Concentration', 'Kurze Pause': 'Pause courte', 'Lange Pause': 'Pause longue', 'Tagesziel': 'Objectif quotidien', 'Flaschengröße': 'Taille de la bouteille', 'Aktiv ab': 'Actif à partir de', 'Aktiv bis': "Actif jusqu'à", 'Heutigen Fortschritt zurücksetzen': 'Réinitialiser la progression du jour', 'In diesen Apps ausblenden': 'Masquer dans ces applications', 'Liste aktualisieren': 'Actualiser la liste', 'Alles löschen': 'Tout effacer', 'Heute': "Aujourd'hui", '+ Aufgabe': '+ Tâche', 'Erledigte löschen': 'Supprimer les tâches terminées', 'Zeit zu trinken': 'Il est temps de boire'}}


class Pane:
    """Baut Zeilen (Schalter, Auswahl, Zähler, Farben) in einen Einstellungs-Bereich."""
    X0 = 186

    def __init__(self, notch, widget):
        self.n, self.w, self.y = notch, widget, 4
        self.refreshers = []

    def refresh(self):
        for f in self.refreshers:
            f()

    def language_selector(self):
        make_label(self.w, 0, self.y, 180, 28, self.n.tr("Sprache"), size=10)
        combo = QComboBox(self.w)
        combo.setGeometry(self.X0, self.y, 190, 28)
        for label, code in (("Deutsch", "de"), ("English", "en"), ("Español", "es"), ("Français", "fr")):
            combo.addItem(label, code)
        combo.setCurrentIndex(max(0, combo.findData(self.n.cfg.get("language", "de"))))
        combo.setStyleSheet("QComboBox{background:rgba(255,255,255,0.10);color:white;border:0;border-radius:7px;padding:4px 8px;} QComboBox QAbstractItemView{background:#252936;color:white;}")
        combo.currentIndexChanged.connect(lambda _=0: self.n.set_language(combo.currentData()))
        self.y += 36
        self.language_combo = combo

    def title(self, text):
        make_label(self.w, 0, self.y, 480, 20, text, size=10, bold=True, color="#c8ccd8")
        self.y += 26

    def note(self, text, h=36):
        lab = make_label(self.w, 0, self.y, 480, h, text, size=9, color="#9aa3b8")
        lab.setWordWrap(True)
        lab.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.y += h + 4

    def _toggle(self, path, text, getter, x, width):
        c = make_check(self.w, x, self.y, width, text)
        c.toggled.connect(lambda on, p=path: self.n.set_cfg(p, bool(on)))

        def refresh(c=c, p=path):
            c.blockSignals(True)
            c.setChecked(bool(getter() if getter else cget(self.n.cfg, *p)))
            c.blockSignals(False)
        self.refreshers.append(refresh)

    def toggle(self, path, text, getter=None):
        self._toggle(path, text, getter, 0, 480)
        self.y += 30

    def toggles(self, items):
        width = 480 // len(items)
        for i, (path, text) in enumerate(items):
            self._toggle(path, text, None, i * width, width - 6)
        self.y += 30

    def segmented(self, path, label, options, width=64):
        make_label(self.w, 0, self.y, 180, 28, label, size=10)
        btns = []

        def refresh():
            cur = cget(self.n.cfg, *path)
            for v, b in btns:
                same = abs(v - cur) < 1e-6 if (isinstance(v, float) and isinstance(cur, (int, float))) else v == cur
                b.setChecked(same)

        def choose(v):
            self.n.set_cfg(path, v)
            refresh()
        for i, (val, text) in enumerate(options):
            b = make_button(self.w, self.X0 + i * (width + 6), self.y, width, 28, text, radius=8, checkable=True)
            b.clicked.connect(lambda _=False, v=val: choose(v))
            btns.append((val, b))
        self.refreshers.append(refresh)
        self.y += 36

    def stepper(self, path, label, step, lo, hi, fmt="%d"):
        make_label(self.w, 0, self.y, 180, 28, label, size=10)
        minus = make_button(self.w, self.X0, self.y + 1, 28, 26, radius=13, icon="minus")
        val = make_label(self.w, self.X0 + 32, self.y, 90, 28, "", size=10, align=Qt.AlignCenter)
        plus = make_button(self.w, self.X0 + 126, self.y + 1, 28, 26, radius=13, icon="plus")

        def refresh():
            val.setText(fmt % cget(self.n.cfg, *path))

        def bump(d):
            new = clamp(round(cget(self.n.cfg, *path) + d, 3), lo, hi)
            if isinstance(step, int):
                new = int(new)
            self.n.set_cfg(path, new)
            refresh()
        minus.clicked.connect(lambda: bump(-step))
        plus.clicked.connect(lambda: bump(step))
        self.refreshers.append(refresh)
        self.y += 36

    def color_row(self, path, label, colors):
        make_label(self.w, 0, self.y, 180, 28, label, size=10)
        sw = []

        def refresh():
            cur = str(cget(self.n.cfg, *path)).lower()
            for s in sw:
                s.sel = s.color.name().lower() == cur
                s.update()

        def pick(col):
            self.n.set_cfg(path, col)
            refresh()

        def custom():
            self.n.modal_open = True
            col = QColorDialog.getColor(QColor(str(cget(self.n.cfg, *path))), None, "Farbe wählen")
            self.n.modal_open = False
            if col.isValid():
                pick(col.name())
        for i, c in enumerate(colors):
            s = Swatch(self.w, c)
            s.setGeometry(self.X0 + i * 34, self.y, 28, 28)
            s.clicked.connect(lambda _=False, col=c: pick(col))
            sw.append(s)
        more = make_button(self.w, self.X0 + len(colors) * 34, self.y, 40, 28, "…", radius=8)
        more.clicked.connect(custom)
        self.refreshers.append(refresh)
        self.y += 36

    def gap(self, height=6):
        """Fügt einen vertikalen Abstand zwischen Einstellungselementen ein."""
        self.y += max(0, int(height))

    def button(self, text, cb, danger=False, width=260):
        b = make_button(self.w, 0, self.y, width, 28, text, radius=8)
        if danger:
            b.setStyleSheet(DANGER_STYLE)
        b.clicked.connect(cb)
        self.y += 36
        return b


# ---------------------------------------------------------------- Pomodoro und Wasser
class ProgressRing(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.value, self.text, self.sub = 0.0, "", ""
        self.color = QColor(255, 120, 100)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height())
        r = QRectF((self.width() - s) / 2.0 + 8, (self.height() - s) / 2.0 + 8, s - 16, s - 16)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 40), 8, Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(r)
        p.setPen(QPen(self.color, 8, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 90 * 16, -int(clamp(self.value, 0.0, 1.0) * 360 * 16))
        f = QFont("Segoe UI", 14)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(r.x(), r.center().y() - 22, r.width(), 24), Qt.AlignCenter, self.text)
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor(190, 196, 214))
        p.drawText(QRectF(r.x(), r.center().y() + 2, r.width(), 20), Qt.AlignCenter, self.sub)


class WaterGlass(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.frac = 0.0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.moveTo(8, 6)
        path.lineTo(w - 8, 6)
        path.lineTo(w - 18, h - 6)
        path.lineTo(18, h - 6)
        path.closeSubpath()
        p.save()
        p.setClipPath(path)
        y = (h - 6) - clamp(self.frac, 0.0, 1.0) * (h - 12)
        p.fillRect(QRectF(0, y, w, h - y), QColor(70, 150, 255, 225))
        p.restore()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 200), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        f = QFont("Segoe UI", 11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "%d %%" % int(self.frac * 100))


def focus_stats(cfg):
    today = datetime.date.today().isoformat()
    if cget(cfg, "stats", "date") != today:
        cset(cfg, ("stats",), {"date": today, "sessions": 0, "focus_min": 0})
    return int(cget(cfg, "stats", "sessions")), int(cget(cfg, "stats", "focus_min"))


class Pomodoro:
    def __init__(self, cfg, on_event):
        self.cfg, self.on_event = cfg, on_event
        self.mode, self.running, self.session = "focus", False, 0
        self.end_at, self.left = 0.0, self.duration("focus")

    def duration(self, mode=None):
        return float(cget(self.cfg, "pomo", mode or self.mode)) * 60.0

    def remaining(self):
        return max(0.0, self.end_at - time.time()) if self.running else self.left

    def progress(self):
        d = self.duration()
        return clamp(1.0 - self.remaining() / d, 0.0, 1.0) if d else 0.0

    def toggle(self):
        if self.running:
            self.left, self.running = self.remaining(), False
        else:
            self.end_at, self.running = time.time() + self.left, True

    def reset(self):
        self.running, self.left = False, self.duration()

    def skip(self):
        self._next(False)

    def update(self):
        if self.running and time.time() >= self.end_at:
            self._next(True)

    def _next(self, finished):
        if self.mode == "focus":
            if finished:
                self.session += 1
                s, m = focus_stats(self.cfg)
                cset(self.cfg, ("stats", "sessions"), s + 1)
                cset(self.cfg, ("stats", "focus_min"), m + int(self.duration("focus") / 60))
                save_config(self.cfg)
            self.mode = "long" if (finished and self.session % 4 == 0) else "short"
        else:
            self.mode = "focus"
        self.running, self.left = False, self.duration()
        if finished:
            self.on_event(self.mode)


class Water:
    def __init__(self, cfg, on_remind):
        self.cfg, self.on_remind, self.next_at = cfg, on_remind, 0.0

    def _day(self):
        today = datetime.date.today().isoformat()
        if cget(self.cfg, "water", "date") != today:
            cset(self.cfg, ("water", "date"), today)
            cset(self.cfg, ("water", "ml"), 0)
            save_config(self.cfg)

    def ml(self):
        self._day()
        return int(cget(self.cfg, "water", "ml"))

    def goal_ml(self):
        return int(float(cget(self.cfg, "water", "goal")) * 1000)

    def bottle(self):
        return max(50, int(cget(self.cfg, "water", "bottle")))

    def progress(self):
        g = self.goal_ml()
        return clamp(self.ml() / float(g), 0.0, 1.0) if g else 0.0

    def add(self, amount):
        cset(self.cfg, ("water", "ml"), max(0, self.ml() + int(amount)))
        save_config(self.cfg)
        self.next_at = 0.0

    def reset(self):
        cset(self.cfg, ("water", "ml"), 0)
        save_config(self.cfg)
        self.next_at = 0.0

    def reschedule(self):
        self.next_at = 0.0

    def interval_min(self):
        bottles = max(1, math.ceil(self.goal_ml() / float(self.bottle())))
        span = max(1, (int(cget(self.cfg, "water", "until")) - int(cget(self.cfg, "water", "from"))) * 60)
        return max(20.0, span / float(bottles))

    def in_window(self):
        now = datetime.datetime.now()
        hour = now.hour + now.minute / 60.0
        return int(cget(self.cfg, "water", "from")) <= hour < int(cget(self.cfg, "water", "until"))

    def update(self):
        if (not cget(self.cfg, "water", "reminders") or self.ml() >= self.goal_ml()
                or not self.in_window()):
            self.next_at = 0.0
            return
        now = time.time()
        if self.next_at == 0.0:
            self.next_at = now + self.interval_min() * 60
        elif now >= self.next_at:
            self.next_at = now + self.interval_min() * 60
            self.on_remind()

    def next_text(self):
        if not cget(self.cfg, "water", "reminders"):
            return "Erinnerungen sind aus."
        if self.ml() >= self.goal_ml():
            return "Tagesziel erreicht."
        if not self.in_window():
            return "Außerhalb der aktiven Zeit."
        return "Nächste Erinnerung um %s." % time.strftime("%H:%M", time.localtime(self.next_at)) \
            if self.next_at else ""


# ---------------------------------------------------------------- Die Notch
class Notch(QWidget):
    def __init__(self, cfg, volume, lyrics):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.cfg = cfg
        self.volume = volume
        self.lyrics = lyrics
        self.worker = None

        self.t = 0.0
        self.target = 0
        self.page = PAGE_PLAYER
        self.peek_until = 0.0
        self.leave_at = None
        self.modal_open = False
        self.eye_dx = 0.0
        self.seeking = False
        self.shelf_tab = 0
        self.clips = []
        self.state = dict(has_session=False, title="", artist="", album="", playing=False, cover=None)
        self.key = None
        self.tl = dict(pos=0.0, dur=0.0, stamp=time.time(), playing=False)
        self.lines, self.lyr_times = [], []
        self.cur_idx, self.cur_line = -1, ""
        self._pill_line, self._pill_prev, self._pill_t0 = "", "", 0.0
        self.click_open = False
        self.hud = None
        self._hud_last = {"vol": None, "caps": None, "lang": None, "bat": None}
        self._low_warned = False
        self._poll_n = 0
        self.pomo = Pomodoro(self.cfg, self._pomo_event)
        self.water = Water(self.cfg, self._water_remind)
        self.accent = accent_from(None)
        self.cover_big = rounded_pixmap(None, 96, 16)
        self.cover_mid = rounded_pixmap(None, 56, 12)
        self.cover_small = rounded_pixmap(None, 22, 6)
        self._scr = self.target_screen().geometry()

        # Federn: Aufklappen, Pillen-Größe, Seiten-Größe
        self.s_t = Spring(0.0, k=520.0, zeta=0.88, eps=0.0008)
        self.csize = SizeSpring(230, 34, k=300.0)
        self.esize = SizeSpring(*PAGES[0], k=360.0)
        self._apply_speed()
        self.motion = QTimer(self)
        self.motion.setTimerType(Qt.PreciseTimer)
        self.motion.setInterval(8)
        self.motion.timeout.connect(self._motion_step)
        self._last_step = time.perf_counter()

        self.container = QWidget(self)
        self.pages = []
        self._build_player()
        self._build_lyrics()
        self._build_settings()
        self._build_shelf()
        self._build_today()
        self._build_pomo()
        self._build_water()
        self._translate_ui()
        self.nav_prev = make_button(self.container, 0, 0, 22, 26, radius=11, icon="chev_l")
        self.nav_next = make_button(self.container, 0, 0, 22, 26, radius=11, icon="chev_r")
        self.nav_prev.clicked.connect(lambda: self._nav(-1))
        self.nav_next.clicked.connect(lambda: self._nav(1))
        for k, pg in enumerate(self.pages):
            pg.resize(*PAGES[k])
            pg.setVisible(k == 0)
        self.veil = Veil(self)
        self.veil.raise_()
        self.container.setVisible(False)
        self.veil.setVisible(False)
        self._update_nav_buttons()

        self._refresh_shelf()
        self._refresh_tasks()
        self._apply()
        self._refresh_texts()

        QApplication.clipboard().dataChanged.connect(self._clip_changed)

        self.poll = QTimer(self)
        self.poll.timeout.connect(self._tick)
        self.poll.start(120)
        self.vis_timer = QTimer(self)
        self.vis_timer.timeout.connect(self._check_visibility)
        self.vis_timer.start(500)
        self.paint_timer = QTimer(self)
        self.paint_timer.timeout.connect(self._anim_frame)
        self.paint_timer.start(33)

    # ------------------------------------------------ Animation
    def _kick(self):
        if not self.motion.isActive():
            self._last_step = time.perf_counter()
            self.motion.start()

    def _motion_step(self):
        now = time.perf_counter()
        dt = min(now - self._last_step, 0.05)
        self._last_step = now
        self.s_t.step(dt)
        self.csize.step(dt)
        self.esize.step(dt)
        self.t = self.s_t.x
        if self.s_t.settled() and self.csize.settled() and self.esize.settled():
            self.s_t.snap()
            self.csize.snap()
            self.esize.snap()
            self.t = self.s_t.x
            self.motion.stop()
        self._apply()

    def _go(self, target):
        if target == self.target:
            return
        self.target = target
        self.s_t.target = float(target)
        self._kick()

    # ------------------------------------------------ Seiten bauen
    def _build_player(self):
        pg = QWidget(self.container)
        self.pages.append(pg)
        self.p_cover = QLabel(pg)
        self.p_cover.setGeometry(28, 34, 96, 96)
        self.p_title = make_label(pg, 140, 38, 320, 26, size=13, bold=True)
        self.p_sub = make_label(pg, 140, 66, 320, 20, size=9, color="#b8bcc8")
        self.p_gear = make_button(pg, 458, 32, 32, 28, icon="gear")
        self.p_gear.clicked.connect(lambda: self._set_page(PAGE_SETTINGS))

        self.p_pos = make_label(pg, 28, 138, 48, 18, "0:00", size=8, color="#c8ccd8")
        self.p_seek = QSlider(Qt.Horizontal, pg)
        self.p_seek.setGeometry(80, 140, 356, 14)
        self.p_seek.setRange(0, 1000)
        self.p_seek.setStyleSheet(SLIDER_STYLE)
        self.p_seek.sliderPressed.connect(lambda: setattr(self, "seeking", True))
        self.p_seek.sliderReleased.connect(self._seek_released)
        self.p_rem = make_label(pg, 440, 138, 52, 18, "-0:00", size=8, color="#c8ccd8",
                                align=Qt.AlignRight | Qt.AlignVCenter)

        self.p_lyr = make_button(pg, 28, 164, 38, 30, icon="bubble")
        self.p_lyr.clicked.connect(lambda: self._set_page(PAGE_LYRICS))
        self.btn_prev = make_button(pg, 190, 164, 46, 30, icon="prev")
        self.btn_play = make_button(pg, 244, 164, 46, 30, icon="play")
        self.btn_next = make_button(pg, 298, 164, 46, 30, icon="next")
        self.btn_prev.clicked.connect(lambda: self._cmd("prev"))
        self.btn_play.clicked.connect(lambda: self._cmd("toggle"))
        self.btn_next.clicked.connect(lambda: self._cmd("next"))

        self.p_spk = IconLabel(pg, "speaker")
        self.p_spk.setGeometry(392, 168, 24, 22)
        self.p_vol = QSlider(Qt.Horizontal, pg)
        self.p_vol.setGeometry(422, 172, 76, 14)
        self.p_vol.setRange(0, 100)
        self.p_vol.setStyleSheet(SLIDER_STYLE)
        self._vol_sync = False
        self.p_vol.valueChanged.connect(self._vol_changed)
        if not self.volume.available():
            self.p_spk.hide()
            self.p_vol.hide()

    def _build_lyrics(self):
        pg = QWidget(self.container)
        self.pages.append(pg)
        self.l_cover = QLabel(pg)
        self.l_cover.setGeometry(28, 32, 56, 56)
        self.l_title = make_label(pg, 96, 34, 370, 24, size=12, bold=True)
        self.l_sub = make_label(pg, 96, 58, 370, 20, size=9, color="#b8bcc8")
        self.l_back = make_button(pg, 476, 32, 32, 28, checkable=True, icon="bubble")
        self.l_back.setChecked(True)
        self.l_back.clicked.connect(lambda: self._set_page(PAGE_PLAYER))
        self.l_view = LyricsView(pg)
        self.l_view.setGeometry(28, 98, 464, 100)
        self.l_view.set_lines([], "Keine Musik")

    def _build_settings(self):
        pg = QWidget(self.container)
        self.pages.append(pg)
        self.s_page = pg
        names = ("Allgemein", "Aussehen", "Maskottchen", "Musik", "Seiten", "HUD & Töne",
                 "Pomodoro", "Wasser", "Shelf", "Apps")
        self.cat_list = QListWidget(pg)
        self.cat_list.setGeometry(14, 28, 150, 336)
        self.cat_list.setStyleSheet(CAT_STYLE)
        self.cat_list.setFocusPolicy(Qt.NoFocus)
        for n in names:
            self.cat_list.addItem(n)
        self.panes = []
        for _ in names:
            w = QWidget(pg)
            w.setGeometry(176, 30, 500, 400)
            self.panes.append(w)
        b_done = make_button(pg, 22, 372, 134, 28, "Fertig", radius=10)
        b_done.clicked.connect(lambda: self._set_page(PAGE_PLAYER))
        b_quit = make_button(pg, 22, 404, 134, 28, "Beenden", radius=10)
        b_quit.setStyleSheet(DANGER_STYLE)
        b_quit.clicked.connect(QApplication.quit)
        self._fill_panes()
        self.cat_list.currentRowChanged.connect(self._set_cat)
        self.cat_list.setCurrentRow(0)
        self._set_cat(0)

    def _build_shelf(self):
        pg = QWidget(self.container)
        self.pages.append(pg)
        make_label(pg, 40, 32, 80, 26, "Shelf", size=13, bold=True)
        self.sh_count = make_label(pg, 112, 35, 200, 20, "", size=9, color="#9aa3b8")
        self.sh_tab_files = make_button(pg, 478, 30, 40, 28, radius=10, checkable=True, icon="folder")
        self.sh_tab_clip = make_button(pg, 524, 30, 40, 28, radius=10, checkable=True, icon="clipboard")
        self.sh_tab_files.clicked.connect(lambda: self._set_shelf_tab(0))
        self.sh_tab_clip.clicked.connect(lambda: self._set_shelf_tab(1))

        self.shelf_list = ShelfList(pg)
        self.shelf_list.setGeometry(40, 72, 520, 122)
        self.shelf_list.itemDoubleClicked.connect(self._open_shelf_item)
        self.shelf_list.customContextMenuRequested.connect(self._shelf_menu)
        self.clip_list = QListWidget(pg)
        self.clip_list.setGeometry(40, 72, 520, 122)
        self.clip_list.setStyleSheet(TASK_LIST_STYLE)
        self.clip_list.itemClicked.connect(self._clip_clicked)
        self.sh_hint = make_label(pg, 40, 112, 520, 30, "", size=10, color="#7f8aa8", align=Qt.AlignCenter)
        self.sh_clear = make_button(pg, 438, 202, 122, 28, "Alles löschen", radius=10)
        self.sh_clear.setStyleSheet(DANGER_STYLE)
        self.sh_clear.clicked.connect(self._shelf_clear)
        self._set_shelf_tab(0)

    def _build_today(self):
        pg = QWidget(self.container)
        self.pages.append(pg)
        make_label(pg, 40, 32, 90, 26, "Heute", size=13, bold=True)
        self.td_date = make_label(pg, 122, 35, 160, 20, "", size=9, color="#9aa3b8")
        self.task_list = QListWidget(pg)
        self.task_list.setGeometry(40, 72, 310, 132)
        self.task_list.setStyleSheet(TASK_LIST_STYLE)
        self.task_list.itemChanged.connect(self._task_toggled)
        divider = QWidget(pg)
        divider.setGeometry(367, 74, 1, 128)
        divider.setStyleSheet("background:rgba(255,255,255,0.12);")
        self.week = WeekStrip(pg)
        self.week.setGeometry(384, 68, 196, 54)
        self.td_summary = make_label(pg, 384, 138, 196, 66, "", size=10,
                                     align=Qt.AlignLeft | Qt.AlignTop)
        self.td_summary.setWordWrap(True)
        b_add = make_button(pg, 40, 216, 122, 30, "+ Aufgabe", radius=10)
        b_add.clicked.connect(self._add_task)
        b_clear = make_button(pg, 170, 216, 160, 30, "Erledigte löschen", radius=10)
        b_clear.clicked.connect(self._clear_done)

    # ------------------------------------------------ Einstellungen
    def target_screen(self):
        name = self.cfg.get("monitor", "")
        for s in QApplication.screens():
            if s.name() == name:
                return s
        return QApplication.primaryScreen()

    def _set_cat(self, i):
        for k, pane in enumerate(self.panes):
            pane.setVisible(k == i)

    def _refresh_settings(self):
        for h in self.pane_helpers:
            h.refresh()
        for b in self.mon_btns:
            b.deleteLater()
        self.mon_btns = []
        current = self.target_screen()
        for i, s in enumerate(QApplication.screens()):
            b = make_button(self.mon_box, Pane.X0 + i * 52, self.mon_y, 46, 28, str(i + 1), radius=8,
                            checkable=True)
            b.setChecked(s is current)
            b.clicked.connect(lambda _=False, sc=s: self._set_monitor(sc))
            b.show()
            self.mon_btns.append(b)
        for k, c in self.cards.items():
            c.set_selected(cget(self.cfg, "style") == k)
        self._refresh_apps()

    def _refresh_apps(self):
        hidden = [a.lower() for a in self.cfg.get("hidden_apps", [])]
        names = sorted(visible_apps() | set(hidden))
        self.app_list.blockSignals(True)
        self.app_list.clear()
        for n in names:
            it = QListWidgetItem(n)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if n in hidden else Qt.Unchecked)
            self.app_list.addItem(it)
        self.app_list.blockSignals(False)

    def _app_toggled(self, item):
        name = item.text().lower()
        apps = [a.lower() for a in self.cfg.get("hidden_apps", [])]
        if item.checkState() == Qt.Checked and name not in apps:
            apps.append(name)
        elif item.checkState() != Qt.Checked and name in apps:
            apps.remove(name)
        self.cfg["hidden_apps"] = apps
        save_config(self.cfg)

    def _set_monitor(self, screen):
        self.cfg["monitor"] = screen.name()
        save_config(self.cfg)
        self._scr = self.target_screen().geometry()
        for b, s in zip(self.mon_btns, QApplication.screens()):
            b.setChecked(s is screen)
        self._apply()

    def _set_style(self, kind):
        self.cfg["style"] = kind
        save_config(self.cfg)
        for k, c in self.cards.items():
            c.set_selected(k == kind)
        self._apply()

    def open_settings(self):
        self.show()
        self._set_page(PAGE_SETTINGS)
        self._go(1)

    # ------------------------------------------------ Seiten & Navigation
    def nav_pages(self):
        pages = [PAGE_PLAYER]
        if cget(self.cfg, "pages_shelf"):
            pages.append(PAGE_SHELF)
        if cget(self.cfg, "pages_today"):
            pages.append(PAGE_TODAY)
        if cget(self.cfg, "pages_pomo"):
            pages.append(PAGE_POMO)
        if cget(self.cfg, "pages_water"):
            pages.append(PAGE_WATER)
        return pages

    def _nav(self, step):
        pages = self.nav_pages()
        if self.page not in pages:
            self._set_page(PAGE_PLAYER)
            return
        self._set_page(pages[(pages.index(self.page) + step) % len(pages)])

    def _update_nav_buttons(self):
        show = self.page in self.nav_pages() and len(self.nav_pages()) > 1
        self.nav_prev.setVisible(show)
        self.nav_next.setVisible(show)
        self.nav_prev.raise_()
        self.nav_next.raise_()

    def _set_page(self, i):
        self.page = i
        for k, pg in enumerate(self.pages):
            pg.setVisible(k == i)
        if self.esize.go(*PAGES[i]):
            self._kick()
        if i == PAGE_SETTINGS:
            self._refresh_settings()
        elif i == PAGE_PLAYER and self.volume.available():
            self._vol_sync = True
            self.p_vol.setValue(self.volume.get())
            self._vol_sync = False
        elif i == PAGE_LYRICS:
            self.l_view.jump(self.cur_idx)
        elif i == PAGE_SHELF:
            self._refresh_shelf()
        elif i == PAGE_TODAY:
            self._refresh_tasks()
        elif i == PAGE_POMO:
            self._refresh_pomo()
        elif i == PAGE_WATER:
            self._refresh_water()
        self._update_nav_buttons()
        self._apply()

    def _cmd(self, c, arg=None):
        if self.worker:
            self.worker.send(c, arg)

    def _seek_released(self):
        self.seeking = False
        dur = self.tl["dur"]
        if dur > 0:
            self._cmd("seek", self.p_seek.value() / 1000.0 * dur)

    def _vol_changed(self, v):
        if not self._vol_sync:
            self.volume.set(v)

    # ------------------------------------------------ Shelf & Zwischenablage
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and self.cfg.get("pages_shelf", True):
            e.acceptProposedAction()
            self.peek_until = time.time() + 6
            self._set_page(PAGE_SHELF)
            self._set_shelf_tab(0)
            self._go(1)
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()
        self.peek_until = time.time() + 6

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        self.add_to_shelf(paths)
        e.acceptProposedAction()
        self.peek_until = time.time() + 2

    def add_to_shelf(self, paths):
        shelf = self.cfg.setdefault("shelf", [])
        for p in paths:
            if p and os.path.exists(p) and p not in shelf:
                shelf.append(p)
        save_config(self.cfg)
        self._refresh_shelf()

    def _refresh_shelf(self):
        shelf = [p for p in self.cfg.get("shelf", []) if os.path.exists(p)]
        if shelf != self.cfg.get("shelf", []):
            self.cfg["shelf"] = shelf
            save_config(self.cfg)
        provider = QFileIconProvider()
        self.shelf_list.clear()
        f = self.shelf_list.font()
        for p in shelf:
            name = os.path.basename(p) or p
            if os.path.isdir(p):
                info = "Ordner"
            else:
                try:
                    info = fmt_size(os.path.getsize(p))
                except OSError:
                    info = ""
            if p.lower().endswith(IMAGE_EXT):
                pix = QPixmap(p)
                icon = QIcon(pix.scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation)) \
                    if not pix.isNull() else provider.icon(QFileInfo(p))
            else:
                icon = provider.icon(QFileInfo(p))
            it = QListWidgetItem(icon, elide(name, f, 92, Qt.ElideMiddle) + "\n" + info)
            it.setData(Qt.UserRole, p)
            it.setToolTip(p)
            it.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.shelf_list.addItem(it)
        self._update_shelf_labels()

    def _clip_changed(self):
        md = QApplication.clipboard().mimeData()
        if md is None or not md.hasText():
            return
        if md.hasFormat("ExcludeClipboardContentFromMonitorProcessing"):
            return   # z. B. Passwort-Manager: nicht speichern
        txt = md.text().strip()[:500]
        if not txt:
            return
        if txt in self.clips:
            self.clips.remove(txt)
        self.clips.insert(0, txt)
        del self.clips[int(cget(self.cfg, "clip_limit")):]
        self._refresh_clips()

    def _refresh_clips(self):
        self.clip_list.clear()
        f = self.clip_list.font()
        for txt in self.clips:
            it = QListWidgetItem(elide(txt.replace("\n", "  ·  "), f, 480))
            it.setData(Qt.UserRole, txt)
            self.clip_list.addItem(it)
        self._update_shelf_labels()

    def _clip_clicked(self, item):
        QApplication.clipboard().setText(item.data(Qt.UserRole))

    def _open_shelf_item(self, item):
        try:
            os.startfile(item.data(Qt.UserRole))
        except Exception:
            pass

    def _shelf_menu(self, pos):
        item = self.shelf_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        menu.addAction("Öffnen").triggered.connect(lambda: self._open_shelf_item(item))
        menu.addAction("Aus dem Shelf entfernen").triggered.connect(lambda: self._remove_shelf(item))
        self.modal_open = True
        menu.exec(self.shelf_list.mapToGlobal(pos))
        self.modal_open = False

    def _remove_shelf(self, item):
        p = item.data(Qt.UserRole)
        if p in self.cfg["shelf"]:
            self.cfg["shelf"].remove(p)
            save_config(self.cfg)
        self._refresh_shelf()

    def _shelf_clear(self):
        if self.shelf_tab == 0:
            self.cfg["shelf"] = []
            save_config(self.cfg)
            self._refresh_shelf()
        else:
            self.clips = []
            self._refresh_clips()

    def _set_shelf_tab(self, tab):
        self.shelf_tab = tab
        self.sh_tab_files.setChecked(tab == 0)
        self.sh_tab_clip.setChecked(tab == 1)
        self.shelf_list.setVisible(tab == 0)
        self.clip_list.setVisible(tab == 1)
        self._update_shelf_labels()

    def _update_shelf_labels(self):
        if self.shelf_tab == 0:
            n = self.shelf_list.count()
            self.sh_count.setText("%d Objekt%s" % (n, "" if n == 1 else "e"))
            self.sh_hint.setText("Dateien hierher ziehen" if n == 0 else "")
        else:
            n = self.clip_list.count()
            self.sh_count.setText("%d Eintr%s" % (n, "ag" if n == 1 else "äge"))
            self.sh_hint.setText("Noch nichts kopiert" if n == 0 else "")
        self.sh_hint.raise_()

    # ------------------------------------------------ Heute (Aufgaben)
    def _refresh_tasks(self):
        tasks = self.cfg.get("tasks", [])
        self.task_list.blockSignals(True)
        self.task_list.clear()
        for t in tasks:
            it = QListWidgetItem(t["text"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if t.get("done") else Qt.Unchecked)
            self.task_list.addItem(it)
        self.task_list.blockSignals(False)
        today = datetime.date.today()
        self.td_date.setText("%s %d %s" % (DAYS[today.weekday()], today.day, MONTHS[today.month - 1]))
        self.week.update()
        self._update_task_summary()

    def _update_task_summary(self):
        tasks = self.cfg.get("tasks", [])
        open_tasks = [t for t in tasks if not t.get("done")]
        if not tasks:
            text = "Keine Aufgaben.<br><span style='color:#7f8aa8'>Mit „+ Aufgabe“ hinzufügen.</span>"
        elif not open_tasks:
            text = "<b>Alles erledigt</b>"
        else:
            nxt = elide(open_tasks[0]["text"], self.td_summary.font(), 180)
            nxt = nxt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text = ("<b>%d Aufgabe%s offen</b><br><span style='color:#9aa3b8'>Nächste: %s</span>"
                    % (len(open_tasks), "" if len(open_tasks) == 1 else "n", nxt))
        self.td_summary.setText(text)

    def _task_toggled(self, item):
        row = self.task_list.row(item)
        tasks = self.cfg.get("tasks", [])
        if 0 <= row < len(tasks):
            tasks[row]["done"] = item.checkState() == Qt.Checked
            save_config(self.cfg)
            self._update_task_summary()

    def _add_task(self):
        self.modal_open = True
        text, ok = QInputDialog.getText(None, "Neue Aufgabe", "Was ist zu tun?")
        self.modal_open = False
        if ok and text.strip():
            self.cfg.setdefault("tasks", []).append({"text": text.strip(), "done": False})
            save_config(self.cfg)
            self._refresh_tasks()

    def _clear_done(self):
        self.cfg["tasks"] = [t for t in self.cfg.get("tasks", []) if not t.get("done")]
        save_config(self.cfg)
        self._refresh_tasks()

    # ------------------------------------------------ Musik-Daten
    def on_media(self, d):
        old_key = self.key
        self.state = d
        pix = None
        if d.get("cover"):
            pix = QPixmap()
            pix.loadFromData(d["cover"])
        self.cover_big = rounded_pixmap(pix, 96, 16)
        self.cover_mid = rounded_pixmap(pix, 56, 12)
        self.cover_small = rounded_pixmap(pix, 22, 6)
        self.accent = accent_from(pix)
        self.key = (d["title"], d["artist"]) if d["has_session"] else None

        if self.key != old_key:
            self.lines, self.lyr_times = [], []
            self.cur_idx, self.cur_line = -1, ""
            has_track = bool(self.key and d["title"])
            self.l_view.set_lines([], "Songtext wird geladen …" if has_track else "Keine Musik")
            self.tl = dict(pos=0.0, dur=0.0, stamp=time.time(), playing=d["playing"])
            if has_track:
                QTimer.singleShot(1200, lambda k=self.key: self._fetch_lyrics(k))
            if (self.cfg.get("peek_on_change", True) and d["has_session"]
                    and d["playing"] and self.key):
                self.peek_until = time.time() + 3.5
                if self.page not in (PAGE_PLAYER, PAGE_LYRICS):
                    self._set_page(PAGE_PLAYER)
        self._refresh_texts()
        self.update()

    def on_timeline(self, pos, dur, playing):
        self.tl = dict(pos=pos, dur=dur, stamp=time.time(), playing=playing)

    def _fetch_lyrics(self, key):
        if key != self.key:
            return
        self.lyrics.fetch(key, key[0], key[1], self.tl["dur"] or None)

    def on_lyrics(self, key, lines):
        if key != self.key:
            return
        self.lines = lines
        self.lyr_times = [t for t, _ in lines]
        self.l_view.set_lines(lines, "" if lines else "Keine synchronisierten Songtexte gefunden.")

    def current_pos(self):
        tl = self.tl
        pos = tl["pos"]
        if tl["playing"]:
            pos += time.time() - tl["stamp"]
        if tl["dur"] > 0:
            pos = clamp(pos, 0, tl["dur"])
        return pos

    def _refresh_texts(self):
        d = self.state
        has = d["has_session"] and d["title"]
        title = d["title"] if has else "Keine Musik"
        sub = " – ".join(x for x in (d["artist"], d["album"]) if x) if has else time.strftime("%H:%M")
        for lab, text, w in ((self.p_title, title, 320), (self.p_sub, sub, 320),
                             (self.l_title, title, 370), (self.l_sub, sub, 370)):
            lab.setText(elide(text, lab.font(), w))
        self.p_cover.setPixmap(self.cover_big)
        self.l_cover.setPixmap(self.cover_mid)
        self.btn_play.set_kind("pause" if d["playing"] else "play")
        for b in (self.btn_prev, self.btn_play, self.btn_next):
            b.setEnabled(d["has_session"])

    # ------------------------------------------------ Größe, Position
    def _coll_target(self):
        d = self.state
        if self.hud_active():
            return (310, 34)
        if d["playing"]:
            if self.cfg.get("lyric_in_pill", True) and self.cur_line:
                return (420, 34)
            return (230, 34)
        if self.pomo.running:
            return (170, 34)
        if cget(self.cfg, "minimal"):
            return (130, 26)
        idle = cget(self.cfg, "idle")
        if idle == "time":
            w = 190 + (92 if cget(self.cfg, "show_date") else 0)
            if cget(self.cfg, "ring") == "off":
                w -= 26
            return (w, 34)
        return {"face": (150, 34), "none": (110, 24)}.get(idle, (190, 34))

    def _floating(self):
        return self.cfg.get("style", "classic") == "floating"

    def _cr(self):
        """Breite der geschwungenen Übergänge links und rechts (nur Classic)."""
        return 0 if self._floating() else CORNER

    def _apply(self):
        t = clamp(self.t, 0.0, 1.08)
        cw, ch = self.csize.w, self.csize.h
        ew, eh = self.esize.w, self.esize.h
        wb = max(40, int(round(cw + (ew - cw) * t)))
        h = max(16, int(round(ch + (eh - ch) * t)))
        cr = self._cr()
        W = wb + 2 * cr
        scr = self._scr
        x = scr.x() + (scr.width() - W) // 2
        y = scr.y() + (10 if self._floating() else 0)
        self.setGeometry(x, y, W, h)
        self.container.setGeometry(cr, 0, wb, h)
        pw = PAGES[self.page][0]
        self.pages[self.page].move((wb - pw) // 2, 0)
        self.nav_prev.move(4, h // 2 - 13)
        self.nav_next.move(wb - 26, h // 2 - 13)

        content = clamp((t - 0.42) / 0.5, 0.0, 1.0)
        show_container = t > 0.38
        if self.container.isVisible() != show_container:
            self.container.setVisible(show_container)
        veil_on = show_container and content < 1.0
        self.veil.alpha = 1.0 - content
        self.veil.setGeometry(0, 0, W, h)
        if self.veil.isVisible() != veil_on:
            self.veil.setVisible(veil_on)
            if veil_on:
                self.veil.raise_()
        if veil_on:
            self.veil.update()
        self.update()

    # ------------------------------------------------ Takt
    def _tick(self):
        now = time.time()
        scr = self.target_screen().geometry()
        if scr != self._scr:
            self._scr = scr
            self._apply()
        pos = self.current_pos()
        self.pomo.update()
        self.water.update()
        self._poll_hud()
        if self.csize.go(*self._coll_target()):
            self._kick()

        if self.isVisible():
            inside = self.frameGeometry().adjusted(-6, -14, 6, 8).contains(QCursor.pos())
            if not inside:
                self.click_open = False
            opened = inside if cget(self.cfg, "open_mode") == "hover" else (inside and self.click_open)
            want = (opened or now < self.peek_until or self.page == PAGE_SETTINGS
                    or self.modal_open)
            if want:
                self.leave_at = None
                self._go(1)
            elif self.target == 1:
                if self.leave_at is None:
                    self.leave_at = now
                elif now - self.leave_at > 0.35:
                    self._go(0)
            if self.target == 0 and self.t < 0.02 and self.page != PAGE_PLAYER:
                self._set_page(PAGE_PLAYER)

        if self.t > 0.45:
            if self.page == PAGE_PLAYER:
                dur = self.tl["dur"]
                if not self.seeking:
                    self.p_seek.blockSignals(True)
                    self.p_seek.setValue(int(pos / dur * 1000) if dur > 0 else 0)
                    self.p_seek.blockSignals(False)
                self.p_pos.setText(fmt_time(pos))
                self.p_rem.setText("-" + fmt_time(dur - pos) if dur > 0 else "")
                if not self.state["has_session"]:
                    self._refresh_texts()
            elif self.page == PAGE_POMO:
                self._refresh_pomo()
            elif self.page == PAGE_WATER:
                self._refresh_water()

    def _anim_frame(self):
        now = time.time()
        # Songtext-Zeile bestimmen (mit Vorlauf)
        if self.lyr_times:
            pos = self.current_pos() + float(self.cfg.get("lyric_offset", 0.3))
            self.cur_idx = bisect.bisect_right(self.lyr_times, pos) - 1
        else:
            self.cur_idx = -1
        self.cur_line = self.lines[self.cur_idx][1] if self.cur_idx >= 0 else ""
        if self.cur_line != self._pill_line:
            self._pill_prev, self._pill_line, self._pill_t0 = self._pill_line, self.cur_line, now
        if self.page == PAGE_LYRICS:
            self.l_view.set_index(self.cur_idx)

        cur = QCursor.pos()
        dxt = clamp((cur.x() - (self.x() + self.width() / 2.0)) / 80.0, -4.0, 4.0)
        self.eye_dx += (dxt - self.eye_dx) * 0.25
        if self.isVisible() and self.t < 0.35:
            self.update()

    def _check_visibility(self):
        exe = foreground_exe()
        hidden_apps = [a.lower() for a in self.cfg.get("hidden_apps", [])]
        protected = self.page == PAGE_SETTINGS or self.modal_open
        hide = exe in hidden_apps and exe != own_exe() and not protected
        if (not hide and not protected and cget(self.cfg, "hide_fullscreen")
                and exe != own_exe() and foreground_fullscreen()):
            hide = True
        if hide and self.isVisible():
            self.hide()
        elif not hide and not self.isVisible():
            self.show()

    # ------------------------------------------------ Zeichnen
    def _shape(self, W, h):
        t = clamp(self.t, 0.0, 1.0)
        path = QPainterPath()
        if self._floating():
            rr = min(h / 2.0, 14 + 14 * t)
            path.addRoundedRect(QRectF(0, 0, W, h), rr, rr)
        else:
            cr = float(self._cr())
            body = W - 2 * cr
            r = min(11 + 15 * t, body / 2.0, h - cr)
            path.moveTo(0, 0)
            path.lineTo(W, 0)
            path.quadTo(W - cr, 0, W - cr, cr)           # geschwungener Übergang rechts oben
            path.lineTo(W - cr, h - r)
            path.quadTo(W - cr, h, W - cr - r, h)
            path.lineTo(cr + r, h)
            path.quadTo(cr, h, cr, h - r)
            path.lineTo(cr, cr)
            path.quadTo(cr, 0, 0, 0)                      # geschwungener Übergang links oben
            path.closeSubpath()
        return path

    def _paint_background(self, p, w, h, opacity=1.0):
        t = clamp(self.t, 0.0, 1.0)
        path = self._shape(w, h)
        glass = self.cfg.get("glass", False)
        p.setOpacity(opacity)
        p.fillPath(path, QColor(0, 0, 0, 205 if glass else 255))
        if t > 0 and self.page != PAGE_SETTINGS:
            p.setOpacity(opacity * t)
            g = QLinearGradient(0, 0, 0, h)
            g.setColorAt(0, QColor(0, 0, 0, 0 if glass else 255))
            c = QColor(self.accent)
            c.setAlpha(170 if glass else 255)
            g.setColorAt(1, c)
            p.fillPath(path, QBrush(g))
        p.setOpacity(1.0)
        return path

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, h = self.width(), self.height()
        t = self.t
        path = self._paint_background(p, W, h, 1.0)
        glass = self.cfg.get("glass", False)

        if glass or self._floating():
            p.setPen(QPen(QColor(255, 255, 255, 38 if glass else 22), 1))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        if t < 0.35:
            cr = self._cr()
            p.setOpacity(clamp(1.0 - t / 0.35, 0.0, 1.0))
            p.setClipPath(path)
            p.translate(cr, 0)
            self._paint_collapsed(p, W - 2 * cr, h)
            p.resetTransform()
            p.setClipping(False)
            p.setOpacity(1.0)

        navs = self.nav_pages()
        if t > 0.6 and self.page in navs and len(navs) > 1:
            p.setOpacity(clamp((t - 0.6) / 0.4, 0.0, 1.0))
            p.setPen(Qt.NoPen)
            n = len(navs)
            x = W / 2.0 - (n - 1) * 7
            for pg in navs:
                if pg == self.page:
                    p.setBrush(QColor(255, 255, 255))
                    p.drawRoundedRect(QRectF(x - 6, h - 10, 12, 5), 2.5, 2.5)
                else:
                    p.setBrush(QColor(255, 255, 255, 90))
                    p.drawEllipse(QRectF(x - 2.5, h - 10, 5, 5))
                x += 14
            p.setOpacity(1.0)

    def _paint_collapsed(self, p, w, h):
        d = self.state
        now = time.time()
        if self.hud_active():
            self._paint_hud(p, w, h, self.hud)
            return
        if d["playing"]:
            if self.cfg.get("lyric_in_pill", True) and self._pill_line:
                draw_icon(p, "note", QRectF(14, (h - 14) / 2.0, 14, 14), QColor(150, 160, 190))
                f = QFont("Segoe UI", 10)
                f.setBold(True)
                p.setFont(f)
                p.setPen(QColor(255, 255, 255))
                base = p.opacity()
                a = clamp((now - self._pill_t0) / 0.22, 0.0, 1.0)
                e = a * a * (3 - 2 * a)
                if self._pill_prev and e < 1.0:      # alte Zeile gleitet nach oben und blendet aus
                    p.setOpacity(base * (1.0 - e))
                    p.drawText(QRectF(40, -4 * e, w - 80, h), Qt.AlignCenter,
                               elide(self._pill_prev, f, w - 90))
                p.setOpacity(base * e)               # neue Zeile gleitet von unten ein
                p.drawText(QRectF(40, 4 * (1.0 - e), w - 80, h), Qt.AlignCenter,
                           elide(self._pill_line, f, w - 90))
                p.setOpacity(base)
            else:
                p.drawPixmap(14, (h - 22) // 2, self.cover_small)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255))
                for i in range(4):
                    bh = 4 + 10 * abs(math.sin(now * 9 + i * 1.3))
                    p.drawRoundedRect(QRectF(w - 36 + i * 6, (h - bh) / 2, 3, bh), 1.5, 1.5)
            return

        if self.pomo.running:
            col = QColor(255, 120, 100) if self.pomo.mode == "focus" else QColor(90, 200, 150)
            self._paint_ring_text(p, w, h, fmt_time(self.pomo.remaining()), self.pomo.progress(), col)
            return

        idle = cget(self.cfg, "idle")
        if idle == "time":
            ring = cget(self.cfg, "ring")
            txt = time.strftime("%H:%M")
            if cget(self.cfg, "show_date"):
                today = datetime.date.today()
                txt = "%s %d %s  %s" % (DAYS[today.weekday()], today.day, MONTHS[today.month - 1], txt)
            col = QColor(60, 220, 110)
            if ring == "water":
                frac, col = self.water.progress(), QColor(80, 160, 255)
            elif ring == "todo":
                tasks = self.cfg.get("tasks", [])
                frac = (sum(1 for t in tasks if t.get("done")) / float(len(tasks))) if tasks else 0.0
            elif ring == "off":
                frac = None
            else:
                frac = (time.localtime().tm_sec + (now % 1)) / 60.0
            self._paint_ring_text(p, w, h, txt, frac, col)
        elif idle == "face":
            draw_mascot(p, w, h, mascot_cfg(self.cfg), now, self.eye_dx)

    def _apply_speed(self):
        f = 1.7 if cget(self.cfg, "anim_fast") else 1.0
        self.s_t.retune(520.0 * f, 0.88)
        for sp in (self.csize.sw, self.csize.sh):
            sp.retune(300.0 * f, 1.0)
        for sp in (self.esize.sw, self.esize.sh):
            sp.retune(360.0 * f, 1.0)

    def set_cfg(self, path, value):
        if path == ("autostart",):
            set_autostart(bool(value))
            return
        cset(self.cfg, path, value)
        save_config(self.cfg)
        self._on_cfg(path)

    def _on_cfg(self, path):
        key = path[0]
        if key in ("pages_shelf", "pages_today", "pages_pomo", "pages_water"):
            self._update_nav_buttons()
        elif key == "anim_fast":
            self._apply_speed()
        elif key == "pomo" and not self.pomo.running:
            self.pomo.reset()
        elif key == "water":
            self.water.reschedule()
        self._apply()

    def mousePressEvent(self, e):
        if cget(self.cfg, "open_mode") == "click" and self.t < 0.6:
            self.click_open = True
        super().mousePressEvent(e)

    def tr(self, text):
        return LANGUAGE_TEXT.get(self.cfg.get("language", "de"), {}).get(text, text)

    def set_language(self, lang):
        if lang not in ("de", "en", "es", "fr"):
            return
        self.cfg["language"] = lang
        save_config(self.cfg)
        self._translate_ui()

    def _translate_ui(self):
        # Refresh changing page content first, then translate the resulting widgets.
        for refresh_name in ("_refresh_tasks", "_refresh_shelf", "_refresh_pomo", "_refresh_water"):
            refresh = getattr(self, refresh_name, None)
            if callable(refresh):
                try:
                    refresh()
                except Exception:
                    pass
        mapping = LANGUAGE_TEXT.get(self.cfg.get("language", "de"), {})
        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QLabel, QPushButton, QCheckBox)):
                original = widget.property("_notch_original_text")
                if original is None:
                    original = widget.text()
                    widget.setProperty("_notch_original_text", original)
                widget.setText(mapping.get(str(original), str(original)))
        if hasattr(self, "cat_list"):
            for i in range(self.cat_list.count()):
                item = self.cat_list.item(i)
                original = item.data(Qt.UserRole)
                if original is None:
                    original = item.text()
                    item.setData(Qt.UserRole, original)
                item.setText(mapping.get(str(original), str(original)))

    def _fill_panes(self):
        P = [Pane(self, w) for w in self.panes]
        self.pane_helpers = P
        self.mon_btns = []

        # 0 Allgemein
        p = P[0]
        p.language_selector()
        p.toggle(("autostart",), "Mit Windows starten", getter=autostart_enabled)
        p.segmented(("size",), "Größe (Neustart nötig)",
                    (("auto", "Auto"), ("100", "100 %"), ("115", "115 %"), ("130", "130 %"), ("150", "150 %")),
                    width=54)
        p.segmented(("open_mode",), "Notch öffnen", (("hover", "Hover"), ("click", "Klick")), width=70)
        p.segmented(("anim_fast",), "Animationen", ((False, "Normal"), (True, "Schnell")), width=70)
        p.segmented(("idle",), "Wenn nichts läuft",
                    (("time", "Uhrzeit"), ("face", "Gesicht"), ("none", "Aus")), width=70)
        p.segmented(("ring",), "Ring neben der Uhr",
                    (("auto", "Sekunden"), ("water", "Wasser"), ("todo", "Aufgaben"), ("off", "Aus")), width=70)
        p.toggle(("show_date",), "Datum neben der Uhr anzeigen")
        p.toggle(("minimal",), "Minimale Notch (kleiner, wenn nichts läuft)")
        p.toggle(("hide_fullscreen",), "Im Vollbild ausblenden (Spiele, Videos, Folien)")
        make_label(p.w, 0, p.y, 180, 28, "Monitor", size=10)
        self.mon_box, self.mon_y = p.w, p.y
        p.y += 36

        # 1 Aussehen
        p = P[1]
        p.title("Notch-Stil")
        self.cards = {}
        for i, (kind, text) in enumerate((("classic", "Klassisch (am Rand)"), ("floating", "Schwebend (Pille)"))):
            c = StyleCard(p.w, i * 240, p.y, kind, text)
            c.clicked.connect(lambda k=kind: self._set_style(k))
            self.cards[kind] = c
        p.y += 140
        p.toggle(("glass",), "Glas (leicht durchscheinend)")

        # 2 Maskottchen
        p = P[2]
        self.mascot_preview = MascotPreview(p.w, self)
        self.mascot_preview.setGeometry(0, p.y, 480, 56)
        p.y += 62
        p.color_row(("mascot", "body"), "Körperfarbe", MASCOT_COLORS)
        p.segmented(("mascot", "eye_shape"), "Augenform", EYE_SHAPES, width=56)
        p.color_row(("mascot", "eye_color"), "Augenfarbe", EYE_COLORS)
        p.stepper(("mascot", "eye_size"), "Augengröße", 0.1, 0.6, 1.6, "%.1f ×")
        p.stepper(("mascot", "eye_gap"), "Augenabstand", 0.1, 0.6, 1.8, "%.1f ×")
        p.toggles([(("mascot", "blink"), "Blinzeln"), (("mascot", "follow"), "Folgt der Maus")])
        p.toggles([(("mascot", "glow"), "Leuchtende Augen"), (("mascot", "blush"), "Wangen")])
        p.toggle(("mascot", "mouth"), "Lächeln")
        p.button("Als Anzeige für den Leerlauf verwenden", lambda: self._use_face(p))

        # 3 Musik
        p = P[3]
        p.toggle(("lyric_in_pill",), "Songtext in der eingeklappten Notch")
        p.toggle(("peek_on_change",), "Bei Songwechsel kurz aufklappen")
        p.segmented(("lyric_offset",), "Songtext früher anzeigen",
                    ((0.0, "Aus"), (0.3, "0,3 s"), (0.6, "0,6 s"), (1.0, "1 s")), width=62)
        p.note("Hilft, wenn der Text sich etwas spät anfühlt.")

        # 4 Seiten
        p = P[4]
        p.title("Diese Seiten zeigt die Notch")
        p.toggle(("pages_shelf",), "Shelf & Zwischenablage")
        p.toggle(("pages_today",), "Heute (Woche & Aufgaben)")
        p.toggle(("pages_pomo",), "Pomodoro")
        p.toggle(("pages_water",), "Wasser")
        p.note("Mit den Pfeilen links und rechts an der aufgeklappten Notch wechselst du zwischen den Seiten.")

        # 5 HUD & Töne
        p = P[5]
        p.title("Anzeigen in der Notch")
        p.toggle(("hud", "volume"), "Lautstärke")
        p.toggle(("hud", "caps"), "Caps Lock")
        p.toggle(("hud", "lang"), "Eingabesprache")
        p.toggle(("hud", "battery"), "Akku: Netzteil, niedriger Stand")
        p.gap(6)
        p.toggle(("sounds",), "Erinnerungstöne (Pomodoro und Wasser)")
        p.note("Helligkeit, WLAN und Bluetooth fehlen noch.")

        # 6 Pomodoro
        p = P[6]
        p.title("Dauer")
        p.stepper(("pomo", "focus"), "Fokus", 1, 5, 90, "%d min")
        p.stepper(("pomo", "short"), "Kurze Pause", 1, 1, 30, "%d min")
        p.stepper(("pomo", "long"), "Lange Pause", 5, 5, 60, "%d min")
        p.note("Gestartet wird der Timer auf der Pomodoro-Seite. Nach jeder vierten Fokus-Runde gibt es die lange Pause.")

        # 7 Wasser
        p = P[7]
        p.toggle(("water", "reminders"), "Trink-Erinnerungen über den Tag verteilt")
        p.segmented(("water", "goal"), "Tagesziel",
                    ((1.5, "1,5 L"), (2.0, "2 L"), (2.5, "2,5 L"), (3.0, "3 L")), width=62)
        p.stepper(("water", "bottle"), "Flaschengröße", 50, 100, 1000, "%d ml")
        p.stepper(("water", "from"), "Aktiv ab", 1, 0, 23, "%02d:00")
        p.stepper(("water", "until"), "Aktiv bis", 1, 1, 24, "%02d:00")
        p.gap(6)
        p.button("Heutigen Fortschritt zurücksetzen", lambda: self.water.reset(), danger=True)

        # 8 Shelf
        p = P[8]
        p.toggle(("shelf_empty_start",), "Mit leerem Shelf starten (Dateien der letzten Sitzung werden entfernt)")
        p.stepper(("clip_limit",), "Zwischenablage: Einträge", 5, 5, 50, "%d")
        p.note("Die Zwischenablage wird nicht gespeichert und ist nach einem Neustart leer.")

        # 9 Apps
        p = P[9]
        p.title("In diesen Apps ausblenden")
        self.app_list = QListWidget(p.w)
        self.app_list.setGeometry(0, p.y, 490, 292)
        self.app_list.setStyleSheet(LIST_STYLE)
        self.app_list.itemChanged.connect(self._app_toggled)
        p.y += 298
        p.button("Liste aktualisieren", self._refresh_apps, width=490)

    def _use_face(self, pane):
        self.set_cfg(("idle",), "face")
        for h in self.pane_helpers:
            h.refresh()

    def _build_pomo(self):
        pg = QWidget(self.container)
        self.pages.append(pg)
        self.po_mode = make_label(pg, 40, 32, 320, 26, "Fokus", size=13, bold=True)
        self.po_info = make_label(pg, 40, 58, 340, 20, "", size=9, color="#9aa3b8")
        self.po_time = make_label(pg, 40, 84, 340, 76, "25:00", size=40, bold=True)
        self.po_play = make_button(pg, 40, 176, 64, 36, radius=18, icon="play")
        self.po_reset = make_button(pg, 112, 176, 44, 36, radius=18, icon="reset")
        self.po_skip = make_button(pg, 164, 176, 44, 36, radius=18, icon="next")
        self.po_play.clicked.connect(lambda: (self.pomo.toggle(), self._refresh_pomo()))
        self.po_reset.clicked.connect(lambda: (self.pomo.reset(), self._refresh_pomo()))
        self.po_skip.clicked.connect(lambda: (self.pomo.skip(), self._refresh_pomo()))
        self.po_ring = ProgressRing(pg)
        self.po_ring.setGeometry(410, 40, 150, 150)

    def _refresh_pomo(self):
        pm = self.pomo
        sessions, minutes = focus_stats(self.cfg)
        self.po_mode.setText(self.tr(POMO_NAMES[pm.mode]))
        self.po_time.setText(fmt_time(pm.remaining()))
        self.po_info.setText("Heute: %d Runde%s · %d min Fokus" % (sessions, "" if sessions == 1 else "n", minutes))
        self.po_ring.value = pm.progress()
        self.po_ring.color = QColor(255, 120, 100) if pm.mode == "focus" else QColor(90, 200, 150)
        self.po_ring.text = "Runde %d" % (pm.session % 4 + 1)
        self.po_ring.sub = "von 4"
        self.po_ring.update()
        self.po_play.set_kind("pause" if pm.running else "play")

    def _pomo_event(self, mode):
        play_sound(self.cfg)
        text = {"short": "Fokus beendet. Zeit für eine kurze Pause.",
                "long": "Fokus beendet. Zeit für eine lange Pause.",
                "focus": "Pause vorbei. Weiter geht's."}.get(mode, "Timer beendet.")
        self.show_hud("timer", text, None, 4.0)

    def _build_water(self):
        pg = QWidget(self.container)
        self.pages.append(pg)
        self.wa_glass = WaterGlass(pg)
        self.wa_glass.setGeometry(50, 36, 90, 160)
        self.wa_amount = make_label(pg, 176, 44, 380, 50, "0 ml", size=30, bold=True)
        self.wa_sub = make_label(pg, 176, 96, 380, 22, "", size=10, color="#b8bcc8")
        self.wa_next = make_label(pg, 176, 122, 380, 20, "", size=9, color="#9aa3b8")
        self.wa_add = make_button(pg, 176, 160, 180, 38, "+ 500 ml", radius=12)
        self.wa_undo = make_button(pg, 364, 160, 46, 38, radius=12, icon="minus")
        self.wa_add.clicked.connect(lambda: (self.water.add(self.water.bottle()), self._refresh_water()))
        self.wa_undo.clicked.connect(lambda: (self.water.add(-self.water.bottle()), self._refresh_water()))

    def _refresh_water(self):
        w = self.water
        ml, goal = w.ml(), w.goal_ml()
        self.wa_glass.frac = w.progress()
        self.wa_glass.update()
        self.wa_amount.setText("%d ml" % ml)
        left = max(0, goal - ml)
        self.wa_sub.setText("von %d ml" % goal + (" · noch %d ml" % left if left else " · geschafft"))
        self.wa_next.setText(w.next_text())
        self.wa_add.setText("+ %d ml" % w.bottle())

    def _water_remind(self):
        play_sound(self.cfg)
        self.show_hud("droplet", self.tr("Zeit zu trinken"), None, 4.0)

    def hud_active(self):
        return self.hud is not None and time.time() < self.hud["until"]

    def show_hud(self, icon, text, value=None, secs=1.8):
        self.hud = dict(icon=icon, text=self.tr(text), value=value, until=time.time() + secs)
        if self.csize.go(*self._coll_target()):
            self._kick()
        self.update()

    def _poll_hud(self):
        self._poll_n += 1
        last = self._hud_last
        if cget(self.cfg, "hud", "volume") and self.volume.available():
            cur = (self.volume.get(), volume_muted(self.volume))
            if last["vol"] is not None and cur != last["vol"]:
                if cur[1]:
                    self.show_hud("mute", "Stumm", None, 1.4)
                else:
                    self.show_hud("speaker", "Lautstärke", cur[0], 1.4)
            last["vol"] = cur
        if cget(self.cfg, "hud", "caps"):
            cur = caps_on()
            if last["caps"] is not None and cur != last["caps"]:
                self.show_hud("caps", "Caps Lock an" if cur else "Caps Lock aus", None, 1.6)
            last["caps"] = cur
        if cget(self.cfg, "hud", "lang"):
            hwnd, name = foreground_lang()
            old = last["lang"]
            if old is not None and old[0] == hwnd and old[1] != name and name:
                self.show_hud("lang", "Eingabesprache: " + name, None, 1.6)
            last["lang"] = (hwnd, name)
        if cget(self.cfg, "hud", "battery") and self._poll_n % 40 == 0:
            try:
                b = psutil.sensors_battery()
            except Exception:
                b = None
            if b is not None:
                cur = (bool(b.power_plugged), int(b.percent))
                old = last["bat"]
                if old is not None:
                    if cur[0] != old[0]:
                        msg = "Netzteil verbunden · %d %%" if cur[0] else "Netzteil getrennt · %d %%"
                        self.show_hud("battery", msg % cur[1], None, 2.6)
                    elif not cur[0] and cur[1] <= 20 and not self._low_warned:
                        self._low_warned = True
                        self.show_hud("battery", "Akku niedrig: %d %%" % cur[1], None, 3.5)
                if cur[0] or cur[1] > 25:
                    self._low_warned = False
                last["bat"] = cur

    def _paint_ring_text(self, p, w, h, txt, frac, color):
        f = QFont("Segoe UI", 11)
        f.setBold(True)
        p.setFont(f)
        tw = QFontMetrics(f).horizontalAdvance(txt)
        ring = frac is not None
        lead = 26 if ring else 0
        x0 = (w - (lead + tw)) / 2.0
        if ring:
            rect = QRectF(x0 + 1, (h - 14) / 2.0, 14, 14)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(60, 60, 60), 2.2))
            p.drawEllipse(rect)
            p.setPen(QPen(color, 2.2, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(rect, 90 * 16, -int(clamp(frac, 0.0, 1.0) * 360 * 16))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x0 + lead, 0, tw + 6, h), Qt.AlignVCenter | Qt.AlignLeft, txt)

    def _paint_hud(self, p, w, h, hud):
        draw_icon(p, hud["icon"], QRectF(14, (h - 16) / 2.0, 16, 16), QColor(255, 255, 255))
        f = QFont("Segoe UI", 10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        if hud["value"] is not None:
            p.drawText(QRectF(40, 0, 110, h), Qt.AlignVCenter | Qt.AlignLeft, hud["text"])
            bx, bw = 152.0, max(20.0, w - 152.0 - 56.0)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 60))
            p.drawRoundedRect(QRectF(bx, h / 2.0 - 2.5, bw, 5), 2.5, 2.5)
            p.setBrush(QColor(255, 255, 255))
            p.drawRoundedRect(QRectF(bx, h / 2.0 - 2.5, bw * clamp(hud["value"] / 100.0, 0.0, 1.0), 5), 2.5, 2.5)
            p.setPen(QColor(255, 255, 255))
            p.drawText(QRectF(w - 48, 0, 34, h), Qt.AlignVCenter | Qt.AlignRight, str(int(hud["value"])))
        else:
            p.drawText(QRectF(40, 0, w - 56, h), Qt.AlignVCenter | Qt.AlignLeft, elide(hud["text"], f, w - 60))


# ---------------------------------------------------------------- Start
def main():
    cfg = load_config()
    size = str(cget(cfg, "size"))
    if size.isdigit():
        os.environ["QT_SCALE_FACTOR"] = str(int(size) / 100.0)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if cget(cfg, "shelf_empty_start"):
        cfg["shelf"] = []
    volume = Volume()
    lyrics = Lyrics()

    notch = Notch(cfg, volume, lyrics)
    worker = MediaWorker()
    notch.worker = worker
    worker.changed.connect(notch.on_media)
    worker.timeline.connect(notch.on_timeline)
    lyrics.ready.connect(notch.on_lyrics)

    tray = QSystemTrayIcon(make_tray_icon(), app)
    menu = QMenu()
    menu.addAction("Einstellungen").triggered.connect(notch.open_settings)
    menu.addAction("Beenden").triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip(APP_NAME)
    tray.show()
    worker.error.connect(lambda m: tray.showMessage(APP_NAME, m))

    notch.show()
    worker.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
