; Inno Setup script for OVMS Manager
; Requires Inno Setup 6+ from https://jrsoftware.org/isinfo.php

#define AppName      "OVMS Manager"
#define AppVersion   "1.0.0"
#define AppPublisher "anzdev4life"
#define AppURL       "https://github.com/annguyen209/OVMS_GUI"
#define AppExeName   "OVMS Manager.exe"
#define BuildDir     "dist\OVMS Manager"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=dist\installer
OutputBaseFilename=OVMS_Manager_Setup_{#AppVersion}
SetupIconFile=assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "{cm:CreateDesktopIcon}";    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupentry";  Description: "Start OVMS Manager with Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";     Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Start with Windows (optional, matches app's own toggle)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#AppName}"; \
  ValueData: """{app}\{#AppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: startupentry

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "cmd.exe"; Parameters: "/c taskkill /f /im ""{#AppExeName}"""; Flags: runhidden

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  // Check for Windows 10+
  if not IsWin64 then begin
    MsgBox('OVMS Manager requires a 64-bit version of Windows 10 or later.', mbError, MB_OK);
    Result := False;
  end;
end;
