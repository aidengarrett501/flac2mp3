; Optional. Builds a real Windows installer with Start Menu entry and uninstaller.
; Requires Inno Setup 6:  winget install -e --id JRSoftware.InnoSetup
; build.py runs this automatically if Inno Setup is present.

[Setup]
AppName=FLAC to MP3
AppVersion=1.0.0
AppPublisher=Aiden
DefaultDirName={autopf}\FLAC2MP3
DefaultGroupName=FLAC to MP3
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
OutputDir=dist
OutputBaseFilename=FLAC2MP3-Setup
SetupIconFile=flac2mp3.ico
UninstallDisplayIcon={app}\FLAC2MP3.exe
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\FLAC2MP3.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\FLAC to MP3"; Filename: "{app}\FLAC2MP3.exe"
Name: "{group}\Uninstall FLAC to MP3"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FLAC to MP3"; Filename: "{app}\FLAC2MP3.exe"

[Run]
Filename: "{app}\FLAC2MP3.exe"; Description: "Launch FLAC to MP3"; Flags: nowait postinstall skipifsilent
