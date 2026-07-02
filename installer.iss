; Inno Setup script — produces PhotoStudio-Setup.exe
; Requires Inno Setup 6 (https://jrsoftware.org/isinfo.php) and a prior
; PyInstaller build (run build.bat first).

[Setup]
AppName=Photo Studio by Asad
AppVersion=1.0.0
AppPublisher=Ali Asad
AppCopyright=Copyright (C) 2026 Ali Asad. All rights reserved.
DefaultDirName={autopf}\Photo Studio by Asad
DefaultGroupName=Photo Studio by Asad
OutputBaseFilename=PhotoStudio-Setup
OutputDir=installer_output
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoCompany=Ali Asad
VersionInfoCopyright=Copyright (C) 2026 Ali Asad. All rights reserved.
VersionInfoProductName=Photo Studio by Asad

[Files]
Source: "dist\PhotoStudio\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Photo Studio by Asad"; Filename: "{app}\PhotoStudio.exe"
Name: "{autodesktop}\Photo Studio by Asad"; Filename: "{app}\PhotoStudio.exe"

[Run]
Filename: "{app}\PhotoStudio.exe"; Description: "Launch Photo Studio by Asad"; Flags: nowait postinstall skipifsilent
