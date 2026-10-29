; Installatore Windows (Inno Setup). Si compila con: iscc /DAppVersion=1.0.3 installer_win.iss
; Prende la cartella creata da PyInstaller in dist\Hand Gesture Mouse e crea Hand-Gesture-Mouse-Windows-Setup.exe
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{9BFEA6E1-D3B2-4D78-9B61-F49E63C1D938}
AppName=Hand Gesture Mouse
AppVersion={#AppVersion}
AppPublisher=Francesco Argento
; installazione per l'utente corrente: non servono i permessi di amministratore
PrivilegesRequired=lowest
DefaultDirName={autopf}\Hand Gesture Mouse
DefaultGroupName=Hand Gesture Mouse
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=Hand-Gesture-Mouse-Windows-Setup
SetupIconFile=icons\AppIcon.ico
UninstallDisplayIcon={app}\Hand Gesture Mouse.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea un collegamento sul Desktop"; GroupDescription: "Collegamenti:"
Name: "startup"; Description: "Avvia Hand Gesture Mouse all'accesso a Windows"; GroupDescription: "Opzioni:"; Flags: unchecked

[Files]
Source: "dist\Hand Gesture Mouse\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Hand Gesture Mouse"; Filename: "{app}\Hand Gesture Mouse.exe"
Name: "{autodesktop}\Hand Gesture Mouse"; Filename: "{app}\Hand Gesture Mouse.exe"; Tasks: desktopicon
Name: "{userstartup}\Hand Gesture Mouse"; Filename: "{app}\Hand Gesture Mouse.exe"; Tasks: startup

[Run]
Filename: "{app}\Hand Gesture Mouse.exe"; Description: "Avvia Hand Gesture Mouse"; Flags: nowait postinstall skipifsilent
