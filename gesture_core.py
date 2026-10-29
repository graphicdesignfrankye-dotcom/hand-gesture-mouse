"""Hand Gesture Mouse - logica comune (indipendente dal sistema operativo).

Qui ci sono: configurazione, impostazioni salvate, riconoscimento dei gesti, sequenze registrate, smoothing,
anteprima e tracking MediaPipe. Le parti che toccano il sistema (mouse, tastiera, webcam, icona, finestre)
stanno in hand_mouse.py (macOS) e hand_mouse_win.py (Windows).
"""

import json
import math
import os
import sys
import threading
import time
import types
from collections import Counter, deque

import cv2

# MediaPipe importa matplotlib solo per plot_landmarks(), che qui non serve; caricarlo costa
# ~20 s ad ogni avvio (ricostruisce la cache dei font), quindi lo sostituiamo con un modulo vuoto.
for _name in ("matplotlib", "matplotlib.pyplot"):
    sys.modules.setdefault(_name, types.ModuleType(_name))
sys.modules["matplotlib"].pyplot = sys.modules["matplotlib.pyplot"]

import mediapipe as mp  # noqa: E402

# =============================================================================
# CONFIG - modifica a piacere
# =============================================================================

# --- Camera ------------------------------------------------------------------
CAMERA_INDEX = 0            # 0 = webcam integrata; prova 1 se hai una seconda camera
CAMERA_ID = ""              # webcam scelta dalle Impostazioni (ID univoco); vuoto = usa CAMERA_INDEX
CAMERA_WIDTH = 640          # i frame vengono ridotti a questa larghezza (piu' veloce, basta per le mani)
MIRROR = True               # specchia l'immagine, come davanti a uno specchio

# --- Tracking della mano -----------------------------------------------------
MODEL_COMPLEXITY = 0        # 0 = veloce, 1 = piu' preciso (piu' lento)
# Mani usate: "one" = una mano fa tutto; "two_right" = cursore e click con la destra, gesti-azione con la
# sinistra; "two_left" = il contrario. Si cambia dalle Impostazioni (scheda Generale).
HAND_MODE = "one"
DETECTION_CONFIDENCE = 0.7
TRACKING_CONFIDENCE = 0.6

# --- Mappatura del cursore ---------------------------------------------------
# Solo la parte centrale dell'inquadratura viene mappata su tutto lo schermo.
# Margine = frazione di inquadratura ignorata per lato (0.20 -> usa il 60% centrale).
ACTIVE_MARGIN_X = 0.20
ACTIVE_MARGIN_Y = 0.20
SENSITIVITY = 1.0           # >1 = il cursore corre di piu' per ogni movimento, <1 = piu' fine

# --- Smoothing ---------------------------------------------------------------
SMOOTHING = 0.70            # 0 = grezzo/tremolante ... 0.95 = molto fluido ma in ritardo
SMOOTHING_SPEED_GAIN = 0.01 # lo smoothing si allenta nei movimenti veloci, cosi' il cursore sta al passo
DEADZONE_PX = 4             # ignora movimenti del cursore piu' piccoli di questo (elimina il tremolio)

# --- Pizzico / click ---------------------------------------------------------
# Le distanze sono relative alla grandezza della mano (polso -> nocca del medio),
# quindi funzionano a qualsiasi distanza dalla camera.
PINCH_START = 0.30          # punte delle dita piu' vicine di questo = inizia il pizzico
PINCH_RELEASE = 0.45        # piu' lontane di questo = il pizzico finisce (isteresi)
DRAG_HOLD_SEC = 0.40        # pizzico tenuto piu' a lungo = click e trascinamento
CLICK_COOLDOWN_SEC = 0.25   # tempo minimo tra due click sinistri
RIGHT_CLICK_COOLDOWN_SEC = 0.60
DOUBLE_CLICK_SEC = 0.50     # due click entro questo tempo e ~30 px = doppio click

# --- Scroll ------------------------------------------------------------------
SCROLL_SPEED = 1800         # pixel scorsi per un'intera altezza di inquadratura percorsa dalla mano
SCROLL_DEADZONE = 0.003     # ignora movimenti della mano piu' piccoli di questo per frame
SCROLL_INVERT = False       # True inverte la direzione

# --- Pausa (pugno) -----------------------------------------------------------
FIST_HOLD_SEC = 0.60        # tieni il pugno per tanto tempo per attivare/disattivare la pausa
LOST_HAND_RELEASE_SEC = 0.40  # rilascia un trascinamento se la mano sparisce per tanto tempo

# --- Azioni dei gesti --------------------------------------------------------
# Gesti "a posa": vanno tenuti fermi per ACTION_HOLD_SEC, poi parte l'azione assegnata.
# Tre dita alzate = "three", indice + mignolo alzati = "rock".
# L'azione si cambia dalla finestra Impostazioni (scheda Azioni); le azioni disponibili sono in ACTIONS.
ACTION_HOLD_SEC = 0.70
ACTION_COOLDOWN_SEC = 1.5   # pausa minima tra due azioni
POSE_GRACE_SEC = 0.30       # un gesto che sparisce per meno di questo tempo non viene considerato interrotto

# --- Volume con la mano ------------------------------------------------------
VOLUME_GESTURE = True       # mano aperta: alzarla alza il volume, abbassarla lo abbassa
VOLUME_STEP = 0.05          # quanto muovere la mano (frazione dell'inquadratura) per ogni scatto di volume
VOLUME_ARM_SEC = 0.50       # tieni la mano aperta cosi' a lungo prima che il volume risponda

# --- Swipe con la mano aperta ------------------------------------------------
# Con la mano del mouse aperta: spostarla a sinistra / a destra lancia l'azione scelta per quella direzione.
SWIPE_DISTANCE = 0.45       # quanto spostare la mano (in grandezze della mano, ~ 1 = larghezza del palmo)
SWIPE_COOLDOWN_SEC = 1.0    # pausa dopo uno swipe: evita che il ritorno della mano conti come uno swipe opposto
SWIPE_ARM_SEC = 0.25        # la mano deve essere aperta da almeno questo tempo

# --- Movimenti registrati ----------------------------------------------------
MOTION_THRESHOLD = 0.16     # piu' alto = riconosce anche movimenti meno precisi
MOTION_COOLDOWN_SEC = 1.5   # pausa minima tra due movimenti riconosciuti
GESTURE_ACTIONS = {"three": "next_display", "rock": "fullscreen", "pinky": "call_toggle"}   # modalita' una mano
SWIPE_ACTIONS = {"left": "none", "right": "none"}   # azione dello swipe a mano aperta, per direzione
# Modalita' due mani: la mano libera ha piu' pose a disposizione.
GESTURE_ACTIONS_TWO = {"one": "none", "two": "none", "three": "next_display", "pinky": "call_toggle",
                       "rock": "fullscreen", "fist": "none"}

# --- Rilevamento delle dita --------------------------------------------------
EXTEND_RATIO = 1.15         # rapporto distanza-dal-polso punta/nocca per considerare un dito "esteso"

# --- Finestra di anteprima ---------------------------------------------------
SHOW_PREVIEW = True
PREVIEW_WIDTH = 480
QUIT_KEY = "q"

# --- Icona nella barra dei menu ----------------------------------------------
MENUBAR_ENABLED = True
MENUBAR_TITLE_ACTIVE = "✋"   # icona quando il tracking e' attivo
MENUBAR_TITLE_PAUSED = "⏸"   # icona quando e' in pausa

# =============================================================================
# Indici dei landmark (MediaPipe Hands)
# =============================================================================
WRIST, THUMB_TIP = 0, 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_PIP, PINKY_TIP = 18, 20
FINGERS = [  # (pip, punta) per indice, medio, anulare, mignolo
    (INDEX_PIP, INDEX_TIP),
    (MIDDLE_PIP, MIDDLE_TIP),
    (RING_PIP, RING_TIP),
    (PINKY_PIP, PINKY_TIP),
]

# =============================================================================
# Impostazioni salvate (modificabili dalla finestra Impostazioni)
# =============================================================================
# (nome costante, etichetta, minimo, massimo, formato). I valori di CONFIG qui sopra
# sono i predefiniti; quelli salvati nel file JSON li sostituiscono all'avvio.
TUNABLES = [
    ("SENSITIVITY", "Sensibilità", 0.5, 2.0, "{:.2f}"),
    ("ACTIVE_MARGIN_X", "Margine area attiva X", 0.05, 0.40, "{:.2f}"),
    ("ACTIVE_MARGIN_Y", "Margine area attiva Y", 0.05, 0.40, "{:.2f}"),
    ("SMOOTHING", "Smoothing", 0.0, 0.95, "{:.2f}"),
    ("DEADZONE_PX", "Zona morta (px)", 0, 15, "{:d}"),
    ("PINCH_START", "Pizzico: inizio", 0.15, 0.50, "{:.2f}"),
    ("PINCH_RELEASE", "Pizzico: rilascio", 0.25, 0.70, "{:.2f}"),
    ("DRAG_HOLD_SEC", "Attesa trascinamento (s)", 0.2, 1.0, "{:.2f}"),
    ("CLICK_COOLDOWN_SEC", "Cooldown click (s)", 0.1, 0.8, "{:.2f}"),
    ("SCROLL_SPEED", "Velocità scroll", 500, 4000, "{:d}"),
    ("FIST_HOLD_SEC", "Attesa pugno (s)", 0.3, 1.5, "{:.2f}"),
    ("VOLUME_STEP", "Volume: movimento per scatto", 0.02, 0.15, "{:.2f}"),
    ("VOLUME_ARM_SEC", "Volume: attesa mano aperta (s)", 0.2, 1.5, "{:.2f}"),
    ("MOTION_THRESHOLD", "Movimenti: tolleranza", 0.08, 0.30, "{:.2f}"),
    ("SWIPE_DISTANCE", "Swipe: distanza minima", 0.2, 2.0, "{:.2f}"),
    ("SWIPE_COOLDOWN_SEC", "Swipe: pausa tra due swipe (s)", 0.4, 2.0, "{:.2f}"),
    ("ACTION_HOLD_SEC", "Attesa gesti azione (s)", 0.3, 1.5, "{:.2f}"),
    ("ACTION_COOLDOWN_SEC", "Pausa tra azioni (s)", 0.5, 3.0, "{:.2f}"),
]
SETTING_KEYS = [t[0] for t in TUNABLES] + ["SCROLL_INVERT", "VOLUME_GESTURE"]
DEFAULTS = {k: globals()[k] for k in SETTING_KEYS}
DEFAULT_GESTURE_ACTIONS = dict(GESTURE_ACTIONS)
DEFAULT_SWIPE_ACTIONS = dict(SWIPE_ACTIONS)
DEFAULT_GESTURE_ACTIONS_TWO = dict(GESTURE_ACTIONS_TWO)
DEFAULT_HAND_MODE = HAND_MODE
HAND_MODES = [  # (chiave, nome mostrato)
    ("one", "Una mano (cursore e gesti insieme)"),
    ("two_right", "Due mani: cursore con la destra, azioni con la sinistra"),
    ("two_left", "Due mani: cursore con la sinistra, azioni con la destra"),
]


# Azioni assegnabili ai gesti: (chiave, nome breve per l'anteprima, nome completo).
# I nomi con la scorciatoia (es. "Schermo intero (Ctrl+Cmd+F)") li imposta ogni sistema con set_action_text().
ACTIONS = [
    ("none", "Nessuna azione", "Nessuna azione"),
    ("next_display", "Monitor successivo", "Cursore sul monitor successivo"),
    ("fullscreen", "Schermo intero", "Schermo intero"),
    ("mission_control", "Vista attivita", "Panoramica delle finestre"),
    ("space_left", "Desktop a sinistra", "Desktop a sinistra"),
    ("space_right", "Desktop a destra", "Desktop a destra"),
    ("app_switcher", "Cambia app", "Cambia app"),
    ("minimize", "Riduci finestra", "Riduci finestra"),
    ("play_pause", "Play/Pausa musica", "Musica: play / pausa"),
    ("next_track", "Brano successivo", "Musica: brano successivo"),
    ("prev_track", "Brano precedente", "Musica: brano precedente"),
    ("volume_up", "Volume su", "Volume: alza"),
    ("volume_down", "Volume giu", "Volume: abbassa"),
    ("mute", "Muto", "Volume: muto / riattiva"),
    ("screenshot", "Screenshot area", "Screenshot di un'area"),
    ("lock_screen", "Blocca schermo", "Blocca lo schermo"),
    ("spotlight", "Ricerca", "Ricerca di sistema"),
    ("answer_call", "Rispondi chiamata", "Rispondi alla chiamata (click registrato)"),
    ("decline_call", "Rifiuta chiamata", "Rifiuta la chiamata (click registrato)"),
    ("end_call", "Chiudi chiamata", "Chiudi la chiamata (click registrato)"),
    ("call_toggle", "Rispondi/chiudi", "Rispondi alla chiamata, poi chiudila (stesso gesto)"),
]
ACTION_SHORT = {k: short for k, short, _ in ACTIONS}


def set_action_text(texts):
    """Sostituisce nome breve e completo delle azioni con quelli del sistema in uso: {chiave: (breve, completo)}."""
    for i, (key, short, title) in enumerate(ACTIONS):
        if key in texts:
            short, title = texts[key]
            ACTIONS[i] = (key, short, title)
            ACTION_SHORT[key] = short


# Gesti a posa: (chiave, nome completo, nome breve per l'anteprima)
ACTION_GESTURES = [
    ("three", "Tre dita alzate (indice, medio, anulare)", "Tre dita"),
    ("rock", "Indice e mignolo alzati", "Indice+mignolo"),
    ("pinky", "Solo mignolo alzato", "Mignolo"),
]
# Pose della mano libera (modalita' due mani)
FREE_HAND_GESTURES = [
    ("one", "Un dito (indice)", "Un dito"),
    ("two", "Due dita (indice e medio)", "Due dita"),
    ("three", "Tre dita (indice, medio, anulare)", "Tre dita"),
    ("pinky", "Solo mignolo alzato", "Mignolo"),
    ("rock", "Indice e mignolo alzati", "Indice+mignolo"),
    ("fist", "Pugno chiuso", "Pugno libero"),
]
POSE_NAMES = {k: short for k, _, short in ACTION_GESTURES + FREE_HAND_GESTURES}
POSE_NAMES["open"] = "Mano aperta"   # usabile solo per i movimenti registrati (la mano aperta ferma regola il volume)


# Scorciatoie registrate dall'utente: {"id", "label", "code", "flags"}; il significato di code/flags e'
# del sistema operativo in uso (codice tasto e modificatori).
CUSTOM_ACTIONS = []


def register_custom(entry):
    key = entry["id"]
    if key in ACTION_SHORT:
        return
    n = len(CUSTOM_ACTIONS) + 1
    CUSTOM_ACTIONS.append(entry)
    ACTIONS.append((key, f"Scorciatoia {n}", f"Scorciatoia registrata: {entry['label']}"))
    ACTION_SHORT[key] = f"Scorciatoia {n}"


# Sequenze registrate: {"id", "name", "steps"}; ogni passo e' un tasto {"k": "key", "code", "flags", "d"}
# o un click {"k": "click", "x", "y", "b": "left"/"right", "d"}; "d" = pausa prima del passo, in secondi.
MACROS = []
MAX_MACROS = 6
MAX_STEPS = 200


def register_macro(entry):
    key = entry["id"]
    if key in ACTION_SHORT:
        return
    n = len(MACROS) + 1
    MACROS.append(entry)
    ACTIONS.append((key, f"Sequenza {n}", f"Sequenza registrata {n} ({len(entry['steps'])} passi)"))
    ACTION_SHORT[key] = f"Sequenza {n}"


def valid_macro(entry):
    if not (isinstance(entry, dict) and str(entry.get("id", "")).startswith("macro")
            and isinstance(entry.get("steps"), list) and 0 < len(entry["steps"]) <= MAX_STEPS):
        return False
    for st in entry["steps"]:
        if not (isinstance(st, dict) and isinstance(st.get("d"), (int, float))):
            return False
        if st.get("k") == "key":
            if not (isinstance(st.get("code"), int) and isinstance(st.get("flags"), int)):
                return False
        elif st.get("k") == "click":
            if not (isinstance(st.get("x"), (int, float)) and isinstance(st.get("y"), (int, float))
                    and st.get("b") in ("left", "right")):
                return False
        else:
            return False
    return True


def remove_macros():
    for entry in MACROS:
        ACTION_SHORT.pop(entry["id"], None)
        for mapping in (GESTURE_ACTIONS, GESTURE_ACTIONS_TWO, SWIPE_ACTIONS):
            for gesture, action in mapping.items():
                if action == entry["id"]:
                    mapping[gesture] = "none"
        for motion in MOTIONS:
            if motion["action"] == entry["id"]:
                motion["action"] = "none"
    ACTIONS[:] = [a for a in ACTIONS if not a[0].startswith("macro")]
    MACROS.clear()



# Click registrati per rispondere / rifiutare / chiudere una chiamata: {"answer_call": [x, y], ...}
CALL_ACTIONS = ("answer_call", "decline_call", "end_call")
CALL_POINTS = {}

# Movimenti della mano registrati: {"id", "name", "pose", "dur", "length", "points", "action"}.
# "points" e' il tracciato normalizzato (MOTION_POINTS punti); si riconosce con la posa indicata.
MOTIONS = []
MAX_MOTIONS = 6
MOTION_POINTS = 24
MOTION_MIN_LENGTH = 0.35                      # percorso minimo, in "grandezze della mano"
MOTION_MIN_REACH = 0.15                       # spostamento minimo dal punto di partenza
MOTION_START = 0.06                           # spostamento da cui si considera iniziato il movimento
# Punto della mano che si segue per un movimento: la registrazione sceglie quello che si muove di piu'
# (un saluto dal polso muove soprattutto le punte delle dita, uno swipe sposta tutta la mano).
MOTION_TRACKS = ("mcp", "tip", "wrist", "center")
TRACK_NAMES = {"mcp": "nocche", "tip": "punte", "wrist": "polso", "center": "centro"}


# Larghezza / altezza dell'immagine della webcam (la imposta il programma a ogni frame). I landmark sono
# normalizzati separatamente su x e y: senza questo fattore un movimento orizzontale sembra piu' piccolo
# di uno verticale (con una webcam 16:9 di circa il 44%).
FRAME_ASPECT = 1.0


def hand_size(lm):
    """Grandezza della mano (polso -> nocca del medio), misurata in modo uniforme su x e y."""
    return max(math.hypot((lm[WRIST].x - lm[MIDDLE_MCP].x) * FRAME_ASPECT, lm[WRIST].y - lm[MIDDLE_MCP].y), 1e-6)


def hand_points(lm):
    """Posizione (x, y) dei punti che si possono seguire per un movimento (x scalata come l'altezza)."""
    n = len(lm)
    a = FRAME_ASPECT
    return {"mcp": (lm[MIDDLE_MCP].x * a, lm[MIDDLE_MCP].y), "tip": (lm[MIDDLE_TIP].x * a, lm[MIDDLE_TIP].y),
            "wrist": (lm[WRIST].x * a, lm[WRIST].y),
            "center": (sum(p.x for p in lm) * a / n, sum(p.y for p in lm) / n)}


ONE_HAND_MOTION_POSES = ("three", "rock", "pinky", "open")   # in modalita' una mano le altre pose sono del cursore


def register_motion(entry):
    MOTIONS.append(entry)


def remove_motion(motion_id):
    MOTIONS[:] = [m for m in MOTIONS if m["id"] != motion_id]


def valid_motion(e):
    return (isinstance(e, dict) and str(e.get("id", "")).startswith("move") and e.get("pose") in POSE_NAMES
            and e.get("track", "mcp") in MOTION_TRACKS
            and isinstance(e.get("dur"), (int, float)) and isinstance(e.get("length"), (int, float))
            and isinstance(e.get("points"), list) and len(e["points"]) == MOTION_POINTS
            and all(isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p)
                    for p in e["points"]))


def path_length(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def resample(pts, n):
    """Ricampiona un tracciato in n punti equidistanti lungo il percorso."""
    pts = [tuple(p) for p in pts]
    total = path_length(pts)
    if not pts or total < 1e-9:
        return [pts[0]] * n if pts else []
    step = total / (n - 1)
    out, prev, acc, i = [pts[0]], pts[0], 0.0, 1
    while i < len(pts) and len(out) < n:
        cur = pts[i]
        d = math.hypot(cur[0] - prev[0], cur[1] - prev[1])
        if d > 0 and acc + d >= step:
            t = (step - acc) / d
            prev = (prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1]))
            out.append(prev)
            acc = 0.0
        else:
            acc += d
            prev = cur
            i += 1
    while len(out) < n:
        out.append(pts[-1])
    return out


def normalize_motion(pts):
    """Tracciato -> n punti, centrato e scalato sulla sua lunghezza (indipendente da posizione e dimensione)."""
    r = resample(pts, MOTION_POINTS)
    length = path_length(r) or 1e-9
    cx = sum(p[0] for p in r) / len(r)
    cy = sum(p[1] for p in r) / len(r)
    return [((p[0] - cx) / length, (p[1] - cy) / length) for p in r]


def bbox_diagonal(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys))


def motion_distance(a, b):
    return sum(math.hypot(p[0] - q[0], p[1] - q[1]) for p, q in zip(a, b)) / len(a)


def remove_customs():
    for entry in CUSTOM_ACTIONS:
        ACTION_SHORT.pop(entry["id"], None)
        for mapping in (GESTURE_ACTIONS, GESTURE_ACTIONS_TWO, SWIPE_ACTIONS):
            for gesture, action in mapping.items():
                if action == entry["id"]:
                    mapping[gesture] = "none"
        for motion in MOTIONS:
            if motion["action"] == entry["id"]:
                motion["action"] = "none"
    ACTIONS[:] = [a for a in ACTIONS if not a[0].startswith("custom")]
    CUSTOM_ACTIONS.clear()


SETTINGS_PATH = os.path.join(os.path.expanduser("~"), "Hand Gesture Mouse settings.json")   # lo imposta il sistema
LOG_PATH = os.path.join(os.path.expanduser("~"), "Hand Gesture Mouse.log")                    # lo imposta il sistema


def log(msg):
    """Scrive su file (l'app non ha console) e su stderr."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        print(line, file=sys.stderr)
    except Exception:   # console non UTF-8 (Windows) o senza console: il log su file basta
        pass
    try:
        with open(LOG_PATH, "a", encoding="utf-8", errors="replace") as f:   # UTF-8: su Windows il predefinito (cp1252) non sa scrivere frecce e simboli
            f.write(line + "\n")
    except OSError:
        pass


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    limits = {t[0]: (t[2], t[3]) for t in TUNABLES}
    for k in SETTING_KEYS:
        v = data.get(k) if isinstance(data, dict) else None
        if isinstance(v, (int, float)):
            if k in limits:
                v = min(max(v, limits[k][0]), limits[k][1])
            globals()[k] = type(DEFAULTS[k])(v)
    if isinstance(data, dict):
        if data.get("HAND_MODE") in [m[0] for m in HAND_MODES]:
            globals()["HAND_MODE"] = data["HAND_MODE"]
        if isinstance(data.get("CAMERA_ID"), str):
            globals()["CAMERA_ID"] = data["CAMERA_ID"]
    for entry in (data.get("CUSTOM_ACTIONS") if isinstance(data, dict) else None) or []:
        if (isinstance(entry, dict) and str(entry.get("id", "")).startswith("custom")
                and isinstance(entry.get("label"), str) and isinstance(entry.get("code"), int)
                and isinstance(entry.get("flags"), int)):
            register_custom(dict(entry))
    for entry in (data.get("MACROS") if isinstance(data, dict) else None) or []:
        if valid_macro(entry):
            register_macro({k: entry[k] for k in ("id", "name", "steps")})
    if isinstance(data, dict) and isinstance(data.get("MOTIONS"), list):
        MOTIONS.clear()
        for entry in data["MOTIONS"]:
            if valid_motion(entry) and len(MOTIONS) < MAX_MOTIONS:
                action = entry.get("action") if entry.get("action") in ACTION_SHORT else "none"
                register_motion({k: entry[k] for k in ("id", "name", "pose", "dur", "length", "points")}
                                | {"action": action, "track": entry.get("track", "mcp")})
    calls = data.get("CALL_POINTS") if isinstance(data, dict) else None
    if isinstance(calls, dict):
        for key in CALL_ACTIONS:
            pt = calls.get(key)
            if isinstance(pt, (list, tuple)) and len(pt) == 2 and all(isinstance(v, (int, float)) for v in pt):
                CALL_POINTS[key] = [float(pt[0]), float(pt[1])]
    saved_swipe = data.get("SWIPE_ACTIONS") if isinstance(data, dict) else None
    if isinstance(saved_swipe, dict):
        for direction in ("left", "right"):
            if saved_swipe.get(direction) in ACTION_SHORT:
                SWIPE_ACTIONS[direction] = saved_swipe[direction]
    for name, mapping, gestures in (("GESTURE_ACTIONS", GESTURE_ACTIONS, ACTION_GESTURES),
                                    ("GESTURE_ACTIONS_TWO", GESTURE_ACTIONS_TWO, FREE_HAND_GESTURES)):
        saved = data.get(name) if isinstance(data, dict) else None
        if isinstance(saved, dict):
            for gesture, _, _ in gestures:
                if saved.get(gesture) in ACTION_SHORT:
                    mapping[gesture] = saved[gesture]


def save_settings():
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    data = {k: globals()[k] for k in SETTING_KEYS}
    data["GESTURE_ACTIONS"] = GESTURE_ACTIONS
    data["GESTURE_ACTIONS_TWO"] = GESTURE_ACTIONS_TWO
    data["CUSTOM_ACTIONS"] = CUSTOM_ACTIONS
    data["MACROS"] = MACROS
    data["MOTIONS"] = MOTIONS
    data["SWIPE_ACTIONS"] = SWIPE_ACTIONS
    data["CALL_POINTS"] = CALL_POINTS
    data["HAND_MODE"] = HAND_MODE
    data["CAMERA_ID"] = CAMERA_ID
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# Gesto mostrato nell'anteprima -> voce della lista di test
LABEL_KEYS = {"Muovi": "move", "Trascinamento": "drag", "Click destro": "right",
              "Scroll": "scroll", "Pugno": "fist"}


def dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))



class MouseBase:
    """Logica comune di mouse e tastiera: monitor, modalita' test, registro dei comandi, sequenze registrate.

    Ogni sistema operativo ne deriva una classe che implementa solo le primitive: position, _list_displays,
    _warp, _emit_move, _emit_button, _emit_scroll, _emit_key, _emit_action, supports e (se serve) _trusted.
    """

    permission_name = "permessi"

    def __init__(self):
        self.displays = self._list_displays()
        self._use_display(self._display_under(*self.position()))
        self.dragging = False
        self.replaying = False          # True mentre una sequenza registrata e' in esecuzione
        self.dry_run = False            # modalita' test: riconosce i gesti ma non muove il mouse vero
        self.events = deque(maxlen=5)   # ultimi comandi, mostrati nella finestra Impostazioni

    # --- primitive del sistema operativo --------------------------------------------------
    def position(self):
        raise NotImplementedError

    def _list_displays(self):
        """Monitor attivi come (x, y, larghezza, altezza), ordinati da sinistra a destra."""
        raise NotImplementedError

    def _warp(self, x, y):
        raise NotImplementedError

    def _emit_move(self, x, y, dragging):
        raise NotImplementedError

    def _emit_button(self, button, down, x, y, clicks):
        """button = "left" o "right"; down = True (premuto) / False (rilasciato)."""
        raise NotImplementedError

    def _emit_scroll(self, pixels):
        raise NotImplementedError

    def _emit_key(self, code, flags):
        """Preme e rilascia un tasto con i suoi modificatori (codici propri del sistema)."""
        raise NotImplementedError

    def _emit_action(self, action):
        """Esegue un'azione predefinita (scorciatoia o tasto multimediale)."""
        raise NotImplementedError

    def supports(self, action):
        return False

    def _trusted(self):
        return True

    # --- monitor ----------------------------------------------------------------------
    def _display_under(self, x, y):
        for i, (x0, y0, w, h) in enumerate(self.displays):
            if x0 <= x < x0 + w and y0 <= y < y0 + h:
                return i
        return 0

    def _use_display(self, i):
        self.index = i
        self.x0, self.y0, self.width, self.height = self.displays[i]

    def next_display(self):
        """Passa al monitor successivo: la mano controlla quello e il cursore ci salta al centro."""
        self.displays = self._list_displays()
        n = len(self.displays)
        if n < 2:
            self.events.append("Un solo monitor collegato")
            return None
        i = (self.index + 1) % n
        self.events.append(f"Cursore sul monitor {i + 1} di {n}")
        if self.dry_run:
            return None
        self._check_permission(f"cursore sul monitor {i + 1} di {n}")
        self._use_display(i)
        center = (self.x0 + self.width / 2, self.y0 + self.height / 2)
        self._warp(*center)
        self.move(*center)
        return center

    def _check_permission(self, what):
        """Registra l'azione e avvisa se manca il permesso (i comandi verrebbero ignorati)."""
        if self.dry_run:
            return
        if self._trusted():
            log(f"Azione eseguita: {what}")
        else:
            log(f"Azione NON eseguita ({what}): manca il permesso {self.permission_name}")
            self.events.append(f"MANCA il permesso {self.permission_name}!")

    # --- tastiera e sequenze -------------------------------------------------------------
    def shortcut(self, action):
        """Esegue la scorciatoia (predefinita o registrata) associata a un'azione."""
        name = next(t for k, _, t in ACTIONS if k == action)
        self.events.append(name)
        if self.dry_run:
            return
        self._check_permission(name)
        if action.startswith("custom"):
            entry = next((e for e in CUSTOM_ACTIONS if e["id"] == action), None)
            if entry:
                self._emit_key(entry["code"], entry["flags"])
        else:
            self._emit_action(action)

    def volume_step(self, up, count=1):
        """Alza/abbassa il volume di qualche scatto (tasto multimediale); un solo messaggio nell'elenco comandi."""
        if self.events and self.events[-1].startswith("Volume:"):
            self.events.pop()
        self.events.append("Volume: su" if up else "Volume: giù")
        if self.dry_run:
            return
        if not self._trusted():
            self.events.append(f"MANCA il permesso {self.permission_name}!")
            return
        for _ in range(count):
            self._emit_action("volume_up" if up else "volume_down")

    def run_macro(self, steps, on_done=None, name=None):
        """Esegue una sequenza registrata su un thread a parte, cosi' la camera non si ferma."""
        self.events.append(name or f"Sequenza di {len(steps)} passi")
        if self.dry_run or self.replaying:
            return
        self._check_permission(f"sequenza di {len(steps)} passi")
        self.replaying = True
        threading.Thread(target=self._play, args=(steps, on_done), daemon=True).start()

    def _play(self, steps, on_done):
        pos = None
        try:
            for st in steps:
                time.sleep(min(max(st["d"], 0.05), 3.0))
                if st["k"] == "key":
                    self._emit_key(st["code"], st["flags"])
                    continue
                x, y = st["x"], st["y"]
                pos = (x, y)
                self._emit_move(x, y, False)
                time.sleep(0.04)
                self._click(st["b"], x, y, 1)
        except Exception as exc:
            log(f"Errore durante la sequenza: {exc}")
        finally:
            self.replaying = False
            if on_done and pos:
                on_done(pos)

    # --- mouse ----------------------------------------------------------------------
    def move(self, x, y):
        if self.dry_run or self.replaying:
            return
        self._emit_move(x, y, self.dragging)

    def _click(self, button, x, y, clicks):
        if self.dry_run:
            return
        self._emit_button(button, True, x, y, clicks)
        self._emit_button(button, False, x, y, clicks)

    def left_click(self, x, y, clicks=1):
        self.events.append("Doppio click sinistro" if clicks == 2 else "Click sinistro")
        self._click("left", x, y, clicks)

    def right_click(self, x, y):
        self.events.append("Click destro")
        self._click("right", x, y, 1)

    def press(self, x, y):
        self.events.append("Trascinamento: inizio")
        if not self.dry_run:
            self._emit_button("left", True, x, y, 1)
        self.dragging = True

    def release(self, x, y):
        if not self.dragging:
            return
        self.events.append("Trascinamento: fine")
        if not self.dry_run:
            self._emit_button("left", False, x, y, 1)
        self.dragging = False

    def scroll(self, pixels):
        if self.dry_run:
            return
        self._emit_scroll(pixels)


class CursorSmoother:
    """Smoothing esponenziale che si allenta nei movimenti veloci e tiene fermo il cursore su quelli minuscoli."""

    def __init__(self):
        self.pos = None

    def update(self, x, y):
        if self.pos is None:
            self.pos = (x, y)
            return self.pos
        px, py = self.pos
        d = math.hypot(x - px, y - py)
        if d < DEADZONE_PX:
            return self.pos
        s = SMOOTHING / (1.0 + d * SMOOTHING_SPEED_GAIN)
        self.pos = (px + (x - px) * (1 - s), py + (y - py) * (1 - s))
        return self.pos


class GestureController:
    def __init__(self, mouse):
        self.mouse = mouse
        self.smoother = CursorSmoother()
        self.cursor = mouse.position()

        self.paused = False
        self.fist_since = None
        self.fist_latched = False

        self.idx_pinch = False
        self.mid_pinch = False
        self.pinch_start = 0.0
        self.last_click_t = -1e9
        self.last_click_pos = (0.0, 0.0)
        self.click_count = 0
        self.last_right_t = -1e9

        self.scroll_y = None
        self.scroll_acc = 0.0
        self.lost_since = None

        self.pose = None            # gesto a posa in corso ("three", "rock") e da quando
        self.pose_since = 0.0
        self.pose_fired = False
        self.pose_cand = None
        self.pose_cand_since = 0.0
        self.last_action_t = -1e9
        self.call_active_since = None   # da quando ho risposto con «Rispondi/chiudi» (il prossimo gesto chiude)

        self.vol_since = None       # mano aperta: da quando, ultimo istante visto e altezza di riferimento
        self.vol_seen = 0.0
        self.vol_ref = None
        self.vol_hist = deque()
        self.vol_label_until = 0.0
        self.vol_label = ""

        self.swipe_buf = deque()    # tracciato della mano aperta (ultimo mezzo secondo)
        self.swipe_since = None
        self.swipe_fire_t = -1e9
        self.swipe_label = ""
        self.swipe_label_until = 0.0

        self.motion_buf = deque()   # (t, x, y, grandezza) della mano nella posa dei movimenti registrati
        self.motion_pose = None
        self.motion_fire_t = -1e9
        self.motion_label = ""
        self.motion_label_until = 0.0
        self.rec = None             # registrazione di un movimento in corso
        self.motion_message = ""    # esito/avanzamento della registrazione, mostrato nelle Impostazioni
        self.cue = None             # funzione(tipo) del sistema che suona un segnale: tick, start, ok, fail
        self.motions_changed = False

        self.verified = set()   # gesti riconosciuti dall'ultimo azzeramento (lista di test)
        self.debug = None       # (dist. pollice-indice, pollice-medio, dita estese) dell'ultimo frame

    # -- funzioni di supporto -------------------------------------------------
    def _map_to_screen(self, nx, ny):
        ax = (nx - ACTIVE_MARGIN_X) / (1 - 2 * ACTIVE_MARGIN_X)
        ay = (ny - ACTIVE_MARGIN_Y) / (1 - 2 * ACTIVE_MARGIN_Y)
        ax = clamp((ax - 0.5) * SENSITIVITY + 0.5, 0.0, 1.0)
        ay = clamp((ay - 0.5) * SENSITIVITY + 0.5, 0.0, 1.0)
        m = self.mouse
        return m.x0 + ax * (m.width - 1), m.y0 + ay * (m.height - 1)

    def _move_cursor(self, tip):
        tx, ty = self._map_to_screen(tip.x, tip.y)
        self.cursor = self.smoother.update(tx, ty)
        self.mouse.move(*self.cursor)

    @staticmethod
    def _extended(lm, pip, tip):
        return dist(lm[WRIST], lm[tip]) > dist(lm[WRIST], lm[pip]) * EXTEND_RATIO

    def _reset_pinches(self):
        self.mouse.release(*self.cursor)
        self.idx_pinch = False
        self.mid_pinch = False
        self.scroll_y = None
        self.scroll_acc = 0.0

    def set_paused(self, paused):
        """Attiva/disattiva la pausa (usato da pugno e menu); in pausa rilascia ogni pulsante premuto."""
        self.paused = paused
        if paused:
            self._reset_pinches()

    # -- punti di ingresso per ogni frame -------------------------------------
    def free_hand_lost(self):
        """La mano dei gesti-azione non si vede: azzera posa, volume e tracciato del movimento."""
        self.pose = None
        self.vol_since = None
        self.vol_hist.clear()
        self.motion_buf.clear()
        self.motion_pose = None

    def no_hand(self, now):
        self.debug = None
        self.fist_since = None
        self.fist_latched = False
        self.scroll_y = None
        self.scroll_acc = 0.0
        if self.lost_since is None:
            self.lost_since = now
        if now - self.lost_since > LOST_HAND_RELEASE_SEC:
            self._reset_pinches()
        return "Nessuna mano"

    def update(self, lm, now, actions=True):
        """Elabora un frame di landmark e restituisce il nome del gesto.

        actions=False (modalita' due mani) ignora i gesti a posa: li gestisce l'altra mano.
        """
        self.lost_since = None
        prev_pose = self.pose
        if actions:
            self.pose = None
        size = max(dist(lm[WRIST], lm[MIDDLE_MCP]), 1e-6)
        d_ti = dist(lm[THUMB_TIP], lm[INDEX_TIP]) / size
        d_tm = dist(lm[THUMB_TIP], lm[MIDDLE_TIP]) / size
        ext = [self._extended(lm, pip, tip) for pip, tip in FINGERS]  # indice..mignolo
        self.debug = (d_ti, d_tm, ext)
        if not all(ext):
            self.swipe_since = None   # la mano non e' piu' aperta: lo swipe riparte da capo
        if actions and self.rec is not None:   # sto registrando un movimento: il cursore resta fermo
            return self._record_frame(lm, "open" if all(ext) else self._free_pose(ext), now)
        self._volume_check_idle(actions and VOLUME_GESTURE and all(ext), now)

        # --- pugno: pausa / ripresa (ignorato mentre un pizzico e' in corso) ---
        if not any(ext) and not (self.idx_pinch or self.mid_pinch):
            if self.fist_since is None:
                self.fist_since = now
            elif not self.fist_latched and now - self.fist_since >= FIST_HOLD_SEC:
                self.set_paused(not self.paused)
                self.fist_latched = True
            return "Pugno (cambio pausa...)" if not self.fist_latched else "Pugno"
        self.fist_since = None
        self.fist_latched = False

        if self.paused:
            return "IN PAUSA - tieni il pugno per riprendere"

        # --- rilevamento del pizzico con isteresi -----------------------------
        thr_i = PINCH_RELEASE if self.idx_pinch else PINCH_START
        thr_m = PINCH_RELEASE if self.mid_pinch else PINCH_START
        want_idx = d_ti < thr_i and not self.mid_pinch and (self.idx_pinch or d_ti <= d_tm)
        want_mid = d_tm < thr_m and not self.idx_pinch and (self.mid_pinch or d_tm < d_ti)

        # tasto sinistro (pollice + indice)
        if want_idx and not self.idx_pinch:
            self.idx_pinch = True
            self.pinch_start = now
        elif not want_idx and self.idx_pinch:
            self.idx_pinch = False
            if self.mouse.dragging:
                self.mouse.release(*self.cursor)
            elif now - self.pinch_start < DRAG_HOLD_SEC and now - self.last_click_t >= CLICK_COOLDOWN_SEC:
                self._left_click(now)

        # tasto destro (pollice + medio)
        if want_mid and not self.mid_pinch:
            self.mid_pinch = True
            if now - self.last_right_t >= RIGHT_CLICK_COOLDOWN_SEC:
                self.last_right_t = now
                self.mouse.right_click(*self.cursor)
        elif not want_mid:
            self.mid_pinch = False

        # --- agisci in base alla posa attuale ---------------------------------
        if self.idx_pinch:
            if not self.mouse.dragging and now - self.pinch_start >= DRAG_HOLD_SEC:
                self.mouse.press(*self.cursor)
            if self.mouse.dragging:
                self._move_cursor(lm[INDEX_TIP])
                return "Trascinamento"
            return "Pizzico (click)"   # cursore fermo, cosi' il click cade dove hai puntato
        if self.mid_pinch:
            return "Click destro"

        if all(ext):   # mano aperta: swipe, poi movimenti registrati e volume (solo la mano dei gesti)
            fired = self._swipe_step(lm, now)
            if fired:
                return fired
            if not actions:
                return "Mano aperta"
            fired = self._motion_step("open", lm, now)
            if fired:
                return fired
            return self._volume(lm, now) if VOLUME_GESTURE else "Mano aperta"
        if actions:
            motion_pose = self._free_pose(ext)
            fired = self._motion_step(motion_pose if motion_pose in ONE_HAND_MOTION_POSES else None, lm, now)
            if fired:
                return fired
        pose = self._filter_pose(self._action_pose(ext), prev_pose, now) if actions else None
        if pose:
            self.scroll_y = None
            self.scroll_acc = 0.0
            return self._hold_pose(pose, prev_pose, now)

        if ext[0] and ext[1] and not ext[2] and not ext[3]:
            self._scroll((lm[INDEX_TIP].y + lm[MIDDLE_TIP].y) / 2)
            return "Scroll"
        self.scroll_y = None
        self.scroll_acc = 0.0

        if ext[0] and not ext[1]:
            self._move_cursor(lm[INDEX_TIP])
            return "Muovi"
        return "Inattivo"

    # -- gesti a posa -----------------------------------------------------------
    @staticmethod
    def _pose_map():
        return GESTURE_ACTIONS if HAND_MODE == "one" else GESTURE_ACTIONS_TWO

    @staticmethod
    def _free_pose(ext):
        """Pose della mano libera (due mani). La mano aperta (tutte le dita alzate) e' riposo e non e' una posa."""
        return {(False, False, False, False): "fist", (True, False, False, False): "one",
                (True, True, False, False): "two", (True, True, True, False): "three",
                (False, False, False, True): "pinky", (True, False, False, True): "rock"}.get(tuple(ext))

    @staticmethod
    def _action_pose(ext):
        if ext[0] and ext[1] and ext[2] and not ext[3]:
            return "three"
        if ext[0] and ext[3] and not ext[1] and not ext[2]:
            return "rock"
        if ext[3] and not (ext[0] or ext[1] or ext[2]):
            return "pinky"
        return None

    def _filter_pose(self, raw, prev_pose, now):
        """Evita che un riconoscimento instabile azzeri il gesto: passare da una posa a un'altra (o a
        nessuna) deve durare POSE_GRACE_SEC. Entrare in una posa da una mano a riposo e' immediato."""
        if raw == prev_pose or prev_pose is None:
            self.pose_cand = None
            return raw
        if raw != self.pose_cand:
            self.pose_cand, self.pose_cand_since = raw, now
        if now - self.pose_cand_since >= POSE_GRACE_SEC:
            self.pose_cand = None
            return raw
        return prev_pose

    def update_actions(self, lm, now):
        """Mano libera (modalita' due mani): riconosce solo i gesti a posa. None se nessuno."""
        ext = [self._extended(lm, pip, tip) for pip, tip in FINGERS]
        if self.rec is not None:
            return self._record_frame(lm, "open" if all(ext) else self._free_pose(ext), now)
        prev_pose, self.pose = self.pose, None
        open_hand = all(ext)
        self._volume_check_idle(VOLUME_GESTURE and open_hand, now)
        if self.paused:
            return None
        if open_hand:
            fired = self._motion_step("open", lm, now)
            if fired:
                return fired
            return self._volume(lm, now) if VOLUME_GESTURE else None
        pose = self._filter_pose(self._free_pose(ext), prev_pose, now)
        fired = self._motion_step(pose, lm, now)
        if fired:
            return fired
        if not pose:
            return None
        return self._hold_pose(pose, prev_pose, now)

    # -- swipe con la mano aperta -------------------------------------------------------
    SWIPE_WINDOW = 0.5   # secondi su cui si misura lo spostamento

    def _swipe_step(self, lm, now):
        """Mano aperta spostata a sinistra o a destra: lancia l'azione assegnata a quella direzione."""
        if self.swipe_since is None:
            self.swipe_since = now
            self.swipe_buf.clear()
        buf = self.swipe_buf
        buf.append((now, hand_points(lm), hand_size(lm)))
        while buf and now - buf[0][0] > self.SWIPE_WINDOW:
            buf.popleft()
        shown = self.swipe_label if now < self.swipe_label_until else None
        if (now - self.swipe_since < SWIPE_ARM_SEC or now - self.swipe_fire_t < SWIPE_COOLDOWN_SEC
                or len(buf) < 4 or self.paused):
            return shown
        size = sorted(p[2] for p in buf)[len(buf) // 2]
        best = None   # (spostamento, direzione nell'immagine: +1 = x crescente)
        for track in ("mcp", "tip", "center"):
            xs = [p[1][track][0] / size for p in buf]
            ys = [p[1][track][1] / size for p in buf]
            right = left = 0.0
            lo = hi = xs[0]
            for x in xs:
                lo, hi = min(lo, x), max(hi, x)
                right, left = max(right, x - lo), max(left, hi - x)
            d, sign = (right, 1) if right >= left else (left, -1)
            if d >= SWIPE_DISTANCE and (max(ys) - min(ys)) <= 0.8 * d and (best is None or d > best[0]):
                best = (d, sign)
        if best is None:
            return shown
        # con l'immagine specchiata la destra dell'immagine e' la destra dell'utente
        direction = "right" if (best[1] > 0) == MIRROR else "left"
        action = SWIPE_ACTIONS.get(direction, "none")
        if action == "none":
            return shown   # nessuna azione per questa direzione: lascio il movimento ai movimenti registrati
        self.swipe_fire_t = now
        buf.clear()
        self.verified.add("swipe_" + direction)
        self._run_action(action)
        side = "destra" if direction == "right" else "sinistra"
        self.swipe_label = f"Swipe a {side} > {ACTION_SHORT.get(action, 'Nessuna azione')}"
        self.swipe_label_until = now + 1.0
        return self.swipe_label

    # -- volume con la mano aperta ----------------------------------------------------
    def _volume_check_idle(self, open_hand, now):
        if not open_hand and self.vol_since is not None and now - self.vol_seen > POSE_GRACE_SEC:
            self.vol_since = None

    def _volume(self, lm, now):
        """Mano aperta: tenuta ferma si "aggancia", poi alzarla/abbassarla alza/abbassa il volume a scatti."""
        y = lm[MIDDLE_MCP].y
        if self.vol_since is None:
            self.vol_since, self.vol_ref = now, None
            self.vol_hist.clear()
        self.vol_seen = now
        hist = self.vol_hist
        hist.append((now, lm[MIDDLE_MCP].x, y))
        while hist and now - hist[0][0] > 0.6:
            hist.popleft()
        if now - self.vol_since < VOLUME_ARM_SEC:
            return "Volume: tieni la mano aperta"
        dx = (max(h[1] for h in hist) - min(h[1] for h in hist)) * FRAME_ASPECT
        dy = max(h[2] for h in hist) - min(h[2] for h in hist)
        if dx > 0.03 and dx > 1.5 * dy:   # movimento orizzontale (un saluto): non e' un comando di volume
            self.vol_ref = y
            return "Mano aperta (movimento)"
        if self.vol_ref is None:
            self.vol_ref = y
        steps = int((self.vol_ref - y) / VOLUME_STEP)   # mano in alto = y piu' piccola
        if steps:
            steps = max(-3, min(3, steps))
            self.vol_ref -= steps * VOLUME_STEP
            self.mouse.volume_step(steps > 0, abs(steps))
            self.verified.add("volume")
            self.vol_label = "Volume: su" if steps > 0 else "Volume: giu"
            self.vol_label_until = now + 0.7
        return self.vol_label if now < self.vol_label_until else "Volume: alza o abbassa la mano"

    def _hold_pose(self, pose, prev_pose, now):
        """Fa partire l'azione assegnata quando la posa viene tenuta abbastanza a lungo."""
        if pose != prev_pose:
            self.pose_since, self.pose_fired = now, False
        self.pose = pose
        action = self._pose_map().get(pose, "none")
        if not self.pose_fired and self._motion_moving(pose, now):
            self.pose_since = now   # sto facendo un movimento registrato: non e' un gesto "tenuto fermo"
        if (not self.pose_fired and now - self.pose_since >= ACTION_HOLD_SEC
                and now - self.last_action_t >= ACTION_COOLDOWN_SEC):
            self.pose_fired = True
            self.last_action_t = now
            self.verified.add(pose if pose in ("three", "rock") else "free_" + pose)
            self._run_action(action)
        if self.pose_fired:
            return f"{POSE_NAMES[pose]} > {ACTION_SHORT.get(action, 'Nessuna azione')}"
        return f"{POSE_NAMES[pose]} (tieni fermo)"

    def _run_action(self, action):
        if action == "next_display":
            center = self.mouse.next_display()
            if center:
                self.cursor = center
                self.smoother.pos = center
        elif action.startswith("custom") or self.mouse.supports(action):
            self.mouse.shortcut(action)
        elif action.startswith("macro"):
            steps = next((m["steps"] for m in MACROS if m["id"] == action), None)
            if steps:
                self.mouse.run_macro(steps, self._after_macro)
        elif action == "call_toggle":
            now = time.monotonic()
            active = self.call_active_since is not None and now - self.call_active_since < 4 * 3600
            step = "end_call" if active else "answer_call"
            if not CALL_POINTS.get(step):
                self.mouse.events.append("Prima registra il click «" + ("Chiudi" if active else "Rispondi") + "» (scheda Generale)")
                return
            self.call_active_since = None if active else now
            self._run_action(step)
        elif action in CALL_ACTIONS:
            point = CALL_POINTS.get(action)
            if not point:
                self.mouse.events.append("Prima registra il click (scheda Generale)")
                return
            title = next(t for k, _, t in ACTIONS if k == action)
            self.mouse.run_macro([{"k": "click", "x": point[0], "y": point[1], "b": "left", "d": 0.05}],
                                 self._after_macro, name=title)

    def _after_macro(self, pos):
        """Dopo una sequenza con click il cursore e' rimasto dove ha cliccato."""
        self.cursor = pos
        self.smoother.pos = pos

    # -- movimenti registrati ------------------------------------------------------------
    MOTION_COUNTDOWN = 3.0    # secondi per prepararsi prima di registrare
    MOTION_SECONDS = 2.5      # durata della registrazione

    def start_motion_recording(self):
        """Registra un movimento della mano: 3 s per prepararsi, poi 2,5 s di movimento."""
        if len(MOTIONS) >= MAX_MOTIONS:
            self.motion_message = f"Massimo {MAX_MOTIONS} movimenti: eliminane qualcuno."
            return
        self.rec = {"phase": "count", "t0": None, "t1": None, "frames": [], "poses": [], "lost": None}
        self.motion_message = "Mostra la mano nella posa scelta: tra poco inizia il conto alla rovescia."

    def _cue(self, kind):
        if self.cue:
            try:
                self.cue(kind)
            except Exception:
                pass

    def cancel_motion_recording(self):
        self.rec = None
        self.motion_message = "Registrazione annullata."

    def _record_frame(self, lm, pose, now):
        rec = self.rec
        rec["lost"] = None
        if rec["t0"] is None:
            rec["t0"] = now
        elapsed = now - rec["t0"]
        if rec["phase"] == "count":
            if elapsed < self.MOTION_COUNTDOWN:
                remaining = int(self.MOTION_COUNTDOWN - elapsed) + 1
                if rec.get("tick") != remaining:
                    rec["tick"] = remaining
                    self._cue("tick")
                self.motion_message = f"Preparati: il movimento inizia tra {remaining}... (aspetta il segnale «ORA»)"
                return f"Movimento: preparati ({remaining})"
            rec["phase"], rec["t1"] = "capture", now
            self._cue("start")
        rec["frames"].append((now, hand_points(lm), hand_size(lm)))
        rec["poses"].append(pose)
        if now - rec["t1"] >= self.MOTION_SECONDS:
            before = len(MOTIONS)
            self._finish_motion()
            log(f"Movimento: {self.motion_message}")
            self._cue("ok" if len(MOTIONS) > before else "fail")
            return "Movimento: fatto"
        self.motion_message = f"ORA! Muovi la mano ({self.MOTION_SECONDS - (now - rec['t1']):.1f} s)"
        return "Movimento: muovi la mano ORA"

    def _finish_motion(self):
        rec, self.rec = self.rec, None
        frames, poses = rec["frames"], rec["poses"]
        if len(frames) < 6:
            self.motion_message = "Mano vista troppo poco: riprova tenendola nell'inquadratura."
            return
        size = sorted(f[2] for f in frames)[len(frames) // 2]
        tracks = {t: [(f[1][t][0] / size, f[1][t][1] / size) for f in frames] for t in MOTION_TRACKS}
        reaches = {t: max(math.hypot(p[0] - pts[0][0], p[1] - pts[0][1]) for p in pts) for t, pts in tracks.items()}
        track = max(reaches, key=reaches.get)   # il punto che si e' mosso di piu'
        pts = tracks[track]
        reach = reaches[track]
        total = path_length(pts)
        seconds = frames[-1][0] - frames[0][0]
        info = (f"{len(frames)} immagini in {seconds:.1f} s; spostamento massimo {reach:.2f} ({TRACK_NAMES[track]}) e "
                f"percorso {total:.2f}, in grandezze della mano (servono almeno {MOTION_MIN_REACH} e {MOTION_MIN_LENGTH})")
        log(f"Registrazione movimento: {info}; spostamento per punto: "
            f"{ {TRACK_NAMES[t]: round(v, 2) for t, v in reaches.items()} }; pose viste: {dict(Counter(poses))}")
        # ritaglia i tratti iniziale e finale in cui la mano e' ferma
        i0 = next((i for i, p in enumerate(pts) if math.hypot(p[0] - pts[0][0], p[1] - pts[0][1]) > MOTION_START), None)
        i1 = next((i for i in range(len(pts) - 1, -1, -1)
                   if math.hypot(pts[i][0] - pts[-1][0], pts[i][1] - pts[-1][1]) > MOTION_START), None)
        if i0 is None or i1 is None or i1 - i0 < 2 or reach < MOTION_MIN_REACH:
            self.motion_message = f"Non ho visto un movimento ({info}). Muovi la mano piu' ampia, dopo «ORA»."
            return
        i0, i1 = max(0, i0 - 1), min(len(pts) - 1, i1 + 1)
        segment = pts[i0:i1 + 1]
        length = path_length(segment)
        if length < MOTION_MIN_LENGTH:
            self.motion_message = f"Movimento troppo piccolo ({info}). Fai un gesto piu' ampio."
            return
        top = Counter(p for p in poses if p).most_common(1)
        if not top or top[0][1] < 0.6 * len(poses):
            self.motion_message = "Posa non stabile: tieni la stessa posa per tutto il movimento (mano aperta, tre dita, mignolo...)."
            return
        pose = top[0][0]
        if HAND_MODE == "one" and pose not in ONE_HAND_MOTION_POSES:
            self.motion_message = (f"In modalita' una mano «{POSE_NAMES[pose]}» e' usata per il cursore: usa tre dita, "
                                   "indice+mignolo o solo mignolo (oppure passa a due mani).")
            return
        number = max([int(m["id"][4:]) for m in MOTIONS] + [0]) + 1
        entry = {"id": f"move{number}", "name": f"Movimento {number}", "pose": pose,
                 "dur": round(max(frames[i1][0] - frames[i0][0], 0.2), 2), "length": round(length, 2), "track": track,
                 "points": [[round(x, 4), round(y, 4)] for x, y in normalize_motion(segment)], "action": "none"}
        register_motion(entry)
        save_settings()
        self.motions_changed = True
        self.motion_message = (f"Registrato «{entry['name']}» (posa: {POSE_NAMES[pose]}, {len(segment)} immagini): "
                               "scegli qui sotto l'azione da collegare.")

    def _motion_moving(self, pose, now):
        motion = next((m for m in MOTIONS if m["pose"] == pose), None)
        if motion is None:
            return False
        track = motion.get("track", "mcp")
        recent = [(p[1][track][0] / p[2], p[1][track][1] / p[2]) for p in self.motion_buf if now - p[0] <= 0.5]
        return len(recent) > 1 and path_length(recent) > 0.5

    def _motion_step(self, pose, lm, now):
        """Confronta il movimento recente della mano con quelli registrati per la posa in corso."""
        candidates = [m for m in MOTIONS if m["pose"] == pose] if pose else []
        if not candidates:
            self.motion_buf.clear()
            self.motion_pose = None
            return self.motion_label if now < self.motion_label_until else None
        if pose != self.motion_pose:
            self.motion_buf.clear()
            self.motion_pose = pose
        buf = self.motion_buf
        buf.append((now, hand_points(lm), hand_size(lm)))
        while buf and now - buf[0][0] > 3.5:
            buf.popleft()
        if now - self.motion_fire_t < MOTION_COOLDOWN_SEC:
            return self.motion_label if now < self.motion_label_until else None
        best = None
        for m in candidates:
            for scale in (0.8, 1.0, 1.25):
                span = m["dur"] * scale
                seg = [p for p in buf if p[0] >= now - span]
                if len(seg) < 4 or seg[-1][0] - seg[0][0] < span * 0.7:
                    continue
                size = sorted(p[2] for p in seg)[len(seg) // 2]
                track = m.get("track", "mcp")
                pts = [(p[1][track][0] / size, p[1][track][1] / size) for p in seg]
                if path_length(pts) < 0.6 * m["length"]:
                    continue
                if bbox_diagonal(pts) < 0.6 * bbox_diagonal(m["points"]) * m["length"]:
                    continue   # un tremolio ha molto percorso ma si sposta poco: non e' il movimento registrato
                d = motion_distance(normalize_motion(pts), m["points"])
                if d < MOTION_THRESHOLD and (best is None or d < best[0]):
                    best = (d, m)
        if best is None:
            return self.motion_label if now < self.motion_label_until else None
        m = best[1]
        self.motion_fire_t = now
        buf.clear()
        self.verified.add("motion")
        self._run_action(m["action"])
        self.motion_label = f"{m['name']} > {ACTION_SHORT.get(m['action'], 'Nessuna azione')}"
        self.motion_label_until = now + 1.0
        return self.motion_label

    # -- azioni ---------------------------------------------------------------
    def _left_click(self, now):
        x, y = self.cursor
        near = math.hypot(x - self.last_click_pos[0], y - self.last_click_pos[1]) < 30
        if now - self.last_click_t < DOUBLE_CLICK_SEC and near:
            self.click_count = 2 if self.click_count == 1 else 1
        else:
            self.click_count = 1
        self.last_click_t = now
        self.last_click_pos = (x, y)
        self.verified.add("click")
        self.mouse.left_click(x, y, self.click_count)

    def _scroll(self, y):
        if self.scroll_y is not None:
            dy = self.scroll_y - y            # mano che sale => positivo
            if abs(dy) > SCROLL_DEADZONE:
                self.scroll_acc += dy * SCROLL_SPEED * (-1 if SCROLL_INVERT else 1)
        self.scroll_y = y
        px = int(self.scroll_acc)
        if px:
            self.scroll_acc -= px
            self.mouse.scroll(px)


def draw_preview(frame, results, label, paused, camera_name=""):
    h, w = frame.shape[:2]
    mp_draw = mp.solutions.drawing_utils
    if results and results.multi_hand_landmarks:
        for hand in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(
                frame, hand, mp.solutions.hands.HAND_CONNECTIONS,
                mp.solutions.drawing_styles.get_default_hand_landmarks_style(),
                mp.solutions.drawing_styles.get_default_hand_connections_style(),
            )
    # area attiva
    cv2.rectangle(
        frame,
        (int(ACTIVE_MARGIN_X * w), int(ACTIVE_MARGIN_Y * h)),
        (int((1 - ACTIVE_MARGIN_X) * w), int((1 - ACTIVE_MARGIN_Y) * h)),
        (0, 160, 255) if not paused else (90, 90, 90), 1,
    )
    color = (0, 0, 255) if paused else (0, 255, 0)
    cv2.rectangle(frame, (0, 0), (w, 34), (0, 0, 0), -1)
    cv2.putText(frame, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)
    cv2.putText(frame, camera_name.encode("ascii", "replace").decode(), (10, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)
    cv2.putText(frame, f"{QUIT_KEY.upper()} = esci", (w - 100, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)
    scale = PREVIEW_WIDTH / w
    return cv2.resize(frame, (PREVIEW_WIDTH, int(h * scale)))


def make_hands(max_hands):
    return mp.solutions.hands.Hands(
        static_image_mode=False,
        max_num_hands=max_hands,
        model_complexity=MODEL_COMPLEXITY,
        min_detection_confidence=DETECTION_CONFIDENCE,
        min_tracking_confidence=TRACKING_CONFIDENCE,
    )


def process_hands(ctrl, results, now):
    """Assegna le mani riconosciute a cursore e gesti-azione secondo HAND_MODE; restituisce il gesto da mostrare."""
    found = results.multi_hand_landmarks or []
    if HAND_MODE == "one" or not found:
        if found:
            return ctrl.update(found[0].landmark, now)
        ctrl.free_hand_lost()
        return ctrl.no_hand(now)

    pointer_side = "Right" if HAND_MODE == "two_right" else "Left"
    pointer = other = None
    for lm, handedness in zip(found, results.multi_handedness):
        side = handedness.classification[0].label   # con l'immagine specchiata e' la mano reale
        if not MIRROR:
            side = "Left" if side == "Right" else "Right"
        if side == pointer_side and pointer is None:
            pointer = lm.landmark
        elif side != pointer_side and other is None:
            other = lm.landmark
    label = ctrl.update(pointer, now, actions=False) if pointer else ctrl.no_hand(now)
    action_label = ctrl.update_actions(other, now) if other else None
    if not other:
        ctrl.free_hand_lost()
    return action_label or label


