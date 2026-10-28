"""Prova di fumo macOS: crea icona e finestra Impostazioni senza camera (non invia eventi veri)."""
import os, sys, tempfile, time
from types import SimpleNamespace as P
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gesture_core as core
import hand_mouse as hm
core.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")

m = hm.Mouse(); m.dry_run = True
print("monitor:", len(m.displays), "| supports fullscreen:", m.supports("fullscreen"), "| custom:", m.supports("custom1"))
c = core.GestureController(m)
mb = hm.MenuBar.alloc().initWithController_(c)
w = hm.SettingsWindow.alloc().initWithController_mouse_(c, m); mb.settings = w
mb.settings_(None)
tabs = w.window.contentView().subviews()[0]
for i in range(5):
    tabs.selectTabViewItemAtIndex_(i)
    for _ in range(3): mb.pump(); w.refresh("Muovi"); time.sleep(0.03)
class S:
    def __init__(s, tag=0, v=0, i=0): s._t, s._v, s._i = tag, v, i
    def tag(s): return s._t
    def doubleValue(s): return s._v
    def state(s): return 1
    def indexOfSelectedItem(s): return s._i
w.slider_(S(5, 0.5)); print("slider pizzico:", core.PINCH_START, core.PINCH_RELEASE)
w.hands_(S(i=1)); print("mani:", core.HAND_MODE)
w.invert_(S()); print("inverti scroll:", core.SCROLL_INVERT)
w.gesture_(S(100, 0, 3)); print("azione:", core.GESTURE_ACTIONS_TWO["one"])
w.reset_(None); print("reset:", core.PINCH_START, core.HAND_MODE, core.SCROLL_INVERT)
print("webcam:", [n for _, n in hm.list_cameras()])
m.shortcut("fullscreen"); m.shortcut("play_pause"); print("eventi:", list(m.events))
w.window.close(); mb.close(); print("SMOKE OK")
