# Hand Gesture Mouse (macOS e Windows)

Controlla il cursore con la mano tramite la webcam. Python 3 + OpenCV + MediaPipe Hands.
Su macOS gli eventi passano da Quartz, su Windows da `user32` (ctypes): pyautogui non serve.

## Download

Dalla pagina **Releases** del repository scarichi l'ultima versione già pronta:

- **macOS:** `Hand-Gesture-Mouse-macOS.dmg` (Apple Silicon). Aprilo e trascina l'app in Applicazioni. L'app non è firmata
  da uno sviluppatore Apple: al primo avvio fai click destro sull'app → **Apri** → **Apri** (oppure, da Terminale:
  `xattr -dr com.apple.quarantine "/Applications/Hand Gesture Mouse.app"`). Poi concedi **Fotocamera** e **Accessibilità**.
- **Windows:** `Hand-Gesture-Mouse-Windows.zip`. Estrai la cartella e avvia `Hand Gesture Mouse.exe`. Se compare l'avviso
  di SmartScreen («Windows ha protetto il PC») scegli *Ulteriori informazioni* → *Esegui comunque*.

Le versioni si compilano da sole con GitHub Actions (`.github/workflows/release.yml`) ogni volta che si crea un tag `v*`.

## File del progetto

| File | A cosa serve |
|---|---|
| `gesture_core.py` | **Logica comune**: gesti, impostazioni, azioni, sequenze, smoothing, anteprima. Uguale per tutti i sistemi |
| `hand_mouse.py` | Parte **macOS**: eventi Quartz, webcam AVFoundation, icona barra dei menu, finestra Impostazioni (AppKit) |
| `hand_mouse_win.py` | Parte **Windows**: eventi `user32`, webcam DirectShow, icona area di notifica, Impostazioni (tkinter) |
| `requirements.txt` / `requirements-windows.txt` | Librerie per macOS / per Windows |
| `run.sh`, `build_app.sh`, `HandGestureMouse.spec` | Avvio e creazione del `.app` (macOS) |
| `setup_win.bat`, `run_win.bat`, `build_exe.bat` | Installazione, avvio e creazione dell'`.exe` (Windows) |
| `tests/` | Prove automatiche senza webcam (`test_core.py`, `test_win.py`, `smoke_mac.py`) |

## Windows

> La versione Windows è stata scritta e provata **solo con test automatici su un Mac** (user32 simulato):
> sul PC reale potrebbero servire piccoli aggiustamenti. Il log è in `%LOCALAPPDATA%\Hand Gesture Mouse\log.txt`.

**Cosa copiare sul PC** (cartella `hand-gesture-mouse`): `gesture_core.py`, `hand_mouse_win.py`,
`requirements-windows.txt`, `setup_win.bat`, `run_win.bat`, `build_exe.bat`, questo `README.md` (e, se vuoi,
`tests/`). **Non** copiare `.venv/`, `dist/`, `build/`, `Hand Gesture Mouse.app`, `hand_mouse.py`, `run.sh`.
Se vuoi portare le impostazioni del Mac, `settings.json` si può copiare in `%APPDATA%\Hand Gesture Mouse\`
(le scorciatoie e le sequenze registrate sul Mac però non valgono su Windows: vanno rifatte).

1. Installa **Python 3.11** (3.9–3.12 vanno bene, MediaPipe non supporta le versioni più recenti) da python.org,
   spuntando «Add python.exe to PATH».
2. Doppio click su `setup_win.bat` (crea `.venv` e installa le librerie).
3. Doppio click su `run_win.bat` per avviare. Nell'anteprima: **Q** esci, **S** Impostazioni, **P** pausa.
4. L'icona verde nell'area di notifica (vicino all'orologio, forse dentro la freccia ^) ha il menu: pausa,
   Impostazioni, esci. Diventa rossa in pausa e arancione durante la registrazione di una sequenza.
5. Per un `.exe` senza terminale: `build_exe.bat` → `dist\Hand Gesture Mouse\Hand Gesture Mouse.exe`.

Differenze rispetto al Mac: scorciatoie di Windows (F11 schermo intero, Win+Tab vista attività, Win+Ctrl+←/→ desktop
virtuali, Alt+Tab, Win+Giù, Win+Shift+S screenshot, Win+L blocca, Win+S ricerca); «monitor successivo» sposta il
cursore tra gli schermi; i comandi non arrivano alle finestre avviate «come amministratore» a meno che anche questa app lo sia.

## macOS

### Installazione

```bash
cd hand-gesture-mouse
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip   # il pip vecchio non trova i pacchetti per macOS e prova a compilare pyobjc
pip install -r requirements.txt
```

Nota: MediaPipe supporta Python 3.9–3.12. Se `pip install` fallisce su una versione più recente, crea il venv con 3.11 o 3.12.

### Avvio

Con un solo comando (attiva il venv e avvia l'app):

```bash
./run.sh
```

Oppure a mano, con il venv già attivo:

```bash
python hand_mouse.py
```

### App macOS (.app)

Per avere un'app che si apre con un doppio click, senza terminale:

```bash
./build_app.sh
```

Crea `dist/Hand Gesture Mouse.app` (circa 300 MB, include Python, OpenCV e MediaPipe). Trascinala in
Applicazioni e aprila. I permessi **Fotocamera** e **Accessibilità** vanno dati all'app stessa
("Hand Gesture Mouse"), non più al terminale.

Dopo ogni modifica a `hand_mouse.py` va rieseguito `./build_app.sh`. La firma è "ad-hoc", quindi
con la firma a requisito fisso i permessi dovrebbero restare validi anche dopo una ricompilazione; se macOS
li richiede, in Accessibilità togli l'app con `−` e riaggiungila.

### Permessi (primo avvio)

1. **Fotocamera** – macOS lo chiede la prima volta. Se non lo fa, abilita il tuo terminale in
   Impostazioni di Sistema → Privacy e sicurezza → **Fotocamera**.
2. **Accessibilità** – serve per muovere il cursore e cliccare. Aggiungi il tuo terminale in
   Impostazioni di Sistema → Privacy e sicurezza → **Accessibilità**, poi riavvia il terminale.

## Gesti

| Gesto | Azione |
|---|---|
| Indice alzato, muovi la mano | Muove il cursore |
| Pizzico rapido (pollice + indice) | Click sinistro (due pizzichi rapidi = doppio click) |
| Pizzico tenuto (~0,4 s), muovi, apri la mano | Click e trascinamento, rilascia per lasciare |
| Pizzico pollice + medio | Click destro |
| Indice + medio alzati (anulare/mignolo giù), muovi su/giù | Scroll |
| Pugno chiuso, tenuto ~0,6 s | Pausa / ripresa del tracking |
| Tre dita alzate (indice, medio, anulare), tenute ~0,7 s | Cursore sul monitor successivo *(azione modificabile)* |
| Indice e mignolo alzati, tenuti ~0,7 s | Schermo intero, Ctrl+Cmd+F *(azione modificabile)* |
| Mano aperta tenuta ferma ~0,5 s, poi alzala / abbassala | Volume su / giù, a scatti *(si può spegnere)* |
| `Q` nella finestra di anteprima | Esci (oppure Ctrl+C nel terminale) |

### Icona nella barra dei menu

Mentre l'app gira compare l'icona ✋ in alto a destra (⏸ quando è in pausa). Il menu ha:

- **Metti in pausa / Attiva** – come il gesto del pugno
- **Impostazioni…** (⌘,) – apre la finestra Impostazioni
- **Esci** – chiude l'app senza usare il terminale

L'icona si può cambiare o disattivare con `MENUBAR_*` nel blocco `CONFIG`.

### Finestra Impostazioni

Quattro schede:

**Test dei comandi**
- Gesto riconosciuto in tempo reale, distanze del pizzico e dita estese.
- Lista di controllo: ogni gesto diventa verde (✓) la prima volta che lo esegui.
- *Modalità test*: l'app riconosce i gesti ma **non muove il mouse vero né preme tasti**, così puoi provarli
  in sicurezza (nell'anteprima compare `[TEST]`). Ricordati di disattivarla per usare l'app.
- Elenco degli ultimi comandi eseguiti (click, trascinamento, azioni...).

**Azioni dei gesti** – l'elenco cambia secondo la modalità scelta in *Generale → Mani*:
- *Una mano*: due gesti a posa, tre dita e indice + mignolo.
- *Due mani*: la mano libera ha sei pose: un dito, due dita, tre dita, solo mignolo, indice + mignolo, pugno.
  La mano aperta (tutte le dita alzate) è la posizione di riposo e non fa mai nulla. Se il riconoscimento
  oscilla un istante tra due pose, il gesto non viene azzerato (serve una variazione di 0,3 s). Ogni modalità ha le sue azioni, salvate separatamente.

Azioni disponibili: nessuna, cursore sul monitor successivo, schermo intero (Ctrl+Cmd+F), Mission Control (Ctrl+Su),
spazio a sinistra/destra (Ctrl+←/→), cambia app (Cmd+Tab), riduci finestra (Cmd+M), screenshot di un'area
(Shift+Cmd+4), blocca schermo (Ctrl+Cmd+Q), Spotlight (Cmd+Spazio) e i **tasti multimediali**: play/pausa, brano
successivo/precedente, volume su/giù, muto (agiscono sull'app musicale attiva, come i tasti F7-F12). Le scorciatoie usano quelle
predefinite di macOS: se le hai cambiate in Impostazioni di Sistema → Tastiera, l'azione non partirà.

**Registra scorciatoia…** – premi il pulsante e poi la combinazione di tasti che vuoi (fino a 6, Esc da solo
annulla): compare nei menu come "Scorciatoia 1", "Scorciatoia 2"... e puoi assegnarla a qualsiasi gesto.
*Elimina registrate* le cancella.

**Registra sequenza…** – registra una serie di **tasti e click** da rieseguire con un gesto:
1. premi *Registra sequenza…* (la prima volta macOS può chiedere il permesso «Monitoraggio input»: concedilo);
2. esegui normalmente, in qualsiasi app, i tasti e i click che vuoi (fino a 200 passi): l'icona nella barra dei menu
   diventa ⏺ e il pulsante *Ferma registrazione* (o ✋ → *Ferma registrazione sequenza*) chiude la registrazione;
3. la sequenza compare nei menu come «Sequenza 1», «Sequenza 2»… e si assegna a un gesto.

Le pause tra un passo e l'altro vengono conservate (tra 0,05 e 3 secondi). I click vengono rifatti nelle stesse
**posizioni dello schermo**: se la finestra si sposta, il click cade altrove. Durante l'esecuzione il cursore non
segue la mano. Non vengono registrati i trascinamenti né le rotelle. Fino a 6 sequenze; *Elimina sequenze* le cancella. Alcune combinazioni riservate dal sistema (es. Cmd+Tab) non si possono registrare
premendole: usa l'azione già pronta.

**Generale**
- *Webcam*: scegli quale usare (anche una esterna o l'iPhone); il cambio è immediato e il nome della webcam
  in uso compare in basso a sinistra nell'anteprima. L'app apre il dispositivo scelto direttamente (AVFoundation).
- *Mani*: con **due mani** una controlla cursore e click, l'altra i gesti-azione (tre dita, indice + mignolo).
  Utile per non far partire azioni per sbaglio mentre punti. Scegli se il cursore va alla mano destra o sinistra.
- *Permessi*: mostra se Fotocamera e Accessibilità sono attive, con scorciatoie per aprire le Impostazioni di Sistema.

**Parametri** – sensibilità, smoothing, soglie del pizzico, tempi, scroll, attesa e pausa dei gesti a posa si
regolano con gli slider e hanno effetto subito. Si salvano da soli in
`~/Library/Application Support/Hand Gesture Mouse/settings.json` e vengono ricaricati all'avvio;
*Ripristina predefiniti* torna ai valori del blocco `CONFIG`.

### Swipe con la mano aperta

Con la **mano del mouse aperta** (tutte le dita alzate) spostala **a sinistra** o **a destra**: parte l'azione che
hai scelto per quella direzione (scheda *Movimenti*, in cima: «Mano aperta → sinistra» e «→ destra»). Con una mano
vale per l'unica mano, con due mani per la mano del cursore (aperta, il cursore resta fermo). Si vede come in uno
specchio: «sinistra» è la tua sinistra. Alzare o abbassare la mano aperta continua a regolare il volume.

- La mano deve essere aperta da almeno un quarto di secondo; poi basta un movimento rapido di circa un palmo.
- Dopo uno swipe c'è una pausa (1 s di default): così il ritorno della mano non conta come uno swipe opposto.
- *Parametri → Swipe: distanza minima* (più basso = basta un movimento più corto) e *pausa tra due swipe*.
- Se per una direzione l'azione è «Nessuna azione», quel movimento resta libero per i movimenti registrati.
- Le azioni sono vuote di default: assegna tu cosa devono fare.

### Volume, movimenti registrati e chiamate

**Volume con la mano aperta.** Tieni la mano aperta (tutte le dita alzate) ferma per mezzo secondo: l'app «si
aggancia». Poi alza la mano per alzare il volume e abbassala per abbassarlo: ogni scatto è un tasto volume, come
sulla tastiera (di default ogni 5% dell'altezza dell'inquadratura, regolabile in *Parametri*). In modalità due mani
vale per la mano libera. Si spegne da *Generale → Volume con la mano aperta*.

**Movimenti registrati** (scheda *Movimenti*). Registri un gesto fatto *muovendo* la mano, per esempio uno swipe
a destra, e gli colleghi un'azione:
1. scegli la posa che userai (una mano: **mano aperta**, tre dita, indice + mignolo o solo mignolo; due mani:
   qualsiasi posa della mano libera) e mostrala alla webcam. Un saluto sinistra-destra con la mano aperta va
   benissimo: il volume risponde solo ai movimenti su/giù e ignora quelli orizzontali;
2. premi *Registra movimento…*: parte un conto alla rovescia di 3 secondi, poi hai 2,5 secondi per fare il movimento;
3. scegli l'azione dal menu accanto a «Movimento 1» (fino a 6 movimenti).

Durante la registrazione l'app segue il punto della mano che si muove di più (nocche, punte delle dita, polso o
centro): così funziona sia per uno swipe sia per un saluto fatto dal polso. Un segnale sonoro scandisce il conto
alla rovescia («Pop» ogni secondo), l'inizio («Tink») e la fine («Glass» riuscito, «Basso» fallito); nel log
(`Registrazione movimento: ...`) trovi quanto si è mosso ogni punto.

Si riconosce quando rifai lo stesso movimento con la stessa posa, anche in un altro punto e a velocità diversa, ma
non il movimento contrario né uno diverso (per esempio verticale invece che orizzontale). *Movimenti → tolleranza*
in *Parametri* regola quanto devono assomigliare. Mentre fai un movimento l'azione «tenuta ferma» della stessa
posa non parte. Il movimento registrato vale per la posa e il numero di mani con cui l'hai fatto.

**Rispondere alle chiamate.** Funziona con qualsiasi app, registrando dove si trova il pulsante:
1. fai comparire la notifica di chiamata (una chiamata di prova, o chiedi a qualcuno di chiamarti);
2. in *Generale → Chiamate* premi *Registra click «Rispondi»*, poi clicca sul pulsante Accetta/Rispondi della
   notifica; ripeti con *Registra click «Rifiuta»* se vuoi;
3. assegna «Rispondi chiamata» / «Rifiuta chiamata» a un gesto o a un movimento.

**Mignolo alzato = rispondi / chiudi.** Con il **solo mignolo alzato** (tenuto ~0,7 s) l'app risponde alla chiamata;
rifacendo lo stesso gesto **chiude** la chiamata (e poi di nuovo risponde, e così via). Servono i click registrati
«Rispondi» e «Chiudi» (in *Generale → Chiamate*): «Chiudi» è il pulsante rosso che compare dopo aver risposto. Il
«Rispondi/chiudi» si può assegnare anche ad altri gesti dal menu delle azioni. Attenzione: se il gesto è stato
fatto senza una chiamata in corso, il secondo click cade comunque nel punto registrato di «Chiudi».

Il click viene rifatto *nello stesso punto dello schermo*: funziona finché la notifica compare lì (di solito in alto
a destra). Su macOS la prima registrazione può chiedere il permesso «Monitoraggio input».

### Più monitor

Con "monitor successivo" la mano controlla quello schermo e il cursore salta al suo centro; i monitor
vengono scorsi da sinistra a destra e poi si ricomincia. Per aggiungere nuove azioni: voce in `ACTIONS` e,
se è una scorciatoia, in `SHORTCUTS`. Per un nuovo gesto a posa: `ACTION_GESTURES` e `_action_pose()`.

### Log

L'app scrive un log in `~/Library/Logs/Hand Gesture Mouse.log` (utile se qualcosa non parte).

## Regolazioni

Tutte le impostazioni sono nel blocco `CONFIG` in cima a `hand_mouse.py`:

- `SENSITIVITY`, `ACTIVE_MARGIN_X/Y` – quanto corre il cursore per ogni movimento della mano
- `SMOOTHING`, `DEADZONE_PX` – tremolio contro reattività
- `PINCH_START`, `PINCH_RELEASE`, `DRAG_HOLD_SEC` – sensazione del pizzico
- `CLICK_COOLDOWN_SEC`, `RIGHT_CLICK_COOLDOWN_SEC` – protezione dal doppio click involontario
- `SCROLL_SPEED`, `SCROLL_INVERT` – scrolling
- `CAMERA_INDEX`, `MODEL_COMPLEXITY`, `SHOW_PREVIEW`, `MENUBAR_ENABLED`

## Limitazioni

- Il cambio monitor sposta il cursore; non sposta le finestre da un monitor all'altro.
- Il tasto `Q` viene letto dalla finestra di anteprima, quindi quella finestra deve essere in primo piano; altrimenti usa Ctrl+C.
