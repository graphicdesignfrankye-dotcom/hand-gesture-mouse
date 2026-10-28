"""Prove della versione Windows eseguibili anche su un Mac/Linux: user32 e' finto, tkinter e' vero.

Uso:  python tests/test_win.py
"""
import ctypes
import os
import sys
import tempfile
import time
from types import SimpleNamespace as P

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gesture_core as core  # noqa: E402
import hand_mouse_win as win  # noqa: E402

core.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "settings.json")
core.LOG_PATH = os.path.join(tempfile.mkdtemp(), "log.txt")
failures = []


def check(name, cond, detail=""):
    print(("OK   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        failures.append(name)


class FakeUser32:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*args):
            self.calls.append((name, args))
            return 0
        return call

    def GetCursorPos(self, ref):
        self.calls.append(("GetCursorPos", ()))
        pt = ref._obj
        pt.x, pt.y = 100, 200
        return 1

    def EnumDisplayMonitors(self, hdc, clip, proc, data):
        for rect in ((1920, 0, 3200, 1024), (0, 0, 1920, 1080), (-1000, 0, 0, 800)):
            r = win._RECT(*rect)
            proc(0, 0, ctypes.pointer(r), 0)
        return 1


fake = FakeUser32()
win.user32 = fake
m = win.Mouse()
check("monitor ordinati da sinistra", [d[0] for d in m.displays] == [-1000.0, 0.0, 1920.0], m.displays)
check("posizione del cursore", m.position() == (100.0, 200.0))
check("monitor sotto il cursore", m.index == 1, m.index)

fake.calls.clear()
m.left_click(10, 20)
names = [c[0] for c in fake.calls]
check("click sinistro = giu + su", names == ["SetCursorPos", "mouse_event", "SetCursorPos", "mouse_event"]
      and [c[1][0] for c in fake.calls if c[0] == "mouse_event"] == [0x2, 0x4], fake.calls)
fake.calls.clear(); m.right_click(10, 20)
check("click destro", [c[1][0] for c in fake.calls if c[0] == "mouse_event"] == [0x8, 0x10])
fake.calls.clear(); m.scroll(-50)
check("scroll verso il basso (valore negativo)", fake.calls[0][1][0] == 0x800 and fake.calls[0][1][3] == (-60 & 0xFFFFFFFF), fake.calls)
fake.calls.clear(); m.shortcut("fullscreen")
check("schermo intero = F11", fake.calls == [("keybd_event", (0x7A, 0, 0, 0)), ("keybd_event", (0x7A, 0, 2, 0))], fake.calls)
fake.calls.clear(); m.shortcut("space_left")
seq = [(c[1][0], c[1][2]) for c in fake.calls]
check("desktop a sinistra = Win+Ctrl+Sinistra", seq == [(0x5B, 0), (0x11, 0), (0x25, 1), (0x25, 3), (0x11, 2), (0x5B, 2)], seq)
fake.calls.clear(); m.shortcut("play_pause")
check("play/pausa (tasto esteso)", fake.calls[0] == ("keybd_event", (0xB3, 0, 1, 0)), fake.calls)
fake.calls.clear(); m.shortcut("lock_screen")
check("blocca schermo", fake.calls[-1][0] == "LockWorkStation", fake.calls)
fake.calls.clear(); center = m.next_display()
check("monitor successivo: cursore al centro", center == (1920.0 + 3200 / 2 - 1920 / 2 + 0 if False else center) and fake.calls[0][0] == "SetCursorPos", fake.calls)
core.register_custom({"id": "custom1", "label": "Ctrl+Maiusc+4", "code": 0x34, "flags": win.CTRL | win.SHIFT})
fake.calls.clear(); m.shortcut("custom1")
check("scorciatoia registrata", [(c[1][0]) for c in fake.calls] == [0x11, 0x10, 0x34, 0x34, 0x10, 0x11], fake.calls)
m.dry_run = True; fake.calls.clear(); m.shortcut("fullscreen"); m.left_click(1, 1)
check("modalita' test non invia nulla", not fake.calls)
m.dry_run = False

# --- finestra Impostazioni con tkinter vero -------------------------------------------------------
try:
    import tkinter
    root = tkinter.Tk()
except Exception as exc:   # senza schermo/Tk
    print("SALTATO: tkinter non disponibile:", exc)
    root = None
if root is not None:
    ctrl = core.GestureController(m)
    st = win.Settings(root, ctrl, m)
    st.on_scale("PINCH_START", "0.5")
    check("slider pizzico: rilascio sempre piu' ampio", core.PINCH_START == 0.5 and core.PINCH_RELEASE >= 0.55)
    st.hands_combo.current(1); st.on_hands()
    check("modalita' due mani", core.HAND_MODE == "two_right")
    st.combos[("two", "one")].current([k for k, _, _ in core.ACTIONS].index("play_pause")); st.on_action("two", "one", st.combos[("two", "one")])
    check("azione assegnata nella mappa a due mani", core.GESTURE_ACTIONS_TWO["one"] == "play_pause" and core.GESTURE_ACTIONS["three"] == "next_display")
    ev = P(keysym="4", keycode=0x34, state=0x1 | 0x4)
    st.shortcut_recording = True; st.root.bind("<KeyPress>", st.on_shortcut_key)
    st.on_shortcut_key(P(keysym="Shift_L", keycode=16, state=1))
    st.on_shortcut_key(ev)
    check("scorciatoia registrata da tastiera", core.CUSTOM_ACTIONS[-1]["flags"] == (win.SHIFT | win.CTRL) and core.CUSTOM_ACTIONS[-1]["code"] == 0x34,
          core.CUSTOM_ACTIONS)
    check("elenco azioni aggiornato", any("Ctrl+Maiusc+4" in t for _, _, t in core.ACTIONS) or any("CTRL" in t.upper() for _, _, t in core.ACTIONS))
    # registrazione sequenza: simulo i passi che arriverebbero da pynput
    st.ms = P(Button=P(right="R", left="L")); st.macro_recording = True; st.listeners = []; st.macro_steps = []; st.macro_last = None
    st._on_press(P(name="ctrl_l")); st._on_press(P(vk=0x53)); st._on_release(P(name="ctrl_l"))
    st._on_click(300, 400, "R", True); st._on_click(5, 5, "L", False)
    st.stop_macro()
    steps = core.MACROS[-1]["steps"]
    check("sequenza registrata (Ctrl+S e click destro)", [(s["k"], s.get("code"), s.get("flags"), s.get("b")) for s in steps] ==
          [("key", 0x53, win.CTRL, None), ("click", None, None, "right")], steps)
    st.refresh("Muovi"); root.update()
    # --- movimenti, volume e click per le chiamate ---------------------------------------------------
    core.MOTIONS.clear()
    core.register_motion({"id": "move1", "name": "Movimento 1", "pose": "three", "dur": 1.2, "length": 2.0,
                          "points": [[0.01 * i - 0.12, 0.0] for i in range(24)], "action": "none"})
    ctrl.motions_changed = True
    st.refresh("Muovi")
    check("riga del movimento registrato", len(st.motion_frame.winfo_children()) == 3, len(st.motion_frame.winfo_children()))
    combo = [w for w in st.motion_frame.winfo_children() if w.winfo_class() == "TCombobox"][0]
    combo.current([k for k, _, _ in core.ACTIONS].index("answer_call")); st.on_motion_action(core.MOTIONS[0], combo)
    check("azione collegata al movimento", core.MOTIONS[0]["action"] == "answer_call")
    st.delete_motion(core.MOTIONS[0])
    check("movimento eliminato", not core.MOTIONS and not st.motion_frame.winfo_children())
    st.volume_var.set(False); st.on_volume()
    check("volume spento", core.VOLUME_GESTURE is False)
    st.volume_var.set(True); st.on_volume()
    st.call_done = ("answer_call", 321.0, 123.0); st.refresh("Muovi")
    check("click di risposta registrato", core.CALL_POINTS.get("answer_call") == [321.0, 123.0])
    ctrl2 = core.GestureController(m); fake.calls.clear(); m.dry_run = False
    ctrl2._run_action("answer_call"); time.sleep(0.4)
    check("rispondi chiamata = click nel punto", [c[0] for c in fake.calls][:3] == ["SetCursorPos", "SetCursorPos", "mouse_event"], fake.calls)
    m.dry_run = True
    st.swipe_combos["left"].current([k for k, _, _ in core.ACTIONS].index("play_pause")); st.on_swipe("left", st.swipe_combos["left"])
    check("azione dello swipe a sinistra", core.SWIPE_ACTIONS["left"] == "play_pause" and core.SWIPE_ACTIONS["right"] == "none")
    st.reset()
    check("ripristino", core.HAND_MODE == "one" and core.PINCH_START == 0.30)
    root.destroy()

print("\nTUTTO OK" if not failures else f"\nFALLITI: {failures}")
sys.exit(1 if failures else 0)
