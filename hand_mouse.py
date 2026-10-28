#!/usr/bin/env python3
"""Hand Gesture Mouse per macOS (parte specifica del sistema; la logica comune e' in gesture_core.py).

Controlla il cursore con la mano tramite la webcam integrata.

    Indice alzato, muovi ......... muove il cursore
    Pizzico rapido (pollice+indice) click sinistro (due pizzichi rapidi = doppio click)
    Pizzico tenuto ............... premi e trascina, apri la mano per rilasciare
    Pizzico pollice + medio ...... click destro
    Indice + medio alzati, muovi . scroll (mano in su = scorre in su)
    Pugno chiuso (tieni ~0,6 s) .. pausa / ripresa del tracking

Dall'icona nella barra dei menu puoi mettere in pausa, riprendere ed uscire.
Premi Q nella finestra di anteprima per uscire.
"""

import os
import subprocess
import sys
import threading
import time
import traceback

import cv2
import dispatch
import numpy as np
import objc

import gesture_core as core  # importa anche MediaPipe (con il trucco matplotlib)
from ApplicationServices import AXIsProcessTrusted, AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
from AVFoundation import (
    AVCaptureDevice,
    AVCaptureDeviceInput,
    AVCaptureSession,
    AVCaptureVideoDataOutput,
    AVMediaTypeVideo,
)
from CoreMedia import CMSampleBufferGetImageBuffer
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApplication,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSDefaultRunLoopMode,
    NSEventMaskAny,
    NSEvent,
    NSEventMaskKeyDown,
    NSEventMaskLeftMouseDown,
    NSEventMaskRightMouseDown,
    NSEventTypeKeyDown,
    NSEventTypeRightMouseDown,
    NSEventTypeSystemDefined,
    NSEventTypeLeftMouseUp,
    NSFont,
    NSMenu,
    NSMenuItem,
    NSPopUpButton,
    NSSlider,
    NSSound,
    NSStatusBar,
    NSTabView,
    NSTabViewItem,
    NSTextField,
    NSVariableStatusItemLength,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSDate, NSMakeRect, NSObject, NSRunLoop
from Quartz import (
    CGDisplayBounds,
    CGEventCreate,
    CGEventCreateKeyboardEvent,
    CGEventCreateMouseEvent,
    CGEventCreateScrollWheelEvent,
    CGEventGetLocation,
    CGEventPost,
    CGEventSetFlags,
    CGEventSetIntegerValueField,
    CGGetActiveDisplayList,
    CGMainDisplayID,
    CGPreflightListenEventAccess,
    CGRequestListenEventAccess,
    CGWarpMouseCursorPosition,
    CVPixelBufferGetBaseAddress,
    CVPixelBufferGetBytesPerRow,
    CVPixelBufferGetHeight,
    CVPixelBufferGetWidth,
    CVPixelBufferLockBaseAddress,
    CVPixelBufferUnlockBaseAddress,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskSecondaryFn,
    kCGEventFlagMaskShift,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseDragged,
    kCGEventLeftMouseUp,
    kCGEventMouseMoved,
    kCGEventRightMouseDown,
    kCGEventRightMouseUp,
    kCGHIDEventTap,
    kCGMouseButtonLeft,
    kCGMouseButtonRight,
    kCGMouseEventClickState,
    kCGScrollEventUnitPixel,
    kCVPixelBufferPixelFormatTypeKey,
    kCVPixelFormatType_32BGRA,
)


# =============================================================================
# Parti specifiche di macOS
# =============================================================================
SETTINGS_PATH = os.path.expanduser("~/Library/Application Support/Hand Gesture Mouse/settings.json")
LOG_PATH = os.path.expanduser("~/Library/Logs/Hand Gesture Mouse.log")
core.SETTINGS_PATH = SETTINGS_PATH
core.LOG_PATH = LOG_PATH

# Nomi delle azioni con la scorciatoia macOS: {chiave: (nome breve, nome completo)}
core.set_action_text({
    "fullscreen": ("Schermo intero", "Schermo intero (Ctrl+Cmd+F)"),
    "mission_control": ("Mission Control", "Mission Control (Ctrl+Su)"),
    "space_left": ("Spazio a sinistra", "Spazio a sinistra (Ctrl+Sinistra)"),
    "space_right": ("Spazio a destra", "Spazio a destra (Ctrl+Destra)"),
    "app_switcher": ("Cambia app", "Cambia app (Cmd+Tab)"),
    "minimize": ("Riduci finestra", "Riduci finestra (Cmd+M)"),
    "screenshot": ("Screenshot area", "Screenshot di un'area (Shift+Cmd+4)"),
    "lock_screen": ("Blocca schermo", "Blocca lo schermo (Ctrl+Cmd+Q)"),
    "spotlight": ("Spotlight", "Spotlight (Cmd+Spazio)"),
})

# Scorciatoie da tastiera: azione -> (codice tasto, modificatori)
SHORTCUTS = {
    "fullscreen": (3, kCGEventFlagMaskControl | kCGEventFlagMaskCommand),                   # F
    "mission_control": (126, kCGEventFlagMaskControl | kCGEventFlagMaskSecondaryFn),        # freccia su
    "space_left": (123, kCGEventFlagMaskControl | kCGEventFlagMaskSecondaryFn),            # freccia sinistra
    "space_right": (124, kCGEventFlagMaskControl | kCGEventFlagMaskSecondaryFn),           # freccia destra
    "app_switcher": (48, kCGEventFlagMaskCommand),                                          # Tab
    "minimize": (46, kCGEventFlagMaskCommand),                                              # M
    "screenshot": (21, kCGEventFlagMaskCommand | kCGEventFlagMaskShift),                    # 4
    "lock_screen": (12, kCGEventFlagMaskControl | kCGEventFlagMaskCommand),                 # Q
    "spotlight": (49, kCGEventFlagMaskCommand),                                             # Spazio
}
# Tasti multimediali (come quelli della tastiera): azione -> codice NX_KEYTYPE
MEDIA_KEYS = {"play_pause": 16, "next_track": 17, "prev_track": 18,
              "volume_up": 0, "volume_down": 1, "mute": 7}
ARROW_CODES = (123, 124, 125, 126)
KEY_NAMES = {36: "Invio", 48: "Tab", 49: "Spazio", 51: "Canc", 53: "Esc", 117: "Canc avanti",
             123: "←", 124: "→", 125: "↓", 126: "↑", 122: "F1", 120: "F2", 99: "F3", 118: "F4",
             96: "F5", 97: "F6", 98: "F7", 100: "F8", 101: "F9", 109: "F10", 103: "F11", 111: "F12"}
MODIFIER_MASK = 0x1E0000   # shift | control | option | command


def shortcut_label(code, flags, chars):
    mods = (("⌃" if flags & 0x40000 else "") + ("⌥" if flags & 0x80000 else "")
            + ("⇧" if flags & 0x20000 else "") + ("⌘" if flags & 0x100000 else ""))
    return mods + (KEY_NAMES.get(code) or (chars.upper() if chars else f"tasto {code}"))


class Mouse(core.MouseBase):
    """Eventi Quartz (piu' veloci e affidabili di pyautogui su macOS)."""

    permission_name = "Accessibilità"

    def position(self):
        p = CGEventGetLocation(CGEventCreate(None))
        return p.x, p.y

    def _list_displays(self):
        _, ids, _ = CGGetActiveDisplayList(16, None, None)
        rects = []
        for d in ids or [CGMainDisplayID()]:
            b = CGDisplayBounds(d)
            rects.append((b.origin.x, b.origin.y, b.size.width, b.size.height))
        return sorted(rects)

    def _warp(self, x, y):
        CGWarpMouseCursorPosition((x, y))

    def _trusted(self):
        return AXIsProcessTrusted()

    def _emit_move(self, x, y, dragging):
        kind = kCGEventLeftMouseDragged if dragging else kCGEventMouseMoved
        CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kind, (x, y), kCGMouseButtonLeft))

    def _emit_button(self, button, down, x, y, clicks):
        kinds = {("left", True): kCGEventLeftMouseDown, ("left", False): kCGEventLeftMouseUp,
                 ("right", True): kCGEventRightMouseDown, ("right", False): kCGEventRightMouseUp}
        which = kCGMouseButtonRight if button == "right" else kCGMouseButtonLeft
        ev = CGEventCreateMouseEvent(None, kinds[(button, down)], (x, y), which)
        CGEventSetIntegerValueField(ev, kCGMouseEventClickState, clicks)
        CGEventPost(kCGHIDEventTap, ev)

    def _emit_scroll(self, pixels):
        CGEventPost(kCGHIDEventTap, CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitPixel, 1, int(pixels)))

    def _emit_key(self, code, flags):
        if code in ARROW_CODES:
            flags |= kCGEventFlagMaskSecondaryFn
        for down in (True, False):
            ev = CGEventCreateKeyboardEvent(None, code, down)
            CGEventSetFlags(ev, flags)
            CGEventPost(kCGHIDEventTap, ev)

    def supports(self, action):
        return action in SHORTCUTS or action in MEDIA_KEYS

    def _emit_action(self, action):
        if action in MEDIA_KEYS:
            # tasto multimediale: evento di sistema, come i tasti F7-F12
            for down in (True, False):
                state = 0xA00 if down else 0xB00
                ev = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
                    NSEventTypeSystemDefined, (0, 0), state, 0, 0, None, 8, (MEDIA_KEYS[action] << 16) | state, -1)
                CGEventPost(kCGHIDEventTap, ev.CGEvent())
        else:
            self._emit_key(*SHORTCUTS[action])


class MenuBar(NSObject):
    """Icona nella barra dei menu: pausa/ripresa ed uscita senza terminale.

    Gira sul thread principale: pump() va chiamato a ogni frame per far arrivare i click sul menu.
    """

    def initWithController_(self, ctrl):
        self = objc.super(MenuBar, self).init()
        if self is None:
            return None
        self.ctrl = ctrl
        self.quit_requested = False
        self.shown_paused = None
        self.app = NSApplication.sharedApplication()
        self.app.finishLaunching()

        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        self.status_line = menu.addItemWithTitle_action_keyEquivalent_("", None, "")
        self.status_line.setEnabled_(False)
        self.toggle_item = menu.addItemWithTitle_action_keyEquivalent_("", "toggle:", "")
        self.toggle_item.setTarget_(self)
        self.toggle_item.setEnabled_(True)
        self.settings = None   # finestra Impostazioni, assegnata da main()
        self.stoprec_item = menu.addItemWithTitle_action_keyEquivalent_("Ferma registrazione sequenza", "stoprec:", "")
        self.stoprec_item.setTarget_(self)
        self.stoprec_item.setEnabled_(True)
        self.shown_recording = None
        settings_item = menu.addItemWithTitle_action_keyEquivalent_("Impostazioni…", "settings:", ",")
        settings_item.setTarget_(self)
        settings_item.setEnabled_(True)
        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = menu.addItemWithTitle_action_keyEquivalent_("Esci", "quit:", "q")
        quit_item.setTarget_(self)
        quit_item.setEnabled_(True)
        self.item.setMenu_(menu)
        self.refresh()
        return self

    @objc.python_method
    def refresh(self):
        paused = self.ctrl.paused
        recording = self.settings is not None and self.settings.macro_monitor is not None
        self.shown_paused = paused
        self.shown_recording = recording
        self.stoprec_item.setHidden_(not recording)
        self.item.button().setTitle_("⏺" if recording else (core.MENUBAR_TITLE_PAUSED if paused else core.MENUBAR_TITLE_ACTIVE))
        self.status_line.setTitle_("Stato: in pausa" if paused else "Stato: attivo")
        self.toggle_item.setTitle_("Attiva" if paused else "Metti in pausa")

    @objc.python_method
    def pump(self):
        while True:
            ev = self.app.nextEventMatchingMask_untilDate_inMode_dequeue_(
                NSEventMaskAny, None, NSDefaultRunLoopMode, True)
            if ev is None:
                break
            self.app.sendEvent_(ev)
        recording = self.settings is not None and self.settings.macro_monitor is not None
        if self.ctrl.paused != self.shown_paused or recording != self.shown_recording:   # pausa anche col pugno
            self.refresh()

    @objc.python_method
    def close(self):
        NSStatusBar.systemStatusBar().removeStatusItem_(self.item)

    def toggle_(self, sender):
        self.ctrl.set_paused(not self.ctrl.paused)
        self.refresh()

    def settings_(self, sender):
        if self.settings is not None:
            self.settings.show()

    def stoprec_(self, sender):
        if self.settings is not None:
            self.settings.stop_macro()

    def quit_(self, sender):
        self.quit_requested = True


class SettingsWindow(NSObject):
    """Finestra Impostazioni: test dei comandi dal vivo e parametri regolabili."""

    def initWithController_mouse_(self, ctrl, mouse):
        self = objc.super(SettingsWindow, self).init()
        if self is None:
            return None
        self.ctrl = ctrl
        self.mouse = mouse
        self.sliders = {}   # nome costante -> (slider, etichetta valore, formato)
        self.checks = {}    # voce di test -> (campo di testo, nome)
        self.popups = {}    # gesto -> menu a tendina dell'azione
        self.cameras = []   # webcam elencate nel menu (ID, nome)
        self.camera_dirty = False   # True quando l'utente sceglie un'altra webcam
        self.call_monitor = None    # monitor globale per registrare il click di risposta/rifiuto
        self.call_target = None
        self.macro_monitor = None   # monitor globale attivo durante la registrazione di una sequenza
        self.macro_steps = []
        self.macro_last = None
        self.recorder = None        # monitor tastiera attivo durante la registrazione di una scorciatoia
        self.popup_info = {}        # tag del menu -> (modalita', gesto)
        self.row_views = {"one": [], "two": []}   # controlli delle righe, mostrati secondo la modalita' mani
        self.last_refresh = 0.0
        self.build()
        return self

    @objc.python_method
    def build(self):
        W, H = 560, 640
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(160, 120, W, H), style, NSBackingStoreBuffered, False)
        self.window.setTitle_("Impostazioni - Hand Gesture Mouse")
        self.window.setReleasedWhenClosed_(False)
        tabs = NSTabView.alloc().initWithFrame_(NSMakeRect(10, 10, W - 20, H - 20))
        self.window.contentView().addSubview_(tabs)
        CW, CH = W - 44, H - 76   # area utile di ogni scheda

        def page(title):
            item = NSTabViewItem.alloc().initWithIdentifier_(title)
            item.setLabel_(title)
            view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, CW, CH))
            item.setView_(view)
            tabs.addTabViewItem_(item)
            return view

        def text(view, s, x, y, w, h=18, size=12, bold=False, mono=False):
            t = NSTextField.labelWithString_(s)
            t.setFrame_(NSMakeRect(x, y, w, h))
            if bold:
                t.setFont_(NSFont.boldSystemFontOfSize_(size))
            elif mono:
                t.setFont_(NSFont.monospacedSystemFontOfSize_weight_(size, 0.0))
            else:
                t.setFont_(NSFont.systemFontOfSize_(size))
            view.addSubview_(t)
            return t

        def button(view, title, x, y, w, action, switch=False):
            b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, 24))
            b.setTitle_(title)
            b.setButtonType_(3 if switch else 7)   # 3 = interruttore, 7 = pulsante
            if not switch:
                b.setBezelStyle_(1)
            b.setTarget_(self)
            b.setAction_(action)
            view.addSubview_(b)
            return b

        # --- scheda Test -------------------------------------------------------
        v = page("Test dei comandi")
        y = CH - 34
        self.gesture_label = text(v, "-", 10, y, CW - 20, 26, 20, bold=True)
        y -= 26
        self.metric1 = text(v, "", 10, y, CW - 20, size=11, mono=True)
        y -= 18
        self.metric2 = text(v, "", 10, y, CW - 20, size=11, mono=True)
        y -= 28
        names = [("move", "Muovi il cursore"), ("click", "Click sinistro"), ("drag", "Trascinamento"),
                 ("right", "Click destro"), ("scroll", "Scroll"), ("fist", "Pausa (pugno)"),
                 ("three", "Tre dita alzate"), ("rock", "Indice + mignolo"),
                 ("volume", "Volume (mano aperta)"), ("motion", "Movimento registrato"),
                 ("swipe_left", "Swipe a sinistra"), ("swipe_right", "Swipe a destra")]
        for i, (key, name) in enumerate(names):
            self.checks[key] = (text(v, "", 10 + (i % 2) * 255, y - (i // 2) * 22, 245), name)
        y -= 6 * 22 + 8
        self.dry_box = button(v, "Modalità test: non muovere il mouse vero", 10, y - 4, 330, "dry:", switch=True)
        button(v, "Azzera test", 370, y - 4, 130, "clear:")
        y -= 30
        self.events_label = text(v, "", 10, y - 96, CW - 20, 96)

        # --- scheda Azioni -----------------------------------------------------
        v = page("Azioni dei gesti")
        y = CH - 30
        self.mode_label = text(v, "", 10, y, CW - 20, 18, 13, bold=True)
        y -= 22
        text(v, "Ogni gesto va tenuto fermo per il tempo impostato in Parametri.", 10, y, CW - 20, size=11)
        y -= 16
        text(v, "Prova le azioni con la Modalità test (scheda Test): vedi cosa farebbero senza eseguirle.", 10, y, CW - 20, size=11)
        y -= 40
        for mode, gestures in (("one", core.ACTION_GESTURES), ("two", core.FREE_HAND_GESTURES)):
            row_y = y
            for i, (key, name, _) in enumerate(gestures):
                label = text(v, name, 10, row_y + 4, 250)
                popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(270, row_y, 240, 26), False)
                tag = i if mode == "one" else 100 + i
                popup.setTag_(tag)
                popup.setTarget_(self)
                popup.setAction_("gesture:")
                v.addSubview_(popup)
                self.popups[(mode, key)] = popup
                self.popup_info[tag] = (mode, key)
                self.row_views[mode] += [label, popup]
                row_y -= 40
        button(v, "Registra scorciatoia…", 10, 106, 170, "record:")
        button(v, "Elimina registrate", 190, 106, 150, "clearcustom:")
        button(v, "Registra sequenza…", 10, 74, 170, "macrorec:")
        button(v, "Ferma registrazione", 190, 74, 150, "macrostop:")
        button(v, "Elimina sequenze", 350, 74, 140, "macroclear:")
        self.record_note = text(v, "", 10, 46, CW - 20, 18, size=11)

        # --- scheda Movimenti --------------------------------------------------
        v = page("Movimenti")
        y = CH - 30
        text(v, "Mano aperta: movimento rapido a sinistra o a destra", 10, y, CW - 20, 18, 13, bold=True)
        y -= 20
        text(v, "Vale per la mano del mouse (con una mano, per l'unica mano). «Sinistra» è la tua sinistra.", 10, y, CW - 20, size=11)
        y -= 16
        text(v, "Distanza e pausa si regolano in Parametri; alzare o abbassare la mano aperta regola il volume.", 10, y, CW - 20, size=11)
        y -= 38
        self.swipe_popups = {}
        for i, (direction, title) in enumerate((("left", "Mano aperta → sinistra"), ("right", "Mano aperta → destra"))):
            text(v, title, 10, y + 4, 200)
            popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(215, y, 295, 26), False)
            popup.setTag_(400 + i)
            popup.setTarget_(self)
            popup.setAction_("swipe:")
            v.addSubview_(popup)
            self.swipe_popups[direction] = popup
            y -= 36
        y -= 14
        text(v, "Movimenti registrati", 10, y, CW - 20, 18, 13, bold=True)
        y -= 20
        text(v, "Scegli la posa (tre dita, mignolo, mano aperta...), premi Registra: dopo 3 s muovi la mano per 2 s.", 10, y, CW - 20, size=11)
        y -= 16
        text(v, "Una mano: mano aperta, tre dita, indice+mignolo o mignolo. Due mani: la mano libera.", 10, y, CW - 20, size=11)
        y -= 36
        button(v, "Registra movimento…", 10, y, 170, "motionrec:")
        button(v, "Annulla", 190, y, 100, "motioncancel:")
        y -= 28
        self.motion_note = text(v, "", 10, y, CW - 20, 18, size=11)
        y -= 40
        self.motion_rows = []
        for i in range(core.MAX_MOTIONS):
            label = text(v, "", 10, y + 4, 205)
            popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(215, y, 230, 26), False)
            popup.setTag_(200 + i)
            popup.setTarget_(self)
            popup.setAction_("motionaction:")
            v.addSubview_(popup)
            delete = button(v, "Elimina", 450, y, 60, "motiondel:")
            delete.setTag_(300 + i)
            self.motion_rows.append((label, popup, delete))
            y -= 38

        # --- scheda Parametri --------------------------------------------------
        v = page("Parametri")
        y = CH - 24
        for i, (key, label, lo, hi, fmt) in enumerate(core.TUNABLES):
            text(v, label, 10, y, 190)
            s = NSSlider.alloc().initWithFrame_(NSMakeRect(205, y - 2, 190, 20))
            s.setMinValue_(lo)
            s.setMaxValue_(hi)
            s.setTag_(i)
            s.setContinuous_(True)
            s.setTarget_(self)
            s.setAction_("slider:")
            v.addSubview_(s)
            self.sliders[key] = (s, text(v, "", 405, y, 90, size=12, mono=True), fmt)
            y -= 24
        self.invert_box = button(v, "Inverti direzione dello scroll", 10, y - 4, 300, "invert:", switch=True)
        y -= 40
        button(v, "Ripristina predefiniti", 10, y, 170, "reset:")

        # --- scheda Generale ---------------------------------------------------
        v = page("Generale")
        y = CH - 34
        text(v, "Webcam", 10, y + 4, 110)
        self.camera_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(120, y, 270, 26), False)
        self.camera_popup.setTarget_(self)
        self.camera_popup.setAction_("camera:")
        v.addSubview_(self.camera_popup)
        button(v, "Aggiorna elenco", 400, y, 110, "cameras:")
        y -= 50
        text(v, "Mani", 10, y + 4, 110)
        self.hands_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(120, y, 390, 26), False)
        self.hands_popup.addItemsWithTitles_([title for _, title in core.HAND_MODES])
        self.hands_popup.setTarget_(self)
        self.hands_popup.setAction_("hands:")
        v.addSubview_(self.hands_popup)
        y -= 24
        text(v, "Con due mani una controlla il cursore e click,", 120, y, CW - 130, size=11)
        y -= 16
        text(v, "l'altra i gesti-azione (tre dita, indice + mignolo).", 120, y, CW - 130, size=11)
        y -= 40
        text(v, "Permessi", 10, y + 4, 110)
        self.perm_label = text(v, "", 120, y + 4, CW - 130)
        y -= 34
        button(v, "Apri Accessibilità", 120, y, 170, "access:")
        button(v, "Apri Fotocamera", 300, y, 170, "cameraperm:")
        y -= 46
        self.volume_box = button(v, "Volume con la mano aperta (alzala / abbassala)", 10, y, 420, "volume:", switch=True)
        y -= 46
        text(v, "Chiamate", 10, y + 4, 110)
        button(v, "Registra click «Rispondi»", 120, y, 190, "callans:")
        button(v, "Registra click «Rifiuta»", 320, y, 190, "calldec:")
        y -= 30
        button(v, "Registra click «Chiudi»", 120, y, 190, "callend:")
        button(v, "Annulla", 320, y, 90, "callcancel:")
        y -= 26
        self.call_label = text(v, "", 120, y, CW - 130, size=11)
        y -= 22
        self.call_note = text(v, "", 10, y, CW - 20, 18, size=11)
        y -= 18
        text(v, "Con la notifica di chiamata visibile: premi il pulsante, poi clicca sul suo «Accetta» / «Rifiuta».", 10, y, CW - 20, size=11)
        y -= 16
        text(v, "Il mignolo alzato risponde e, rifatto, chiude (usa i click «Rispondi» e «Chiudi»).", 10, y, CW - 20, size=11)
        self.fill_cameras()
        self.refill_actions()

    # -- aggiornamento dei controlli -------------------------------------------
    @objc.python_method
    def sync(self, key):
        slider, value_label, fmt = self.sliders[key]
        value = getattr(core, key)
        slider.setDoubleValue_(value)
        value_label.setStringValue_(fmt.format(int(value) if "d" in fmt else value))

    @objc.python_method
    def sync_all(self):
        for key in self.sliders:
            self.sync(key)
        self.invert_box.setState_(1 if core.SCROLL_INVERT else 0)
        self.volume_box.setState_(1 if core.VOLUME_GESTURE else 0)
        self.hands_popup.selectItemAtIndex_([k for k, _ in core.HAND_MODES].index(core.HAND_MODE))
        keys = [k for k, _, _ in core.ACTIONS]
        for direction, popup in self.swipe_popups.items():
            popup.selectItemAtIndex_(keys.index(core.SWIPE_ACTIONS.get(direction, "none")))
        for (mode, gesture), popup in self.popups.items():
            mapping = core.GESTURE_ACTIONS if mode == "one" else core.GESTURE_ACTIONS_TWO
            popup.selectItemAtIndex_(keys.index(mapping.get(gesture, "none")))
        two = core.HAND_MODE != "one"
        for mode, views in self.row_views.items():
            for view in views:
                view.setHidden_(two if mode == "one" else not two)
        self.mode_label.setStringValue_(
            "Modalità due mani: gesti della mano libera" if two else "Modalità una mano")

    @objc.python_method
    def refill_actions(self):
        """Riempie i menu delle azioni (anche dopo aver registrato o eliminato una scorciatoia)."""
        titles = [t for _, _, t in core.ACTIONS]
        for popup in list(self.popups.values()) + list(self.swipe_popups.values()):
            popup.removeAllItems()
            popup.addItemsWithTitles_(titles)
        self.sync_all()
        self.refill_motions()

    @objc.python_method
    def refill_motions(self):
        titles = [t for _, _, t in core.ACTIONS]
        keys = [k for k, _, _ in core.ACTIONS]
        for i, (label, popup, delete) in enumerate(self.motion_rows):
            visible = i < len(core.MOTIONS)
            for view in (label, popup, delete):
                view.setHidden_(not visible)
            if visible:
                motion = core.MOTIONS[i]
                label.setStringValue_(f"{motion['name']} · {core.POSE_NAMES[motion['pose']]}")
                popup.removeAllItems()
                popup.addItemsWithTitles_(titles)
                popup.selectItemAtIndex_(keys.index(motion["action"]) if motion["action"] in keys else 0)

    @objc.python_method
    def fill_cameras(self):
        self.cameras = list_cameras()
        self.camera_popup.removeAllItems()
        self.camera_popup.addItemsWithTitles_([name for _, name in self.cameras] or ["(nessuna webcam trovata)"])
        if self.cameras:
            self.camera_popup.selectItemAtIndex_(min(camera_index(), len(self.cameras) - 1))

    @objc.python_method
    def show(self):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)

    @objc.python_method
    def refresh(self, label):
        """Chiamato a ogni frame con il gesto riconosciuto."""
        key = core.LABEL_KEYS.get(label)
        if key:
            self.ctrl.verified.add(key)
        if self.ctrl.motions_changed:
            self.ctrl.motions_changed = False
            self.refill_motions()
        now = time.monotonic()
        if not self.window.isVisible() or now - self.last_refresh < 0.1:
            return
        self.last_refresh = now
        self.motion_note.setStringValue_(self.ctrl.motion_message)
        self.call_label.setStringValue_(
            f"Rispondi {'✓' if 'answer_call' in core.CALL_POINTS else '—'}    "
            f"Rifiuta {'✓' if 'decline_call' in core.CALL_POINTS else '—'}    "
            f"Chiudi {'✓' if 'end_call' in core.CALL_POINTS else '—'}")

        status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo)
        self.perm_label.setStringValue_(
            f"Fotocamera {'✓' if status == 3 else '✗'}    "
            f"Accessibilità {'✓' if AXIsProcessTrusted() else '✗ manca'}")
        self.gesture_label.setStringValue_(label)
        self.gesture_label.setTextColor_(NSColor.systemRedColor() if self.ctrl.paused else NSColor.labelColor())
        if self.ctrl.debug:
            d_ti, d_tm, ext = self.ctrl.debug
            self.metric1.setStringValue_(
                f"Pollice-indice {d_ti:.2f} (pizzico sotto {core.PINCH_START:.2f})   "
                f"Pollice-medio {d_tm:.2f}")
            names = ["indice", "medio", "anulare", "mignolo"]
            self.metric2.setStringValue_("Dita estese: " + "  ".join(
                f"{n} {'✓' if e else '·'}" for n, e in zip(names, ext)))
        else:
            self.metric1.setStringValue_("Nessuna mano nell'inquadratura")
            self.metric2.setStringValue_("")
        for k, (field, name) in self.checks.items():
            ok = k in self.ctrl.verified
            field.setStringValue_(("✓ " if ok else "○ ") + name)
            field.setTextColor_(NSColor.systemGreenColor() if ok else NSColor.secondaryLabelColor())
        recent = "\n".join(reversed(self.mouse.events)) or "(nessun comando ancora)"
        self.events_label.setStringValue_("Ultimi comandi:\n" + recent)

    # -- azioni dei controlli ---------------------------------------------------
    def slider_(self, sender):
        key = core.TUNABLES[sender.tag()][0]
        value = sender.doubleValue()
        setattr(core, key, int(round(value)) if isinstance(core.DEFAULTS[key], int) else value)
        # il rilascio deve restare piu' ampio dell'inizio, altrimenti l'isteresi si rompe
        if key == "PINCH_START" and core.PINCH_RELEASE < core.PINCH_START + 0.05:
            setattr(core, "PINCH_RELEASE", core.PINCH_START + 0.05)
            self.sync("PINCH_RELEASE")
        elif key == "PINCH_RELEASE" and core.PINCH_RELEASE < core.PINCH_START + 0.05:
            setattr(core, "PINCH_START", core.PINCH_RELEASE - 0.05)
            self.sync("PINCH_START")
        self.sync(key)
        event = NSApplication.sharedApplication().currentEvent()
        if event is not None and event.type() == NSEventTypeLeftMouseUp:   # salva a slider rilasciato
            core.save_settings()

    def gesture_(self, sender):
        mode, gesture = self.popup_info[sender.tag()]
        mapping = core.GESTURE_ACTIONS if mode == "one" else core.GESTURE_ACTIONS_TWO
        mapping[gesture] = core.ACTIONS[sender.indexOfSelectedItem()][0]
        core.save_settings()

    def record_(self, sender):
        if self.recorder is not None:
            return
        if len(core.CUSTOM_ACTIONS) >= 6:
            self.record_note.setStringValue_("Massimo 6 scorciatoie registrate: eliminane qualcuna.")
            return
        self.record_note.setStringValue_("Premi ora la combinazione di tasti (Esc da solo = annulla)...")
        self.recorder = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(NSEventMaskKeyDown, self.captured)

    @objc.python_method
    def captured(self, event):
        NSEvent.removeMonitor_(self.recorder)
        self.recorder = None
        code, flags = event.keyCode(), int(event.modifierFlags()) & MODIFIER_MASK
        if code == 53 and not flags:
            self.record_note.setStringValue_("Registrazione annullata.")
            return None
        label = shortcut_label(code, flags, event.charactersIgnoringModifiers())
        number = max([int(e["id"][6:]) for e in core.CUSTOM_ACTIONS] + [0]) + 1
        core.register_custom({"id": f"custom{number}", "label": label, "code": code, "flags": flags})
        core.save_settings()
        self.refill_actions()
        self.record_note.setStringValue_(
            f"Registrata {label}: ora scegli «{core.ACTION_SHORT[f'custom{number}']}» nel menu di un gesto.")
        return None

    def macrorec_(self, sender):
        if self.macro_monitor is not None or self.recorder is not None:
            return
        if len(core.MACROS) >= core.MAX_MACROS:
            self.record_note.setStringValue_(f"Massimo {core.MAX_MACROS} sequenze: eliminane qualcuna.")
            return
        if not CGPreflightListenEventAccess():
            CGRequestListenEventAccess()   # macOS chiede "Monitoraggio input" per vedere tasti e click
        self.macro_steps = []
        self.macro_last = None
        mask = NSEventMaskKeyDown | NSEventMaskLeftMouseDown | NSEventMaskRightMouseDown
        self.macro_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(mask, self.macro_event)
        self.record_note.setStringValue_("Registrazione… esegui ora tasti e click, poi «Ferma registrazione» (anche da ✋ nel menu).")

    @objc.python_method
    def macro_event(self, event):
        if len(self.macro_steps) >= core.MAX_STEPS:
            return
        now = time.monotonic()
        delay = 0.3 if self.macro_last is None else now - self.macro_last
        if event.type() == NSEventTypeKeyDown:
            if event.isARepeat():
                return
            step = {"k": "key", "code": int(event.keyCode()), "flags": int(event.modifierFlags()) & MODIFIER_MASK}
        else:
            where = NSEvent.mouseLocation()   # coordinate Cocoa (origine in basso) -> coordinate schermo
            height = CGDisplayBounds(CGMainDisplayID()).size.height
            step = {"k": "click", "x": float(where.x), "y": float(height - where.y),
                    "b": "right" if event.type() == NSEventTypeRightMouseDown else "left"}
        step["d"] = round(delay, 2)
        self.macro_steps.append(step)
        self.macro_last = now
        self.record_note.setStringValue_(f"Registrazione… {len(self.macro_steps)} passi")

    @objc.python_method
    def stop_macro(self):
        """Chiude la registrazione e crea l'azione (chiamato dal pulsante o dal menu ✋)."""
        if self.macro_monitor is None:
            return
        NSEvent.removeMonitor_(self.macro_monitor)
        self.macro_monitor = None
        if not self.macro_steps:
            self.record_note.setStringValue_(
                "Nessun passo registrato. Se hai usato tasti e click, abilita «Monitoraggio input» per l'app.")
            return
        number = max([int(m["id"][5:]) for m in core.MACROS] + [0]) + 1
        core.register_macro({"id": f"macro{number}", "name": f"Sequenza {number}", "steps": list(self.macro_steps)})
        core.save_settings()
        self.refill_actions()
        self.record_note.setStringValue_(
            f"Registrata «{core.ACTION_SHORT[f'macro{number}']}» ({len(self.macro_steps)} passi): scegli l'azione nel menu di un gesto.")

    def macrostop_(self, sender):
        self.stop_macro()

    def macroclear_(self, sender):
        core.remove_macros()
        core.save_settings()
        self.refill_actions()
        self.record_note.setStringValue_("Sequenze registrate eliminate.")

    def clearcustom_(self, sender):
        core.remove_customs()
        core.save_settings()
        self.refill_actions()
        self.record_note.setStringValue_("Scorciatoie registrate eliminate.")

    def camera_(self, sender):
        i = sender.indexOfSelectedItem()
        if i < len(self.cameras):
            core.CAMERA_ID = self.cameras[i][0]
            self.camera_dirty = True
            core.save_settings()

    def cameras_(self, sender):
        self.fill_cameras()

    def hands_(self, sender):
        setattr(core, "HAND_MODE", core.HAND_MODES[sender.indexOfSelectedItem()][0])
        self.ctrl.pose = None
        self.sync_all()
        core.save_settings()

    def access_(self, sender):
        subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])

    def cameraperm_(self, sender):
        subprocess.run(["open", CAMERA_SETTINGS_URL])

    def swipe_(self, sender):
        direction = ("left", "right")[sender.tag() - 400]
        core.SWIPE_ACTIONS[direction] = core.ACTIONS[sender.indexOfSelectedItem()][0]
        core.save_settings()

    def volume_(self, sender):
        core.VOLUME_GESTURE = bool(sender.state())
        core.save_settings()

    def motionrec_(self, sender):
        self.ctrl.start_motion_recording()

    def motioncancel_(self, sender):
        self.ctrl.cancel_motion_recording()

    def motionaction_(self, sender):
        i = sender.tag() - 200
        if i < len(core.MOTIONS):
            core.MOTIONS[i]["action"] = core.ACTIONS[sender.indexOfSelectedItem()][0]
            core.save_settings()

    def motiondel_(self, sender):
        i = sender.tag() - 300
        if i < len(core.MOTIONS):
            core.remove_motion(core.MOTIONS[i]["id"])
            core.save_settings()
            self.refill_motions()

    def callans_(self, sender):
        self.start_call("answer_call")

    def calldec_(self, sender):
        self.start_call("decline_call")

    def callend_(self, sender):
        self.start_call("end_call")

    @objc.python_method
    def start_call(self, key):
        if self.call_monitor is not None:
            return
        if not CGPreflightListenEventAccess():
            CGRequestListenEventAccess()   # macOS chiede "Monitoraggio input" per vedere i click fuori dall'app
        self.call_target = key
        self.call_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSEventMaskLeftMouseDown, self.call_event)
        self.call_note.setStringValue_("Clicca ora sul pulsante della notifica (non l'ho ancora visto)...")

    @objc.python_method
    def call_event(self, event):
        where = NSEvent.mouseLocation()   # coordinate Cocoa (origine in basso) -> coordinate schermo
        height = CGDisplayBounds(CGMainDisplayID()).size.height
        core.CALL_POINTS[self.call_target] = [float(where.x), float(height - where.y)]
        NSEvent.removeMonitor_(self.call_monitor)
        self.call_monitor = None
        core.save_settings()
        self.call_note.setStringValue_(f"Registrato il click a ({where.x:.0f}, {height - where.y:.0f}).")

    def callcancel_(self, sender):
        if self.call_monitor is not None:
            NSEvent.removeMonitor_(self.call_monitor)
            self.call_monitor = None
            self.call_note.setStringValue_("Registrazione del click annullata.")

    def invert_(self, sender):
        setattr(core, "SCROLL_INVERT", bool(sender.state()))
        core.save_settings()

    def dry_(self, sender):
        self.mouse.dry_run = bool(sender.state())

    def clear_(self, sender):
        self.ctrl.verified.clear()
        self.mouse.events.clear()

    def reset_(self, sender):
        for key in core.SETTING_KEYS:
            setattr(core, key, core.DEFAULTS[key])
        setattr(core, "HAND_MODE", core.DEFAULT_HAND_MODE)
        core.GESTURE_ACTIONS.clear()
        core.GESTURE_ACTIONS.update(core.DEFAULT_GESTURE_ACTIONS)
        core.GESTURE_ACTIONS_TWO.clear()
        core.GESTURE_ACTIONS_TWO.update(core.DEFAULT_GESTURE_ACTIONS_TWO)
        core.SWIPE_ACTIONS.update(core.DEFAULT_SWIPE_ACTIONS)
        self.sync_all()
        core.save_settings()


CAMERA_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"
def fail(title, text, settings_url=None):
    """Mostra un avviso (l'app non ha console) ed esce."""
    core.log(f"{title}: {text}")
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(text)
    alert.addButtonWithTitle_("Apri Impostazioni di Sistema" if settings_url else "OK")
    if settings_url:
        alert.addButtonWithTitle_("Chiudi")
    if alert.runModal() == NSAlertFirstButtonReturn and settings_url:
        subprocess.run(["open", settings_url])
    sys.exit(1)


def ensure_camera_access():
    """Chiede il permesso Fotocamera e aspetta la risposta (altrimenti il primo avvio esce subito)."""
    status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo)
    core.log(f"Stato permesso fotocamera: {status} (0=da decidere, 2=negato, 3=consentito)")
    if status == 0:   # non ancora deciso: macOS mostra la richiesta
        core.log("Richiedo il permesso fotocamera e aspetto la risposta...")
        answer = []

        def on_answer(granted):
            answer.append(granted)

        AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeVideo, on_answer)
        while not answer:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
        return bool(answer[0])
    return status == 3


def ensure_accessibility():
    """Se manca il permesso Accessibilita' macOS mostra la richiesta; l'app resta aperta."""
    return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))


class FrameGrabber(NSObject):
    """Riceve i frame dalla webcam (su un thread di AVFoundation) e conserva l'ultimo."""

    def init(self):
        self = objc.super(FrameGrabber, self).init()
        if self is None:
            return None
        self.cond = threading.Condition()
        self.frame = None
        self.seq = 0
        return self

    def captureOutput_didOutputSampleBuffer_fromConnection_(self, output, sample, connection):
        pixels = CMSampleBufferGetImageBuffer(sample)
        if pixels is None:
            return
        CVPixelBufferLockBaseAddress(pixels, 0)
        try:
            w, h = CVPixelBufferGetWidth(pixels), CVPixelBufferGetHeight(pixels)
            stride = CVPixelBufferGetBytesPerRow(pixels)
            raw = CVPixelBufferGetBaseAddress(pixels).as_buffer(stride * h)
            frame = np.frombuffer(raw, np.uint8).reshape(h, stride // 4, 4)[:, :w, :3].copy()   # BGRA -> BGR
        finally:
            CVPixelBufferUnlockBaseAddress(pixels, 0)
        with self.cond:
            self.frame = frame
            self.seq += 1
            self.cond.notify_all()


class AVCamera:
    """Webcam via AVFoundation. Apre esattamente il dispositivo scelto: gli indici di OpenCV non
    corrispondono ai nomi dell'elenco, quindi non si possono usare per scegliere la webcam."""

    def __init__(self, device):
        self.name = device.localizedName()
        self.session = AVCaptureSession.alloc().init()
        self.grabber = FrameGrabber.alloc().init()
        self.last_seq = 0
        self.opened = False
        cam_input, _ = AVCaptureDeviceInput.deviceInputWithDevice_error_(device, None)
        if cam_input is None:
            return
        output = AVCaptureVideoDataOutput.alloc().init()
        output.setVideoSettings_({kCVPixelBufferPixelFormatTypeKey: kCVPixelFormatType_32BGRA})
        output.setAlwaysDiscardsLateVideoFrames_(True)
        self.queue = dispatch.dispatch_queue_create(b"handmouse.camera", None)
        output.setSampleBufferDelegate_queue_(self.grabber, self.queue)
        self.session.beginConfiguration()
        if not (self.session.canAddInput_(cam_input) and self.session.canAddOutput_(output)):
            self.session.commitConfiguration()
            return
        self.session.addInput_(cam_input)
        self.session.addOutput_(output)
        self.session.commitConfiguration()
        self.session.startRunning()
        self.opened = self.read(timeout=5.0)[0]   # attende il primo frame
        if not self.opened:
            self.session.stopRunning()

    def isOpened(self):
        return self.opened

    def read(self, timeout=1.0):
        with self.grabber.cond:
            if not self.grabber.cond.wait_for(lambda: self.grabber.seq != self.last_seq, timeout):
                return False, None
            self.last_seq = self.grabber.seq
            return True, self.grabber.frame

    def release(self):
        self.session.stopRunning()


def list_cameras():
    """Webcam disponibili come (ID univoco, nome)."""
    return [(d.uniqueID(), d.localizedName()) for d in AVCaptureDevice.devicesWithMediaType_(AVMediaTypeVideo)]


def camera_device():
    """Dispositivo scelto nelle Impostazioni (o quello di core.CAMERA_INDEX se non c'e')."""
    devices = list(AVCaptureDevice.devicesWithMediaType_(AVMediaTypeVideo))
    for d in devices:
        if d.uniqueID() == core.CAMERA_ID:
            return d
    return devices[core.CAMERA_INDEX] if core.CAMERA_INDEX < len(devices) else (devices[0] if devices else None)


def camera_index():
    """Posizione nell'elenco della webcam in uso."""
    device = camera_device()
    for i, (uid, _) in enumerate(list_cameras()):
        if device is not None and uid == device.uniqueID():
            return i
    return 0


def try_open_camera():
    device = camera_device()
    if device is None:
        return None
    cam = AVCamera(device)
    return cam if cam.isOpened() else None


def open_camera():
    cap = try_open_camera()
    if cap is None:
        fail("Impossibile aprire la camera",
             "Controlla che nessun'altra app la stia usando, o scegli un'altra webcam "
             "dalle Impostazioni (scheda Generale).")
    core.log(f"Webcam in uso: {cap.name}")
    return cap


def switch_camera(old, mouse):
    """Passa alla webcam scelta nelle Impostazioni; se non si apre resta su quella attuale."""
    old.release()
    new = try_open_camera()
    if new is None:
        core.log("Impossibile aprire la webcam scelta: torno a quella di prima")
        mouse.events.append("Impossibile aprire la webcam scelta")
        old.session.startRunning()
        return old
    core.log(f"Webcam cambiata: {new.name}")
    return new


def play_cue(kind):
    """Segnali sonori per la registrazione di un movimento: un tic al secondo, poi «ORA», poi esito."""
    sound = NSSound.soundNamed_({"tick": "Pop", "start": "Tink", "ok": "Glass", "fail": "Basso"}[kind])
    if sound is not None:
        sound.stop()
        sound.play()


def main():
    core.log("Avvio")
    core.load_settings()
    NSApplication.sharedApplication()
    if not ensure_camera_access():
        fail("Accesso alla fotocamera negato",
             "Hand Gesture Mouse ha bisogno della webcam. Abilitala in Impostazioni di Sistema > "
             "Privacy e sicurezza > Fotocamera, poi riapri l'app.", CAMERA_SETTINGS_URL)
    if not ensure_accessibility():
        core.log("Permesso Accessibilita' mancante: abilitalo in Impostazioni di Sistema > "
            "Privacy e sicurezza > Accessibilita' (poi riapri l'app).")
    cap = open_camera()
    core.log("Camera aperta")
    mouse = Mouse()
    ctrl = core.GestureController(mouse)
    ctrl.cue = play_cue
    two_hands = core.HAND_MODE != "one"
    hands = core.make_hands(2 if two_hands else 1)
    menubar = MenuBar.alloc().initWithController_(ctrl) if core.MENUBAR_ENABLED else None
    settings = None
    if menubar:
        settings = SettingsWindow.alloc().initWithController_mouse_(ctrl, mouse)
        menubar.settings = settings
    print(f"In esecuzione. Premi {core.QUIT_KEY.upper()} nella finestra di anteprima, usa l'icona nella barra dei menu "
          "(o Ctrl+C qui) per uscire.")

    try:
        while True:
            if settings and settings.camera_dirty:
                settings.camera_dirty = False
                cap = switch_camera(cap, mouse)
            if (core.HAND_MODE != "one") != two_hands:   # cambiata la modalita' mani dalle Impostazioni
                two_hands = core.HAND_MODE != "one"
                hands.close()
                hands = core.make_hands(2 if two_hands else 1)
            ok, frame = cap.read()
            if not ok:
                continue
            if frame.shape[1] > core.CAMERA_WIDTH:
                frame = cv2.resize(frame, (core.CAMERA_WIDTH, round(frame.shape[0] * core.CAMERA_WIDTH / frame.shape[1])))
            if core.MIRROR:
                frame = cv2.flip(frame, 1)
            core.FRAME_ASPECT = frame.shape[1] / frame.shape[0]
            results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            now = time.monotonic()
            label = core.process_hands(ctrl, results, now)

            if menubar:
                menubar.pump()
                settings.refresh(label)
                if menubar.quit_requested:
                    break

            if core.SHOW_PREVIEW:
                shown = label + ("  [TEST]" if mouse.dry_run else "")
                cv2.imshow("Hand Gesture Mouse", core.draw_preview(frame, results, shown, ctrl.paused, cap.name))
                key = cv2.waitKey(1) & 0xFF
                if key == ord(core.QUIT_KEY) or key == ord(core.QUIT_KEY.upper()):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        mouse.release(*ctrl.cursor)
        if menubar:
            menubar.close()
            core.save_settings()
        hands.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        err = traceback.format_exc()
        core.log(err)
        fail("Errore imprevisto", err[-700:])
