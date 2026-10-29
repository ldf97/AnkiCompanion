#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif
[Setup]
AppId={{93883A05-5ED4-4148-8E69-B08808B188F8}
AppName=AnkiCompanion
AppVersion={#AppVersion}
AppPublisher=AnkiCompanion
DefaultDirName={localappdata}\Programs\AnkiCompanion
DefaultGroupName=AnkiCompanion
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\packages
OutputBaseFilename=AnkiCompanion-Windows-Setup
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=yes
UninstallDisplayIcon={app}\desktop\AnkiCompanion.exe
[Files]
Source: "..\dist\AnkiCompanion\*"; DestDir: "{app}\desktop"; Flags: recursesubdirs ignoreversion
Source: "..\dist\AnkiCompanionServer\*"; DestDir: "{app}\server"; Flags: recursesubdirs ignoreversion
Source: "..\deployment\*"; DestDir: "{app}\deployment"; Flags: recursesubdirs ignoreversion
Source: "..\packages\Anki_Companion_Bridge.ankiaddon"; DestDir: "{app}"
[Icons]
Name: "{group}\AnkiCompanion"; Filename: "{app}\desktop\AnkiCompanion.exe"
Name: "{group}\AnkiCompanion Server"; Filename: "{app}\server\AnkiCompanionServer.exe"
Name: "{group}\Connection instructions"; Filename: "{app}\deployment\CONNECT.md"
Name: "{group}\Uninstall"; Filename: "{uninstallexe}"
[Run]
Filename: "{app}\desktop\AnkiCompanion.exe"; Description: "Open AnkiCompanion"; Flags: nowait postinstall skipifsilent
; User data lives outside the installation folder and survives updates/uninstall.
