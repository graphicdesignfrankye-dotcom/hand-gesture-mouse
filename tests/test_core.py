"""Prove della logica comune senza webcam ne' mouse reale (gira su qualsiasi sistema).

Uso:  python tests/test_core.py
"""
import os
import sys
import tempfile
import time
from types import SimpleNamespace as P

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gesture_core as core  # noqa: E402

core.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "settings.json")
core.LOG_PATH = os.path.join(tempfile.mkdtemp(), "log.txt")


class RecMouse(core.MouseBase):
    """Mouse finto: registra cio' che verrebbe inviato al sistema."""

    def __init__(self):
        self.sent = []
        super().__init__()

    def position(self): return (10.0, 10.0)
    def _list_displays(self): return [(0, 0, 1920, 1080), (1920, 0, 1280, 1024), (-1000, 0, 1000, 800)]
    def _warp(self, x, y): self.sent.append(("warp", x, y))
    def _emit_move(self, x, y, dragging): self.sent.append(("move", round(x), round(y), dragging))
    def _emit_button(self, button, down, x, y, clicks): self.sent.append(("btn", button, down, clicks))
    def _emit_scroll(self, pixels): self.sent.append(("scroll", pixels))
    def _emit_key(self, code, flags): self.sent.append(("key", code, flags))
    def _emit_action(self, action): self.sent.append(("action", action))
    def supports(self, action): return action in ("fullscreen", "play_pause", "mission_control")


def hand(index=True, middle=False, ring=False, pinky=False, pinch_i=False, pinch_m=False, x=.5, y=.5):
    lm = [P(x=x, y=y) for _ in range(21)]
    lm[0] = P(x=x, y=y + .3)
    lm[9] = P(x=x, y=y + .1)

    def finger(pip, tip, up, dx):
        lm[pip] = P(x=x + dx, y=y + .1 if up else y + .2)
        lm[tip] = P(x=x + dx, y=y if up else y + .25)
    finger(6, 8, index, -.03); finger(10, 12, middle, 0); finger(14, 16, ring, .03); finger(18, 20, pinky, .06)
    lm[4] = P(x=x - .2, y=y + .1)
    if pinch_i: lm[4] = P(x=lm[8].x + .01, y=lm[8].y)
    if pinch_m: lm[4] = P(x=lm[12].x + .01, y=lm[12].y)
    return lm


def res(*pairs):
    return P(multi_hand_landmarks=[P(landmark=l) for l, _ in pairs],
             multi_handedness=[P(classification=[P(label=s)]) for _, s in pairs])


def drive(ctrl, frames, t=0.0, dt=0.05):
    labels = []
    for kw in frames:
        t += dt
        labels.append(ctrl.update(hand(**kw), t))
    return labels, t


failures = []


def check(name, cond, detail=""):
    print(("OK   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# --- gesti di base (mouse reale, in modalita' test: registra gli eventi) ----------------------
m = RecMouse()
c = core.GestureController(m)
labels, t = drive(c, [dict(index=True)] * 3)
check("muovi il cursore", labels[-1] == "Muovi" and any(s[0] == "move" for s in m.sent))
m.sent.clear()
labels, t = drive(c, [dict(pinch_i=True, middle=True, ring=True, pinky=True)] * 2 + [dict(index=True)] * 2, t)
check("click sinistro", ("btn", "left", True, 1) in m.sent and ("btn", "left", False, 1) in m.sent, m.sent)
m.sent.clear(); m.events.clear()
labels, t = drive(c, [dict(index=True)] + [dict(pinch_i=True)] * 12 + [dict(index=True)] * 2, t + 2)
check("trascinamento", ("btn", "left", True, 1) in m.sent and list(m.events)[-2:] == ["Trascinamento: inizio", "Trascinamento: fine"], list(m.events))
m.sent.clear(); m.events.clear()
labels, t = drive(c, [dict(middle=True, pinch_m=True)] * 3 + [dict(index=True)] * 2, t + 2)
check("click destro", ("btn", "right", True, 1) in m.sent)
m.sent.clear()
labels, t = drive(c, [dict(middle=True, y=.5), dict(middle=True, y=.45), dict(middle=True, y=.40)], t + 2)
check("scroll", any(s[0] == "scroll" and s[1] > 0 for s in m.sent), m.sent)
labels, t = drive(c, [dict(index=False)] * 16, t + 2)
check("pugno = pausa", c.paused and labels[-1].startswith("Pugno"), labels[-1])
c.set_paused(False)

# --- gesti a posa, una mano -----------------------------------------------------------------
core.HAND_MODE = "one"
m = RecMouse(); c = core.GestureController(m)
labels, t = drive(c, [dict(index=True, middle=True, ring=True)] * 20)
check("tre dita = monitor successivo", "Cursore sul monitor 2 di 3" in m.events and "Tre dita" in labels[-1], list(m.events))
m.events.clear()
labels, t = drive(c, [dict(index=True)] * 3 + [dict(index=True, pinky=True)] * 20, t + 2)
check("indice+mignolo = schermo intero", ("action", "fullscreen") in m.sent, m.sent)

# --- due mani: la mano aperta e' riposo, niente scatti ----------------------------------------
core.HAND_MODE = "two_right"
m = RecMouse(); c = core.GestureController(m)
pointer = hand(index=True, x=.4)
open_hand = hand(index=True, middle=True, ring=True, pinky=True)
t = 0
for _ in range(80):
    t += .05
    core.process_hands(c, res((pointer, "Right"), (open_hand, "Left")), t)
check("mano libera aperta a riposo non fa nulla", not [s for s in m.sent if s[0] in ("action", "key", "warp")], m.sent)
three = hand(index=True, middle=True, ring=True)
flicker = [three] * 10 + [hand(index=True, middle=True)] * 2
t = 0
m.sent.clear(); m.events.clear(); c.pose = None; c.last_action_t = -1e9
for lm in flicker * 4:
    t += .05
    core.process_hands(c, res((pointer, "Right"), (lm, "Left")), t)
n = len([e for e in m.events if "monitor" in e])
check("posa oscillante = una sola azione", n == 1, f"{n} azioni")
check("senza mano libera non scatta nulla", core.process_hands(c, res((pointer, "Right")), t + 1) in ("Muovi", "Inattivo"))
core.GESTURE_ACTIONS_TWO["two"] = "play_pause"
m.sent.clear(); c.pose = None; c.last_action_t = -1e9
for _ in range(20):
    t += .05
    core.process_hands(c, res((pointer, "Right"), (hand(index=True, middle=True), "Left")), t)
check("azione riassegnata (due dita = play/pausa)", ("action", "play_pause") in m.sent, m.sent)
check("mappe una/due mani separate", core.GESTURE_ACTIONS["three"] == "next_display")
core.HAND_MODE = "one"

# --- scorciatoie registrate e sequenze ----------------------------------------------------------
m = RecMouse(); c = core.GestureController(m)
core.register_custom({"id": "custom1", "label": "X", "code": 21, "flags": 5})
core.GESTURE_ACTIONS["rock"] = "custom1"
drive(c, [dict(index=True)] * 2 + [dict(index=True, pinky=True)] * 20)
check("scorciatoia registrata inviata", ("key", 21, 5) in m.sent, m.sent)
steps = [{"k": "key", "code": 12, "flags": 1, "d": 0.1}, {"k": "click", "x": 40.0, "y": 50.0, "b": "left", "d": 0.1},
         {"k": "click", "x": 60.0, "y": 70.0, "b": "right", "d": 0.1}]
core.register_macro({"id": "macro1", "name": "Sequenza 1", "steps": steps})
m.sent.clear()
c._run_action("macro1")
time.sleep(1.0)
check("sequenza eseguita", ("key", 12, 1) in m.sent and ("btn", "right", True, 1) in m.sent and not m.replaying, m.sent)
check("cursore dopo la sequenza", c.cursor == (60.0, 70.0), c.cursor)
core.GESTURE_ACTIONS["rock"] = "macro1"; m.sent.clear(); m.dry_run = True
core.GestureController._run_action(c, "macro1")
check("modalita' test non esegue la sequenza", not m.sent)


# --- volume con la mano aperta ------------------------------------------------------------------
core.HAND_MODE = "one"
m = RecMouse(); c = core.GestureController(m)
open_kw = dict(index=True, middle=True, ring=True, pinky=True)
labels, t = drive(c, [dict(open_kw, y=.5)] * 8)          # 0,4 s: ancora non risponde
check("volume: prima di agganciarsi non fa nulla", not any(x[0] == "action" for x in m.sent) and labels[-1].startswith("Volume"))
labels, t = drive(c, [dict(open_kw, y=.5)] * 8, t)       # mano ferma: nessuno scatto
check("volume: mano ferma = nessuno scatto", not any(x[0] == "action" for x in m.sent), m.sent)
labels, t = drive(c, [dict(open_kw, y=.5 - .02 * i) for i in range(1, 9)], t)   # alzo di 0,16
ups = [x for x in m.sent if x == ("action", "volume_up")]
check("volume: mano alzata = volume su", len(ups) == 3, m.sent)
m.sent.clear()
labels, t = drive(c, [dict(open_kw, y=.34 + .02 * i) for i in range(1, 7)], t)  # abbasso di 0,12
downs = [x for x in m.sent if x == ("action", "volume_down")]
check("volume: mano abbassata = volume giu", len(downs) == 2, m.sent)
check("volume: gesto segnato nella lista di test", "volume" in c.verified)
core.VOLUME_GESTURE = False
m.sent.clear(); c2 = core.GestureController(m)
drive(c2, [dict(open_kw, y=.5)] * 20 + [dict(open_kw, y=.5 - .02 * i) for i in range(1, 9)])
check("volume spento nelle impostazioni", not any(x[0] == "action" for x in m.sent))
core.VOLUME_GESTURE = True

# --- movimenti registrati --------------------------------------------------------------------
def swipe(x0, x1, y0=.5, y1=None, n=30, **kw):
    y1 = y0 if y1 is None else y1
    return [dict(kw, x=x0 + (x1 - x0) * i / (n - 1), y=y0 + (y1 - y0) * i / (n - 1)) for i in range(n)]

pinky = dict(index=False, pinky=True)
core.MOTIONS.clear(); core.HAND_MODE = "one"
m = RecMouse(); c = core.GestureController(m)
c.start_motion_recording()
frames = [dict(pinky, x=.3)] * 75 + swipe(.3, .7, **pinky) + [dict(pinky, x=.7)] * 40   # 3 s di conto + 2,5 s
labels, t = drive(c, frames, dt=0.04)
check("registrazione movimento", len(core.MOTIONS) == 1 and core.MOTIONS[0]["pose"] == "pinky", c.motion_message)
core.MOTIONS[0]["action"] = "play_pause"
def try_motion(frames):
    mm = RecMouse(); cc = core.GestureController(mm)
    drive(cc, [dict(pinky, x=frames[0]["x"], y=frames[0].get("y", .5))] * 10, dt=0.04)
    drive(cc, frames, t=0.4, dt=0.04)
    return [x for x in mm.sent if x == ("action", "play_pause")]
check("riconosce lo stesso movimento (altra posizione e velocita')", len(try_motion(swipe(.15, .55, y0=.6, n=22, **pinky))) == 1)
check("non scatta con il movimento contrario", not try_motion(swipe(.7, .3, **pinky)))
check("non scatta con un movimento verticale", not try_motion(swipe(.5, .5, y0=.3, y1=.7, **pinky)))
check("non scatta a mano ferma", not try_motion([dict(pinky, x=.5)] * 60))
check("non scatta con un tremolio", not try_motion(swipe(.5, .52, n=40, **pinky)))
c3 = core.GestureController(RecMouse()); c3.start_motion_recording()
drive(c3, [dict(pinky, x=.3)] * 75 + [dict(pinky, x=.3)] * 70, dt=0.04)
check("registrazione senza movimento: rifiutata", len(core.MOTIONS) == 1 and "movimento" in c3.motion_message.lower(), c3.motion_message)
c4 = core.GestureController(RecMouse()); c4.start_motion_recording()
drive(c4, [dict(index=True, x=.3)] * 75 + swipe(.3, .7, index=True) + [dict(index=True, x=.7)] * 40, dt=0.04)
check("posa del cursore rifiutata in modalita' una mano", len(core.MOTIONS) == 1 and "cursore" in c4.motion_message, c4.motion_message)


# --- movimento breve sinistra-destra, pochi fotogrammi al secondo (come con una webcam lenta) ------------
def wave(amp, n_each=6, y=.5, **kw):
    xs = [.5 - amp * (i + 1) / n_each for i in range(n_each)] + [.5 - amp + 2 * amp * (i + 1) / n_each for i in range(n_each)]
    return [dict(kw, x=x, y=y) for x in xs]

for amp, name in ((.12, "ampio"), (.05, "piccolo")):
    core.MOTIONS.clear(); core.HAND_MODE = "one"
    cw = core.GestureController(RecMouse()); cw.start_motion_recording()
    drive(cw, [dict(pinky, x=.5)] * 46 + [dict(pinky, x=.5)] * 8 + wave(amp, **pinky) + [dict(pinky, x=.5)] * 24, dt=1 / 15)
    check(f"registra una mossa sinistra-destra {name} a 15 immagini/s", len(core.MOTIONS) == 1, cw.motion_message)
    if core.MOTIONS:
        core.MOTIONS[0]["action"] = "play_pause"
        mm = RecMouse(); cc = core.GestureController(mm)
        drive(cc, [dict(pinky, x=.5)] * 15, dt=1 / 15)
        drive(cc, wave(amp, **pinky) + [dict(pinky, x=.5)] * 3, t=1.0, dt=1 / 15)
        check(f"la riconosce quando la rifai ({name})", ("action", "play_pause") in mm.sent, mm.sent)
        mm = RecMouse(); cc = core.GestureController(mm)
        drive(cc, [dict(pinky, x=.5 + .004 * ((-1) ** i)) for i in range(60)], dt=1 / 15)
        check(f"non scatta con un tremolio ({name})", not mm.sent)
core.MOTIONS.clear()
c6 = core.GestureController(RecMouse()); c6.start_motion_recording()
drive(c6, [dict(index=True, middle=True, ring=True, pinky=True, x=.5)] * 46 + [dict(index=True, middle=True, ring=True, pinky=True, x=.5 - .1 * (i % 2)) for i in range(40)], dt=1 / 15)
check("mano aperta con movimento minimo: spiega i numeri", "spostamento massimo" in c6.motion_message or len(core.MOTIONS) >= 1, c6.motion_message)
c7 = core.GestureController(RecMouse()); c7.start_motion_recording()
drive(c7, [dict(pinky, x=.5)] * 100, dt=1 / 15)
check("nessun movimento: il messaggio dice quanto ho misurato", "spostamento massimo" in c7.motion_message, c7.motion_message)


# --- saluto sinistra-destra con la mano aperta (posa del volume) ----------------------------------------
opn = dict(index=True, middle=True, ring=True, pinky=True)
core.MOTIONS.clear(); core.HAND_MODE = "one"
mv = RecMouse(); cv_ = core.GestureController(mv); cv_.start_motion_recording()
drive(cv_, [dict(opn, x=.5)] * 100 + wave(.12, **opn) + [dict(opn, x=.5)] * 70, dt=1 / 30)
check("registra un saluto con la mano aperta", len(core.MOTIONS) == 1 and core.MOTIONS[0]["pose"] == "open", cv_.motion_message)
check("il saluto non cambia il volume (solo orizzontale)", not any(x[0] == "action" for x in mv.sent), mv.sent)
if core.MOTIONS:
    core.MOTIONS[0]["action"] = "answer_call"
    core.CALL_POINTS["answer_call"] = [50.0, 60.0]
    mm = RecMouse(); cc = core.GestureController(mm)
    drive(cc, [dict(opn, x=.5)] * 40, dt=1 / 30)       # mano aperta ferma, il volume si aggancia
    drive(cc, wave(.12, **opn) + [dict(opn, x=.5)] * 6, t=1.4, dt=1 / 30)
    time.sleep(0.3)
    check("il saluto fa partire l'azione e non tocca il volume",
          ("btn", "left", True, 1) in mm.sent and not any(x == ("action", "volume_up") or x == ("action", "volume_down") for x in mm.sent), mm.sent)
    mm = RecMouse(); cc = core.GestureController(mm)
    drive(cc, [dict(opn, x=.5, y=.5)] * 40 + [dict(opn, x=.5, y=.5 - .02 * i) for i in range(1, 9)], dt=1 / 30)
    check("il volume funziona ancora con un movimento registrato a mano aperta", ("action", "volume_up") in mm.sent, mm.sent)
core.MOTIONS.clear(); core.CALL_POINTS.pop("answer_call", None)


# --- segnali e avanzamento durante la registrazione ----------------------------------------------------
core.MOTIONS.clear(); core.HAND_MODE = "one"
cues = []; cq = core.GestureController(RecMouse()); cq.cue = cues.append
cq.start_motion_recording()
msgs = []
t_ = 0.0
for kw in [dict(pinky, x=.5)] * 100 + wave(.12, **pinky) + [dict(pinky, x=.5)] * 70:
    t_ += 1 / 30
    cq.update(hand(**kw), t_); msgs.append(cq.motion_message)
check("segnali: tic, inizio e fine", cues[:3] == ["tick"] * 3 and "start" in cues and cues[-1] == "ok", cues)
check("avanzamento in diretta nella finestra", any(m.startswith("Preparati") for m in msgs) and any(m.startswith("ORA") for m in msgs))
core.MOTIONS.clear()


# --- saluto "dal polso": il palmo resta fermo e si muovono solo le punte --------------------------------
def pivot(dx, **kw):
    lm = hand(**kw)
    for i in (8, 12, 16, 20):
        lm[i] = P(x=lm[i].x + dx, y=lm[i].y)
    return lm

def pivot_wave(amp=.12, n_each=6, **kw):
    dxs = [-amp * (i + 1) / n_each for i in range(n_each)] + [-amp + 2 * amp * (i + 1) / n_each for i in range(n_each)]
    return [pivot(dx, **kw) for dx in dxs]

def feed(ctrl, lms, t=0.0, dt=1 / 30):
    for lm in lms:
        t += dt
        ctrl.update(lm, t)
    return t

core.MOTIONS.clear(); core.HAND_MODE = "one"; core.CALL_POINTS["answer_call"] = [10.0, 20.0]
cp = core.GestureController(RecMouse()); cp.start_motion_recording()
feed(cp, [pivot(0, **opn)] * 100 + pivot_wave(**opn) + [pivot(0, **opn)] * 70)
check("saluto dal polso: registrato seguendo le punte", len(core.MOTIONS) == 1 and core.MOTIONS[0].get("track") == "tip",
      (cp.motion_message, core.MOTIONS and core.MOTIONS[0].get("track")))
if core.MOTIONS:
    core.MOTIONS[0]["action"] = "answer_call"
    mp_ = RecMouse(); cc = core.GestureController(mp_)
    t2 = feed(cc, [pivot(0, **opn)] * 40)
    feed(cc, pivot_wave(**opn) + [pivot(0, **opn)] * 6, t2)
    time.sleep(0.3)
    check("saluto dal polso riconosciuto", ("btn", "left", True, 1) in mp_.sent, mp_.sent)
    mp_ = RecMouse(); cc = core.GestureController(mp_)
    feed(cc, [pivot(0, **opn)] * 120)
    check("palmo fermo: nessuna azione", not mp_.sent)
core.MOTIONS.clear(); core.CALL_POINTS.pop("answer_call", None)


# --- webcam 16:9: un movimento orizzontale non va sottostimato ------------------------------------------
core.MOTIONS.clear(); core.HAND_MODE = "one"
for aspect, expected in ((1.0, False), (16 / 9, True)):
    core.FRAME_ASPECT = aspect
    ca = core.GestureController(RecMouse()); ca.start_motion_recording()
    drive(ca, [dict(pinky, x=.5)] * 100 + wave(.02, **pinky) + [dict(pinky, x=.5)] * 70, dt=1 / 30)
    check(f"mossa orizzontale piccola con immagine {aspect:.2f}:1 -> registrata = {expected}", bool(core.MOTIONS) == expected, ca.motion_message)
    core.MOTIONS.clear()
core.FRAME_ASPECT = 1.0


# --- swipe con la mano aperta: sinistra = un'azione, destra = un'altra ---------------------------------
def slide(x0, x1, n, y=.5, **kw):
    return [dict(kw, x=x0 + (x1 - x0) * (i + 1) / n, y=y) for i in range(n)]

core.SWIPE_ACTIONS.update({"left": "play_pause", "right": "mission_control"})
for mode in ("one", "two_right"):
    core.HAND_MODE = mode
    ms = RecMouse(); cs = core.GestureController(ms)
    t3_ = 0.0
    for kw in [dict(opn, x=.6)] * 15:                       # mano aperta ferma (0,5 s)
        t3_ += 1 / 30; cs.update(hand(**kw), t3_)
    for kw in slide(.6, .4, 8, **opn):                       # verso sinistra in ~0,27 s
        t3_ += 1 / 30; lab = cs.update(hand(**kw), t3_)
    check(f"swipe a sinistra ({mode}): azione assegnata", ("action", "play_pause") in ms.sent and "sinistra" in lab, (ms.sent, lab))
    n_before = len(ms.sent)
    for kw in slide(.4, .6, 8, **opn):                       # il ritorno della mano non deve contare
        t3_ += 1 / 30; cs.update(hand(**kw), t3_)
    check(f"il ritorno non e' uno swipe opposto ({mode})", len(ms.sent) == n_before, ms.sent)
    for kw in [dict(opn, x=.6)] * 40:                        # pausa oltre il cooldown (la mano e' tornata a .6)
        t3_ += 1 / 30; cs.update(hand(**kw), t3_)
    for kw in slide(.6, .8, 8, **opn):                       # verso destra (da dove e' arrivata la mano)
        t3_ += 1 / 30; lab = cs.update(hand(**kw), t3_)
    check(f"swipe a destra ({mode}): altra azione", ("action", "mission_control") in ms.sent and "destra" in lab, (ms.sent, lab))
    check(f"swipe nella lista di test ({mode})", {"swipe_left", "swipe_right"} <= cs.verified)
    # spostamento lento, verticale: niente
    for name, frames in (("lento", slide(.4, .65, 90, **opn)), ("verticale", [dict(opn, x=.4, y=.3 + .4 * i / 7) for i in range(8)])):
        ms2 = RecMouse(); c2_ = core.GestureController(ms2); tt = 0.0
        for kw in [dict(opn, x=.4, y=.3)] * 15 + frames:
            tt += 1 / 30; c2_.update(hand(**kw), tt)
        check(f"nessuno swipe con spostamento {name} ({mode})", not [x for x in ms2.sent if x[1] in ("play_pause", "mission_control")], ms2.sent)
# il cursore non si muove con la mano aperta
core.HAND_MODE = "two_right"; ms = RecMouse(); cs = core.GestureController(ms)
tt = 0.0
for kw in [dict(opn, x=.6)] * 10 + slide(.6, .4, 8, **opn):
    tt += 1 / 30; cs.update(hand(**kw), tt)
check("con la mano aperta il cursore resta fermo", not any(x[0] == "move" for x in ms.sent), ms.sent)
core.SWIPE_ACTIONS.update(core.DEFAULT_SWIPE_ACTIONS); core.HAND_MODE = "one"

# --- click registrato per rispondere alle chiamate -------------------------------------------------
core.CALL_POINTS["answer_call"] = [123.0, 456.0]
m = RecMouse(); c = core.GestureController(m)
core.GESTURE_ACTIONS["rock"] = "answer_call"
drive(c, [dict(index=True)] * 2 + [dict(index=True, pinky=True)] * 20)
time.sleep(0.5)
check("rispondi chiamata = click nel punto registrato", ("move", 123, 456, False) in m.sent and ("btn", "left", True, 1) in m.sent, m.sent)
check("cursore dopo il click", c.cursor == (123.0, 456.0), c.cursor)
core.CALL_POINTS.pop("decline_call", None)
m2 = RecMouse(); c5 = core.GestureController(m2); c5._run_action("decline_call")
check("rifiuta senza click registrato: avviso", "Prima registra il click (scheda Generale)" in m2.events and not m2.sent)
core.GESTURE_ACTIONS["rock"] = "none"

core.register_motion({"id": "move1", "name": "Movimento 1", "pose": "pinky", "dur": 1.0, "length": 1.5,
                      "points": [[0.01 * i - 0.12, 0.0] for i in range(24)], "action": "play_pause"})

# --- mignolo: risponde alla chiamata e, rifatto, la chiude ---------------------------------------------------
saved_calls = dict(core.CALL_POINTS)
for mode in ("one", "two_right"):
    core.HAND_MODE = mode
    core.CALL_POINTS.update({"answer_call": [100.0, 50.0], "end_call": [300.0, 400.0]})
    mc = RecMouse(); cm = core.GestureController(mc)
    check(f"mignolo = rispondi/chiudi di default ({mode})",
          (core.GESTURE_ACTIONS if mode == "one" else core.GESTURE_ACTIONS_TWO)["pinky"] == "call_toggle")
    def hold_pinky(t0):
        tt = t0
        pointer_ = hand(index=True, x=.4)
        for i in range(60):
            tt += 1 / 30
            if mode == "one":
                cm.update(hand(index=False, pinky=True), tt)
            else:
                core.process_hands(cm, res((pointer_, "Right"), (hand(index=False, pinky=True), "Left")), tt)
        return tt
    def release(t0):
        tt = t0
        for i in range(14):
            tt += 1 / 30
            if mode == "one":
                cm.update(hand(index=True), tt)
            else:
                core.process_hands(cm, res((hand(index=True, x=.4), "Right"), (hand(index=True), "Left")), tt)
        return tt
    t0 = hold_pinky(0.0); time.sleep(0.4)
    check(f"primo mignolo: click su «Rispondi» ({mode})", ("move", 100, 50, False) in mc.sent and cm.call_active_since is not None, mc.sent)
    mc.sent.clear()
    t0 = release(t0); cm.last_action_t = -1e9
    t0 = hold_pinky(t0 + 2.0); time.sleep(0.4)
    check(f"secondo mignolo: click su «Chiudi» ({mode})", ("move", 300, 400, False) in mc.sent and cm.call_active_since is None, mc.sent)
    mc.sent.clear()
    t0 = release(t0); cm.last_action_t = -1e9
    t0 = hold_pinky(t0 + 2.0); time.sleep(0.4)
    check(f"terzo mignolo: risponde di nuovo ({mode})", ("move", 100, 50, False) in mc.sent, mc.sent)
core.CALL_POINTS.pop("end_call"); mm_ = RecMouse(); cm2 = core.GestureController(mm_)
cm2.call_active_since = time.monotonic(); cm2._run_action("call_toggle")
check("senza il click «Chiudi» registrato: avviso e resta attiva", any("Chiudi" in e for e in mm_.events) and cm2.call_active_since is not None)
core.CALL_POINTS.clear(); core.CALL_POINTS.update(saved_calls); core.HAND_MODE = "one"

# --- impostazioni salvate -----------------------------------------------------------------------
core.GESTURE_ACTIONS["rock"] = "macro1"
core.SMOOTHING = 0.55; core.HAND_MODE = "two_left"; core.CAMERA_ID = "ID-XYZ"
core.save_settings()
core.SMOOTHING = 0.9; core.HAND_MODE = "one"; core.CAMERA_ID = ""
core.remove_macros(); core.remove_customs(); core.GESTURE_ACTIONS["rock"] = "none"; core.MOTIONS.clear(); core.CALL_POINTS.clear()
core.load_settings()
check("impostazioni ricaricate", core.SMOOTHING == 0.55 and core.HAND_MODE == "two_left" and core.CAMERA_ID == "ID-XYZ")
check("sequenze e scorciatoie ricaricate", [x["id"] for x in core.MACROS] == ["macro1"] and core.CUSTOM_ACTIONS[0]["id"] == "custom1")
check("movimenti e click chiamata ricaricati", core.MOTIONS and core.MOTIONS[0]["action"] == "play_pause" and core.CALL_POINTS.get("answer_call") == [123.0, 456.0])
check("assegnazioni ricaricate", core.GESTURE_ACTIONS["rock"] == "macro1")
core.set_action_text({"fullscreen": ("Schermo intero", "Schermo intero (F11)")})
check("nomi azioni per sistema", dict((k, t_) for k, _, t_ in core.ACTIONS)["fullscreen"] == "Schermo intero (F11)")

print("\nTUTTO OK" if not failures else f"\nFALLITI: {failures}")
sys.exit(1 if failures else 0)
