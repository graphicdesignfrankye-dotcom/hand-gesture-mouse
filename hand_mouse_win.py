#!/usr/bin/env python3
"""Hand Gesture Mouse per Windows (parte specifica del sistema; la logica comune e' in gesture_core.py).

Controlla il cursore con la mano tramite la webcam: gli stessi gesti della versione macOS.

    Indice alzato, muovi ......... muove il cursore
    Pizzico rapido (pollice+indice) click sinistro (due pizzichi rapidi = doppio click)
    Pizzico tenuto ............... premi e trascina, apri la mano per rilasciare
    Pizzico pollice + medio ...... click destro
    Indice + medio alzati, muovi . scroll (mano in su = scorre in su)
    Pugno chiuso (tieni ~0,6 s) .. pausa / ripresa del tracking

Dall'icona nell'area di notifica (vicino all'orologio) puoi mettere in pausa, aprire le Impostazioni ed uscire.
Nella finestra di anteprima: Q = esci, S = Impostazioni, P = pausa.

NOTA: questa versione e' stata scritta su un Mac e non e' ancora stata provata su un PC Windows.
"""

import ctypes
import os
import queue
import sys
import time
import traceback
from ctypes import wintypes

import cv2

import gesture_core as core

IS_WINDOWS = sys.platform == "win32"
user32 = ctypes.windll.user32 if IS_WINDOWS else None   # sostituibile nei test

# =============================================================================
# Percorsi e testi specifici di Windows
# =============================================================================
APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", APPDATA), "Hand Gesture Mouse")
core.SETTINGS_PATH = os.path.join(APPDATA, "Hand Gesture Mouse", "settings.json")
core.LOG_PATH = os.path.join(LOG_DIR, "log.txt")

core.set_action_text({
    "fullscreen": ("Schermo intero", "Schermo intero (F11)"),
    "mission_control": ("Vista attivita", "Vista attività (Win+Tab)"),
    "space_left": ("Desktop a sinistra", "Desktop virtuale a sinistra (Win+Ctrl+←)"),
    "space_right": ("Desktop a destra", "Desktop virtuale a destra (Win+Ctrl+→)"),
    "app_switcher": ("Cambia app", "Cambia app (Alt+Tab)"),
    "minimize": ("Riduci finestra", "Riduci finestra (Win+Giù)"),
    "screenshot": ("Screenshot area", "Screenshot di un'area (Win+Shift+S)"),
    "lock_screen": ("Blocca schermo", "Blocca lo schermo (Win+L)"),
    "spotlight": ("Ricerca", "Ricerca di Windows (Win+S)"),
})

# Modificatori nelle scorciatoie (campo "flags")
SHIFT, CTRL, ALT, WIN = 1, 2, 4, 8
MODIFIER_VK = ((WIN, 0x5B), (CTRL, 0x11), (ALT, 0x12), (SHIFT, 0x10))   # ordine di pressione
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x1, 0x2
# tasti "estesi" (frecce, Home/End, ... e tasti multimediali) vanno inviati col flag apposito
EXTENDED_VK = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB3}

# azione -> (codice tasto virtuale, modificatori)
SHORTCUTS = {
    "fullscreen": (0x7A, 0),                 # F11
    "mission_control": (0x09, WIN),          # Win+Tab
    "space_left": (0x25, WIN | CTRL),        # Win+Ctrl+Sinistra
    "space_right": (0x27, WIN | CTRL),       # Win+Ctrl+Destra
    "app_switcher": (0x09, ALT),             # Alt+Tab
    "minimize": (0x28, WIN),                 # Win+Giu
    "screenshot": (0x53, WIN | SHIFT),       # Win+Shift+S
    "spotlight": (0x53, WIN),                # Win+S
}
MEDIA_KEYS = {"play_pause": 0xB3, "next_track": 0xB0, "prev_track": 0xB1,
              "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD}

MOUSEEVENTF = {("left", True): 0x2, ("left", False): 0x4, ("right", True): 0x8, ("right", False): 0x10}
MOUSEEVENTF_WHEEL = 0x800


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def make_dpi_aware():
    """Coordinate in pixel reali (altrimenti con la scala di Windows il cursore finirebbe fuori posto)."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


class Mouse(core.MouseBase):
    """Eventi di input di Windows (user32: SetCursorPos, mouse_event, keybd_event)."""

    permission_name = "permessi"

    def position(self):
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return float(pt.x), float(pt.y)

    def _list_displays(self):
        rects = []
        functype = ctypes.WINFUNCTYPE if IS_WINDOWS else ctypes.CFUNCTYPE   # CFUNCTYPE solo per i test su altri sistemi
        proc_type = functype(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(_RECT), wintypes.LPARAM)

        def on_monitor(hmonitor, hdc, rect, lparam):
            r = rect.contents
            rects.append((float(r.left), float(r.top), float(r.right - r.left), float(r.bottom - r.top)))
            return True

        user32.EnumDisplayMonitors(None, None, proc_type(on_monitor), 0)
        if not rects:   # ripiego: schermo principale
            rects.append((0.0, 0.0, float(user32.GetSystemMetrics(0)), float(user32.GetSystemMetrics(1))))
        return sorted(rects)

    def _warp(self, x, y):
        user32.SetCursorPos(int(x), int(y))

    def _emit_move(self, x, y, dragging):
        user32.SetCursorPos(int(x), int(y))   # col pulsante premuto diventa un trascinamento

    def _emit_button(self, button, down, x, y, clicks):
        user32.SetCursorPos(int(x), int(y))
        user32.mouse_event(MOUSEEVENTF[(button, down)], 0, 0, 0, 0)

    def _emit_scroll(self, pixels):
        # una tacca della rotella = 120; i pixel di macOS corrispondono a circa un centesimo di tacca
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(pixels * 1.2) & 0xFFFFFFFF, 0)

    def _key(self, vk, down):
        flags = (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_VK else 0) | (0 if down else KEYEVENTF_KEYUP)
        user32.keybd_event(vk, 0, flags, 0)

    def _emit_key(self, code, flags):
        mods = [vk for bit, vk in MODIFIER_VK if flags & bit]
        for vk in mods:
            self._key(vk, True)
        self._key(code, True)
        self._key(code, False)
        for vk in reversed(mods):
            self._key(vk, False)

    def supports(self, action):
        return action in SHORTCUTS or action in MEDIA_KEYS or action == "lock_screen"

    def _emit_action(self, action):
        if action == "lock_screen":
            user32.LockWorkStation()
        elif action in MEDIA_KEYS:
            self._emit_key(MEDIA_KEYS[action], 0)
        else:
            self._emit_key(*SHORTCUTS[action])


# =============================================================================
# Webcam
# =============================================================================
def list_cameras():
    """Webcam disponibili come (ID, nome). L'ID e' il nome; l'ordine e' quello di DirectShow (come OpenCV)."""
    try:
        from pygrabber.dshow_graph import FilterGraph
        names = FilterGraph().get_input_devices()
    except Exception:
        names = []
        for i in range(4):   # senza pygrabber non ci sono i nomi: proviamo gli indici
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                names.append(f"Webcam {i}")
            cap.release()
    return [(name, name) for name in names]


def camera_index():
    for i, (cam_id, _) in enumerate(list_cameras()):
        if cam_id == core.CAMERA_ID:
            return i
    return core.CAMERA_INDEX


class Camera:
    def __init__(self, index):
        cams = list_cameras()
        self.name = cams[index][1] if index < len(cams) else f"Webcam {index}"
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, core.CAMERA_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, core.CAMERA_WIDTH * 3 // 4)

    def isOpened(self):
        return self.cap.isOpened()

    def read(self):
        return self.cap.read()

    def release(self):
        self.cap.release()


def try_open_camera():
    cam = Camera(camera_index())
    if cam.isOpened():
        return cam
    cam.release()
    return None


def fail(title, text):
    core.log(f"{title}: {text}")
    if IS_WINDOWS:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)   # MB_ICONERROR
    sys.exit(1)


def open_camera():
    cap = try_open_camera()
    if cap is None:
        fail("Impossibile aprire la webcam",
             "Controlla che nessun'altra app la stia usando e che l'accesso alla fotocamera sia consentito in "
             "Impostazioni di Windows > Privacy e sicurezza > Fotocamera (anche per le app desktop).")
    core.log(f"Webcam in uso: {cap.name}")
    return cap


def switch_camera(old, mouse):
    """Passa alla webcam scelta nelle Impostazioni; se non si apre resta su quella attuale."""
    old.release()
    new = try_open_camera()
    if new is None:
        core.log("Impossibile aprire la webcam scelta: torno a quella di prima")
        mouse.events.append("Impossibile aprire la webcam scelta")
        return try_open_camera() or old
    core.log(f"Webcam cambiata: {new.name}")
    return new


# =============================================================================
# Icona nell'area di notifica
# =============================================================================
class Tray:
    """Icona vicino all'orologio. I comandi arrivano dal suo thread e passano da una coda al ciclo principale."""

    COLORS = {"active": (40, 180, 90), "paused": (200, 60, 60), "rec": (240, 150, 30)}

    def __init__(self, ctrl, settings, commands):
        import pystray
        self.pystray = pystray
        self.ctrl, self.settings, self.state = ctrl, settings, None
        menu = pystray.Menu(
            pystray.MenuItem(lambda item: "Riprendi" if ctrl.paused else "Metti in pausa",
                             lambda: commands.put("toggle")),
            pystray.MenuItem("Ferma registrazione sequenza", lambda: commands.put("stoprec"),
                             visible=lambda item: settings.macro_recording),
            pystray.MenuItem("Impostazioni…", lambda: commands.put("settings"), default=True),
            pystray.MenuItem("Esci", lambda: commands.put("quit")),
        )
        self.icon = pystray.Icon("HandGestureMouse", self._image("active"), "Hand Gesture Mouse", menu)
        self.icon.run_detached()

    def _image(self, state):
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((4, 4, 60, 60), fill=self.COLORS[state])
        for x in (18, 27, 36, 45):   # una mano stilizzata: quattro dita e il palmo
            draw.rounded_rectangle((x, 12, x + 7, 36), radius=3, fill=(255, 255, 255))
        draw.rounded_rectangle((16, 30, 49, 50), radius=8, fill=(255, 255, 255))
        return img

    def update(self):
        state = "rec" if self.settings.macro_recording else ("paused" if self.ctrl.paused else "active")
        if state != self.state:
            self.state = state
            self.icon.icon = self._image(state)
            self.icon.update_menu()

    def stop(self):
        self.icon.stop()


# =============================================================================
# Finestra Impostazioni (tkinter)
# =============================================================================
class Settings:
    """Come la finestra della versione macOS: Test dei comandi, Azioni, Generale, Parametri."""

    def __init__(self, root, ctrl, mouse):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root, self.ctrl, self.mouse = root, ctrl, mouse
        self.camera_dirty = False
        self.macro_recording = False
        self.macro_steps, self.macro_last, self.macro_mods = [], None, 0
        self.listeners = []
        self.call_listener, self.call_done = None, None
        self.shortcut_recording = False
        self.cameras = []
        self.last_refresh = 0.0
        self._syncing = False
        root.title("Impostazioni - Hand Gesture Mouse")
        root.geometry("680x760")
        root.protocol("WM_DELETE_WINDOW", root.withdraw)
        root.withdraw()
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_test()
        self._build_actions()
        self._build_motions()
        self._build_general()
        self._build_params()
        self.refill_actions()
        self.fill_cameras()
        self.sync_all()

    # -- schede ----------------------------------------------------------------------------
    def _tab(self, title):
        frame = self.ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=title)
        return frame

    def _build_test(self):
        tk, ttk = self.tk, self.ttk
        f = self._tab("Test dei comandi")
        self.gesture_var = tk.StringVar(value="-")
        ttk.Label(f, textvariable=self.gesture_var, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        self.metric1, self.metric2 = tk.StringVar(), tk.StringVar()
        ttk.Label(f, textvariable=self.metric1, font=("Consolas", 10)).pack(anchor="w", pady=(6, 0))
        ttk.Label(f, textvariable=self.metric2, font=("Consolas", 10)).pack(anchor="w")
        grid = ttk.Frame(f)
        grid.pack(anchor="w", pady=12)
        self.checks = {}
        names = [("move", "Muovi il cursore"), ("click", "Click sinistro"), ("drag", "Trascinamento"),
                 ("right", "Click destro"), ("scroll", "Scroll"), ("fist", "Pausa (pugno)"),
                 ("three", "Tre dita alzate"), ("rock", "Indice + mignolo"),
                 ("volume", "Volume (mano aperta)"), ("motion", "Movimento registrato"),
                 ("swipe_left", "Swipe a sinistra"), ("swipe_right", "Swipe a destra")]
        for i, (key, name) in enumerate(names):
            label = tk.Label(grid, text="○ " + name, anchor="w", width=26)
            label.grid(row=i // 2, column=i % 2, sticky="w")
            self.checks[key] = (label, name)
        self.dry_var = tk.BooleanVar(value=False)
        row = ttk.Frame(f)
        row.pack(anchor="w", fill="x")
        ttk.Checkbutton(row, text="Modalità test: non muovere il mouse vero né premere tasti",
                        variable=self.dry_var, command=lambda: setattr(self.mouse, "dry_run", self.dry_var.get())
                        ).pack(side="left")
        ttk.Button(row, text="Azzera test", command=self.clear_test).pack(side="right")
        self.events_var = tk.StringVar()
        ttk.Label(f, textvariable=self.events_var, justify="left").pack(anchor="w", pady=12)

    def _build_actions(self):
        tk, ttk = self.tk, self.ttk
        f = self._tab("Azioni dei gesti")
        self.mode_var = tk.StringVar()
        ttk.Label(f, textvariable=self.mode_var, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(f, text="Ogni gesto va tenuto fermo per il tempo impostato in Parametri. Prova le azioni\n"
                          "con la Modalità test (scheda Test): vedi cosa farebbero senza eseguirle.").pack(anchor="w", pady=6)
        self.mode_frames, self.combos = {}, {}
        for mode, gestures in (("one", core.ACTION_GESTURES), ("two", core.FREE_HAND_GESTURES)):
            frame = ttk.Frame(f)
            self.mode_frames[mode] = frame
            for row, (key, name, _) in enumerate(gestures):
                ttk.Label(frame, text=name, width=36).grid(row=row, column=0, sticky="w", pady=4)
                combo = ttk.Combobox(frame, state="readonly", width=44)
                combo.grid(row=row, column=1, pady=4)
                combo.bind("<<ComboboxSelected>>", lambda e, m=mode, k=key, c=combo: self.on_action(m, k, c))
                self.combos[(mode, key)] = combo
        bottom = ttk.Frame(f)
        bottom.pack(side="bottom", fill="x", pady=6)
        r1 = ttk.Frame(bottom); r1.pack(anchor="w", pady=2)
        ttk.Button(r1, text="Registra scorciatoia…", command=self.record_shortcut).pack(side="left", padx=(0, 6))
        ttk.Button(r1, text="Elimina registrate", command=self.clear_customs).pack(side="left")
        r2 = ttk.Frame(bottom); r2.pack(anchor="w", pady=2)
        ttk.Button(r2, text="Registra sequenza…", command=self.start_macro).pack(side="left", padx=(0, 6))
        ttk.Button(r2, text="Ferma registrazione", command=self.stop_macro).pack(side="left", padx=(0, 6))
        ttk.Button(r2, text="Elimina sequenze", command=self.clear_macros).pack(side="left")
        self.note_var = tk.StringVar()
        ttk.Label(bottom, textvariable=self.note_var, wraplength=560, justify="left").pack(anchor="w", pady=4)

    def on_swipe(self, direction, combo):
        core.SWIPE_ACTIONS[direction] = core.ACTIONS[combo.current()][0]
        core.save_settings()

    def _build_motions(self):
        tk, ttk = self.tk, self.ttk
        f = self._tab("Movimenti")
        ttk.Label(f, text="Mano aperta: movimento rapido a sinistra o a destra", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(f, justify="left", text=(
            "Vale per la mano del mouse (con una mano, per l'unica mano). «Sinistra» è la tua sinistra.\n"
            "Distanza e pausa si regolano in Parametri; alzare o abbassare la mano aperta regola il volume.")).pack(anchor="w")
        grid = ttk.Frame(f)
        grid.pack(anchor="w", pady=8)
        self.swipe_combos = {}
        for row, (direction, title) in enumerate((("left", "Mano aperta → sinistra"), ("right", "Mano aperta → destra"))):
            ttk.Label(grid, text=title, width=26).grid(row=row, column=0, sticky="w", pady=4)
            combo = ttk.Combobox(grid, state="readonly", width=46)
            combo.grid(row=row, column=1)
            combo.bind("<<ComboboxSelected>>", lambda e, d=direction, c=combo: self.on_swipe(d, c))
            self.swipe_combos[direction] = combo
        ttk.Label(f, text="Movimenti registrati", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(14, 0))
        ttk.Label(f, justify="left", text=(
            "Fai la posa che vuoi (tre dita, mignolo, mano aperta...), premi Registra: dopo 3 secondi muovi la mano per 2.\n"
            "Una mano: mano aperta, tre dita, indice+mignolo o mignolo. Due mani: la mano libera.")).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=8)
        ttk.Button(row, text="Registra movimento…", command=self.ctrl.start_motion_recording).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Annulla", command=self.ctrl.cancel_motion_recording).pack(side="left")
        self.motion_note_var = tk.StringVar()
        ttk.Label(f, textvariable=self.motion_note_var, wraplength=600, justify="left").pack(anchor="w")
        self.motion_frame = ttk.Frame(f)
        self.motion_frame.pack(anchor="w", fill="x", pady=8)

    def refill_motions(self):
        ttk = self.ttk
        for child in self.motion_frame.winfo_children():
            child.destroy()
        titles = [t for _, _, t in core.ACTIONS]
        keys = [k for k, _, _ in core.ACTIONS]
        for row, motion in enumerate(core.MOTIONS):
            ttk.Label(self.motion_frame, width=26,
                      text=f"{motion['name']} · {core.POSE_NAMES[motion['pose']]}").grid(row=row, column=0, sticky="w", pady=4)
            combo = ttk.Combobox(self.motion_frame, state="readonly", width=42, values=titles)
            combo.current(keys.index(motion["action"]) if motion["action"] in keys else 0)
            combo.grid(row=row, column=1, padx=6)
            combo.bind("<<ComboboxSelected>>", lambda e, m=motion, c=combo: self.on_motion_action(m, c))
            ttk.Button(self.motion_frame, text="Elimina", command=lambda m=motion: self.delete_motion(m)).grid(row=row, column=2)

    def on_motion_action(self, motion, combo):
        motion["action"] = core.ACTIONS[combo.current()][0]
        core.save_settings()

    def delete_motion(self, motion):
        core.remove_motion(motion["id"])
        core.save_settings()
        self.refill_motions()

    def _build_general(self):
        tk, ttk = self.tk, self.ttk
        f = self._tab("Generale")
        r = ttk.Frame(f); r.pack(anchor="w", fill="x", pady=8)
        ttk.Label(r, text="Webcam", width=10).pack(side="left")
        self.camera_combo = ttk.Combobox(r, state="readonly", width=40)
        self.camera_combo.pack(side="left", padx=6)
        self.camera_combo.bind("<<ComboboxSelected>>", self.on_camera)
        ttk.Button(r, text="Aggiorna elenco", command=self.fill_cameras).pack(side="left")
        r = ttk.Frame(f); r.pack(anchor="w", fill="x", pady=8)
        ttk.Label(r, text="Mani", width=10).pack(side="left")
        self.hands_combo = ttk.Combobox(r, state="readonly", width=52, values=[t for _, t in core.HAND_MODES])
        self.hands_combo.pack(side="left", padx=6)
        self.hands_combo.bind("<<ComboboxSelected>>", self.on_hands)
        ttk.Label(f, text="Con due mani una controlla il cursore e i click,\nl'altra i gesti-azione "
                          "(tre dita, indice + mignolo...).").pack(anchor="w", padx=80)
        self.volume_var = tk.BooleanVar(value=core.VOLUME_GESTURE)
        ttk.Checkbutton(f, text="Volume con la mano aperta (alzala / abbassala)", variable=self.volume_var,
                        command=self.on_volume).pack(anchor="w", pady=10)
        r = ttk.Frame(f); r.pack(anchor="w", fill="x", pady=4)
        ttk.Label(r, text="Chiamate", width=10).pack(side="left")
        ttk.Button(r, text="Registra click «Rispondi»", command=lambda: self.start_call("answer_call")).pack(side="left", padx=3)
        ttk.Button(r, text="Registra click «Rifiuta»", command=lambda: self.start_call("decline_call")).pack(side="left", padx=3)
        ttk.Button(r, text="Registra click «Chiudi»", command=lambda: self.start_call("end_call")).pack(side="left", padx=3)
        ttk.Button(r, text="Annulla", command=self.cancel_call).pack(side="left", padx=3)
        self.call_var, self.call_note_var = tk.StringVar(), tk.StringVar()
        ttk.Label(f, textvariable=self.call_var).pack(anchor="w", padx=80)
        ttk.Label(f, textvariable=self.call_note_var).pack(anchor="w")
        ttk.Label(f, justify="left", text="Con la notifica di chiamata visibile: premi il pulsante, poi clicca sul suo «Accetta» / «Rifiuta».\n"
                                          "Il mignolo alzato risponde e, rifatto, chiude (usa i click «Rispondi» e «Chiudi»).").pack(anchor="w")
        ttk.Label(f, text="\nPermessi: su Windows non servono permessi speciali, ma i comandi non arrivano alle finestre\n"
                          "aperte «come amministratore» a meno che anche questa app sia avviata come amministratore.\n"
                          "La webcam va consentita in Impostazioni di Windows > Privacy e sicurezza > Fotocamera.",
                  justify="left").pack(anchor="w")

    def _build_params(self):
        tk, ttk = self.tk, self.ttk
        f = self._tab("Parametri")
        self.scales = {}
        for row, (key, label, lo, hi, fmt) in enumerate(core.TUNABLES):
            ttk.Label(f, text=label, width=28).grid(row=row, column=0, sticky="w", pady=2)
            is_int = isinstance(core.DEFAULTS[key], int)
            scale = tk.Scale(f, from_=lo, to=hi, orient="horizontal", length=240, showvalue=False,
                             resolution=1 if is_int else 0.01,
                             command=lambda v, k=key: self.on_scale(k, v))
            scale.grid(row=row, column=1, pady=2)
            scale.bind("<ButtonRelease-1>", lambda e: core.save_settings())
            value = ttk.Label(f, text="", width=8)
            value.grid(row=row, column=2)
            self.scales[key] = (scale, value, fmt)
        self.invert_var = tk.BooleanVar(value=core.SCROLL_INVERT)
        ttk.Checkbutton(f, text="Inverti direzione dello scroll", variable=self.invert_var,
                        command=self.on_invert).grid(row=len(core.TUNABLES), column=0, columnspan=3, sticky="w", pady=8)
        ttk.Button(f, text="Ripristina predefiniti", command=self.reset).grid(
            row=len(core.TUNABLES) + 1, column=0, sticky="w")

    # -- aggiornamento dei controlli ------------------------------------------------------
    def sync(self, key):
        scale, value_label, fmt = self.scales[key]
        value = getattr(core, key)
        self._syncing = True
        scale.set(value)
        self._syncing = False
        value_label.config(text=fmt.format(int(value) if "d" in fmt else value))

    def sync_all(self):
        for key in self.scales:
            self.sync(key)
        self.invert_var.set(core.SCROLL_INVERT)
        self.volume_var.set(core.VOLUME_GESTURE)
        self.hands_combo.current([k for k, _ in core.HAND_MODES].index(core.HAND_MODE))
        keys = [k for k, _, _ in core.ACTIONS]
        for direction, combo in self.swipe_combos.items():
            combo.current(keys.index(core.SWIPE_ACTIONS.get(direction, "none")))
        for (mode, gesture), combo in self.combos.items():
            mapping = core.GESTURE_ACTIONS if mode == "one" else core.GESTURE_ACTIONS_TWO
            combo.current(keys.index(mapping.get(gesture, "none")))
        two = core.HAND_MODE != "one"
        for mode, frame in self.mode_frames.items():
            frame.pack_forget()
        self.mode_frames["two" if two else "one"].pack(anchor="w", pady=6)
        self.mode_var.set("Modalità due mani: gesti della mano libera" if two else "Modalità una mano")

    def refill_actions(self):
        titles = [t for _, _, t in core.ACTIONS]
        for combo in list(self.combos.values()) + list(self.swipe_combos.values()):
            combo["values"] = titles
        self.sync_all()
        self.refill_motions()

    def fill_cameras(self):
        self.cameras = list_cameras()
        self.camera_combo["values"] = [name for _, name in self.cameras] or ["(nessuna webcam trovata)"]
        if self.cameras:
            self.camera_combo.current(min(camera_index(), len(self.cameras) - 1))

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def refresh(self, label):
        """Chiamato a ogni frame con il gesto riconosciuto."""
        key = core.LABEL_KEYS.get(label)
        if key:
            self.ctrl.verified.add(key)
        if self.ctrl.motions_changed:
            self.ctrl.motions_changed = False
            self.refill_motions()
        if self.call_done:   # click di risposta/rifiuto ricevuto dal listener (thread a parte)
            target, x, y = self.call_done
            self.call_done, self.call_listener = None, None
            core.CALL_POINTS[target] = [x, y]
            core.save_settings()
            self.call_note_var.set(f"Registrato il click a ({x:.0f}, {y:.0f}).")
        now = time.monotonic()
        if self.root.state() == "withdrawn" or now - self.last_refresh < 0.1:
            return
        self.last_refresh = now
        self.motion_note_var.set(self.ctrl.motion_message)
        self.call_var.set(f"Rispondi {'✓' if 'answer_call' in core.CALL_POINTS else '—'}    "
                          f"Rifiuta {'✓' if 'decline_call' in core.CALL_POINTS else '—'}    "
                          f"Chiudi {'✓' if 'end_call' in core.CALL_POINTS else '—'}")
        self.gesture_var.set(label)
        if self.ctrl.debug:
            d_ti, d_tm, ext = self.ctrl.debug
            self.metric1.set(f"Pollice-indice {d_ti:.2f} (pizzico sotto {core.PINCH_START:.2f})   Pollice-medio {d_tm:.2f}")
            names = ["indice", "medio", "anulare", "mignolo"]
            self.metric2.set("Dita estese: " + "  ".join(f"{n} {'✓' if e else '·'}" for n, e in zip(names, ext)))
        else:
            self.metric1.set("Nessuna mano nell'inquadratura")
            self.metric2.set("")
        for k, (lab, name) in self.checks.items():
            ok = k in self.ctrl.verified
            lab.config(text=("✓ " if ok else "○ ") + name, fg="#1a9e4b" if ok else "#777777")
        recent = "\n".join(reversed(self.mouse.events)) or "(nessun comando ancora)"
        self.events_var.set("Ultimi comandi:\n" + recent)
        if self.macro_recording:
            self.note_var.set(f"Registrazione… {len(self.macro_steps)} passi")

    # -- azioni dei controlli ---------------------------------------------------------------
    def clear_test(self):
        self.ctrl.verified.clear()
        self.mouse.events.clear()

    def on_scale(self, key, raw):
        if self._syncing:
            return
        value = float(raw)
        setattr(core, key, int(round(value)) if isinstance(core.DEFAULTS[key], int) else value)
        if key == "PINCH_START" and core.PINCH_RELEASE < core.PINCH_START + 0.05:
            core.PINCH_RELEASE = core.PINCH_START + 0.05   # il rilascio deve restare piu' ampio dell'inizio
            self.sync("PINCH_RELEASE")
        elif key == "PINCH_RELEASE" and core.PINCH_RELEASE < core.PINCH_START + 0.05:
            core.PINCH_START = core.PINCH_RELEASE - 0.05
            self.sync("PINCH_START")
        scale, value_label, fmt = self.scales[key]
        shown = getattr(core, key)
        value_label.config(text=fmt.format(int(shown) if "d" in fmt else shown))

    def on_volume(self):
        core.VOLUME_GESTURE = bool(self.volume_var.get())
        core.save_settings()

    def start_call(self, target):
        """Registra il prossimo click del mouse (in qualsiasi app) come pulsante di risposta o rifiuto."""
        if self.call_listener is not None:
            return
        try:
            from pynput import mouse
        except ImportError:
            self.call_note_var.set("Serve la libreria pynput (pip install pynput).")
            return

        def on_click(x, y, button, pressed):
            if pressed and button == mouse.Button.left:
                self.call_done = (target, float(x), float(y))
                return False   # ferma il listener

        self.call_listener = mouse.Listener(on_click=on_click)
        self.call_listener.start()
        self.call_note_var.set("Clicca ora sul pulsante della notifica...")

    def cancel_call(self):
        if self.call_listener is not None:
            self.call_listener.stop()
            self.call_listener = None
            self.call_note_var.set("Registrazione del click annullata.")

    def on_invert(self):
        core.SCROLL_INVERT = bool(self.invert_var.get())
        core.save_settings()

    def reset(self):
        for key in core.SETTING_KEYS:
            setattr(core, key, core.DEFAULTS[key])
        core.HAND_MODE = core.DEFAULT_HAND_MODE
        core.GESTURE_ACTIONS.clear()
        core.GESTURE_ACTIONS.update(core.DEFAULT_GESTURE_ACTIONS)
        core.GESTURE_ACTIONS_TWO.clear()
        core.GESTURE_ACTIONS_TWO.update(core.DEFAULT_GESTURE_ACTIONS_TWO)
        core.SWIPE_ACTIONS.update(core.DEFAULT_SWIPE_ACTIONS)
        self.sync_all()
        core.save_settings()

    def on_action(self, mode, gesture, combo):
        mapping = core.GESTURE_ACTIONS if mode == "one" else core.GESTURE_ACTIONS_TWO
        mapping[gesture] = core.ACTIONS[combo.current()][0]
        core.save_settings()

    def on_camera(self, event=None):
        i = self.camera_combo.current()
        if 0 <= i < len(self.cameras):
            core.CAMERA_ID = self.cameras[i][0]
            self.camera_dirty = True
            core.save_settings()

    def on_hands(self, event=None):
        core.HAND_MODE = core.HAND_MODES[self.hands_combo.current()][0]
        self.ctrl.pose = None
        self.sync_all()
        core.save_settings()

    # -- scorciatoia registrata -------------------------------------------------------------
    def record_shortcut(self):
        if self.shortcut_recording or self.macro_recording:
            return
        if len(core.CUSTOM_ACTIONS) >= 6:
            self.note_var.set("Massimo 6 scorciatoie registrate: eliminane qualcuna.")
            return
        self.shortcut_recording = True
        self.note_var.set("Premi ora la combinazione di tasti (Esc da solo = annulla)...")
        self.root.bind("<KeyPress>", self.on_shortcut_key)
        self.root.focus_force()

    def on_shortcut_key(self, event):
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Win_L", "Win_R",
                            "Caps_Lock", "Num_Lock"):
            return "break"   # aspetta il tasto vero
        self.root.unbind("<KeyPress>")
        self.shortcut_recording = False
        flags = (SHIFT if event.state & 0x1 else 0) | (CTRL if event.state & 0x4 else 0) | (ALT if event.state & 0x20000 else 0)
        if event.keysym == "Escape" and not flags:
            self.note_var.set("Registrazione annullata.")
            return "break"
        label = "+".join([n for bit, n in ((CTRL, "Ctrl"), (ALT, "Alt"), (SHIFT, "Maiusc")) if flags & bit]
                         + [event.keysym.upper() if len(event.keysym) == 1 else event.keysym])
        number = max([int(e["id"][6:]) for e in core.CUSTOM_ACTIONS] + [0]) + 1
        core.register_custom({"id": f"custom{number}", "label": label, "code": event.keycode, "flags": flags})
        core.save_settings()
        self.refill_actions()
        self.note_var.set(f"Registrata {label}: ora scegli «{core.ACTION_SHORT[f'custom{number}']}» nel menu di un gesto.")
        return "break"

    def clear_customs(self):
        core.remove_customs()
        core.save_settings()
        self.refill_actions()
        self.note_var.set("Scorciatoie registrate eliminate.")

    # -- sequenza registrata (tasti e click in qualsiasi app, via pynput) ----------------------
    def start_macro(self):
        if self.macro_recording or self.shortcut_recording:
            return
        if len(core.MACROS) >= core.MAX_MACROS:
            self.note_var.set(f"Massimo {core.MAX_MACROS} sequenze: eliminane qualcuna.")
            return
        try:
            from pynput import keyboard, mouse
        except ImportError:
            self.note_var.set("Per registrare le sequenze serve la libreria pynput (pip install pynput).")
            return
        self.macro_steps, self.macro_last, self.macro_mods = [], None, 0
        self.kb, self.ms = keyboard, mouse
        self.listeners = [keyboard.Listener(on_press=self._on_press, on_release=self._on_release),
                          mouse.Listener(on_click=self._on_click)]
        for listener in self.listeners:
            listener.start()
        self.macro_recording = True
        self.note_var.set("Registrazione… esegui ora tasti e click, poi «Ferma registrazione» (o dall'icona vicino all'orologio).")

    def _mod_bit(self, key):
        names = {"shift": SHIFT, "shift_l": SHIFT, "shift_r": SHIFT, "ctrl": CTRL, "ctrl_l": CTRL, "ctrl_r": CTRL,
                 "alt": ALT, "alt_l": ALT, "alt_r": ALT, "alt_gr": ALT, "cmd": WIN, "cmd_l": WIN, "cmd_r": WIN}
        return names.get(getattr(key, "name", ""), 0)

    def _delay(self):
        now = time.monotonic()
        delay = 0.3 if self.macro_last is None else now - self.macro_last
        self.macro_last = now
        return round(delay, 2)

    def _on_press(self, key):
        bit = self._mod_bit(key)
        if bit:
            self.macro_mods |= bit
            return
        vk = getattr(key, "vk", None)
        if vk is None:
            vk = getattr(getattr(key, "value", None), "vk", None)
        if vk is not None and len(self.macro_steps) < core.MAX_STEPS:
            self.macro_steps.append({"k": "key", "code": int(vk), "flags": self.macro_mods, "d": self._delay()})

    def _on_release(self, key):
        self.macro_mods &= ~self._mod_bit(key)

    def _on_click(self, x, y, button, pressed):
        if pressed and len(self.macro_steps) < core.MAX_STEPS:
            self.macro_steps.append({"k": "click", "x": float(x), "y": float(y),
                                     "b": "right" if button == self.ms.Button.right else "left", "d": self._delay()})

    def stop_macro(self, from_tray=False):
        if not self.macro_recording:
            return
        for listener in self.listeners:
            listener.stop()
        self.macro_recording = False
        steps = list(self.macro_steps)
        # il click sul pulsante «Ferma» (o sull'icona) non fa parte della sequenza
        if steps and steps[-1]["k"] == "click" and (from_tray or self._inside_window(steps[-1]["x"], steps[-1]["y"])):
            steps.pop()
        steps = [s for s in steps if not (s["k"] == "click" and self._inside_window(s["x"], s["y"]))]
        if not steps:
            self.note_var.set("Nessun passo registrato.")
            return
        number = max([int(m["id"][5:]) for m in core.MACROS] + [0]) + 1
        core.register_macro({"id": f"macro{number}", "name": f"Sequenza {number}", "steps": steps})
        core.save_settings()
        self.refill_actions()
        self.note_var.set(f"Registrata «{core.ACTION_SHORT[f'macro{number}']}» ({len(steps)} passi): "
                          "scegli l'azione nel menu di un gesto.")

    def _inside_window(self, x, y):
        r = self.root
        return r.state() != "withdrawn" and r.winfo_rootx() <= x <= r.winfo_rootx() + r.winfo_width() \
            and r.winfo_rooty() <= y <= r.winfo_rooty() + r.winfo_height()

    def clear_macros(self):
        core.remove_macros()
        core.save_settings()
        self.refill_actions()
        self.note_var.set("Sequenze registrate eliminate.")


# =============================================================================
# Programma principale
# =============================================================================
def play_cue(kind):
    """Segnali sonori per la registrazione di un movimento: un tic al secondo, poi «ORA», poi esito."""
    import winsound
    freq, ms = {"tick": (600, 60), "start": (1200, 250), "ok": (1000, 150), "fail": (300, 400)}[kind]
    winsound.Beep(freq, ms)   # blocca il programma per qualche decimo di secondo: va bene per questi segnali


def main():
    make_dpi_aware()
    os.makedirs(LOG_DIR, exist_ok=True)
    core.log("Avvio")
    core.load_settings()
    cap = open_camera()
    mouse = Mouse()
    ctrl = core.GestureController(mouse)
    ctrl.cue = play_cue
    two_hands = core.HAND_MODE != "one"
    hands = core.make_hands(2 if two_hands else 1)

    import tkinter
    root = tkinter.Tk()
    settings = Settings(root, ctrl, mouse)
    commands = queue.Queue()
    tray = None
    if core.MENUBAR_ENABLED:
        try:
            tray = Tray(ctrl, settings, commands)
        except Exception as exc:   # pystray/Pillow mancanti: si va avanti con la sola anteprima
            core.log(f"Icona nell'area di notifica non disponibile: {exc}")
    print("In esecuzione. Q = esci, S = Impostazioni, P = pausa (nella finestra di anteprima).")

    def handle(command):
        if command == "toggle":
            ctrl.set_paused(not ctrl.paused)
        elif command == "settings":
            settings.show()
        elif command == "stoprec":
            settings.stop_macro(from_tray=True)
        elif command == "quit":
            return True
        return False

    try:
        while True:
            while not commands.empty():
                if handle(commands.get_nowait()):
                    return
            if settings.camera_dirty:
                settings.camera_dirty = False
                cap = switch_camera(cap, mouse)
            if (core.HAND_MODE != "one") != two_hands:   # cambiata la modalita' mani dalle Impostazioni
                two_hands = core.HAND_MODE != "one"
                hands.close()
                hands = core.make_hands(2 if two_hands else 1)
            ok, frame = cap.read()
            if not ok:
                root.update()
                continue
            if frame.shape[1] > core.CAMERA_WIDTH:
                frame = cv2.resize(frame, (core.CAMERA_WIDTH, round(frame.shape[0] * core.CAMERA_WIDTH / frame.shape[1])))
            if core.MIRROR:
                frame = cv2.flip(frame, 1)
            core.FRAME_ASPECT = frame.shape[1] / frame.shape[0]
            results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            now = time.monotonic()
            label = core.process_hands(ctrl, results, now)

            settings.refresh(label)
            root.update()
            if tray:
                tray.update()

            if core.SHOW_PREVIEW:
                shown = label + ("  [TEST]" if mouse.dry_run else "")
                cv2.imshow("Hand Gesture Mouse", core.draw_preview(frame, results, shown, ctrl.paused, cap.name))
                key = cv2.waitKey(1) & 0xFF
                if key in (ord(core.QUIT_KEY), ord(core.QUIT_KEY.upper())):
                    break
                if key in (ord("s"), ord("S")):
                    settings.show()
                if key in (ord("p"), ord("P")):
                    ctrl.set_paused(not ctrl.paused)
    except KeyboardInterrupt:
        pass
    finally:
        mouse.release(*ctrl.cursor)
        core.save_settings()
        if tray:
            tray.stop()
        hands.close()
        cap.release()
        cv2.destroyAllWindows()
        try:
            root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        err = traceback.format_exc()
        core.log(err)
        fail("Errore imprevisto", err[-700:])
