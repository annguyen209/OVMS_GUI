; Inno Setup script for OVMS Manager
; Requires Inno Setup 6+ from https://jrsoftware.org/isinfo.php

#define AppName      "OpenVINO Manager"
#define AppVersion   "1.0.0"
#define AppPublisher "AnsCodeLab"
#define AppURL       "https://github.com/AnsCodeLab/openvino-manager"
#define AppExeName   "OpenVINO Manager.exe"
#define BuildDir     "dist\OpenVINO Manager"

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
Name: "desktopicon";   Description: "{cm:CreateDesktopIcon}";      GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupentry";  Description: "Start OpenVINO Manager with Windows"; GroupDescription: "Startup:"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Deploy proxy script to the user data directory (onlyifdoesntexist so user edits survive reinstall)
Source: "ovms-proxy.py"; DestDir: "{localappdata}\OVMS Manager"; Flags: onlyifdoesntexist

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

; No [UninstallRun] needed — process termination is handled in Pascal
; CurUninstallStepChanged(usAppMutexCheck) runs before any file deletion.

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsWin64 then begin
    MsgBox('OpenVINO Manager requires a 64-bit version of Windows 10 or later.', mbError, MB_OK);
    Result := False;
  end;
end;

// ── Uninstall cleanup ────────────────────────────────────────────────────────

var
  UninstKeepConfig: Boolean;
  UninstKeepModels: Boolean;
  UninstLog: String;

procedure Log2(const Msg: String);
begin
  SaveStringToFile(UninstLog, Msg + Chr(13) + Chr(10), True);
end;

procedure RemoveDirIfExists(const Path: String);
begin
  Log2('RemoveDir: ' + Path);
  if DirExists(Path) then
  begin
    if DelTree(Path, True, True, True) then
      Log2('  OK')
    else
      Log2('  FAILED (files may be locked)');
  end else
    Log2('  (not found, skipping)');
end;

procedure KillProcessByName(const ExeName: String);
var
  ResultCode: Integer;
  i: Integer;
begin
  Log2('Kill: ' + ExeName);
  // Try up to 3 times in case the process is still starting up
  for i := 1 to 3 do
  begin
    Exec('cmd.exe', '/c taskkill /f /im "' + ExeName + '"', '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
    if ResultCode = 0 then break;
    Sleep(1000);
  end;
  Log2('  exit=' + IntToStr(ResultCode) + ' (0=killed, 128=not found)');
end;

procedure TryDeleteFile(const Path: String);
begin
  Log2('DeleteFile: ' + Path);
  if FileExists(Path) then
  begin
    if DeleteFile(Path) then
      Log2('  OK')
    else
      Log2('  FAILED');
  end else
    Log2('  (not found)');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  LocalAppData, ConfigDir, WorkspaceDir: String;
  Res: Integer;
begin
  // Use GetEnv so constants don't need to resolve during uninstall context
  if UninstLog = '' then
    UninstLog := GetEnv('USERPROFILE') + '\Desktop\OVMS_Manager_uninstall.log';

  Log2('[Step] ' + IntToStr(Ord(CurUninstallStep)));

  if CurUninstallStep = usUninstall then
  begin
    Log2('Killing processes...');
    KillProcessByName('{#AppExeName}');
    KillProcessByName('ovms.exe');
    Log2('Waiting 4s for file handles to release...');
    Sleep(4000);

    if UninstallSilent then
    begin
      Log2('Silent mode: keeping config and models');
      UninstKeepConfig := True;
      UninstKeepModels := True;
    end else
    begin
      Res := MsgBox(
        'Do you want to keep your personal settings (config) and downloaded models?' + Chr(13) + Chr(10) +
        Chr(13) + Chr(10) +
        'Click YES to keep config and models.' + Chr(13) + Chr(10) +
        'Click NO  to remove everything (clean uninstall).',
        mbConfirmation, MB_YESNO);
      UninstKeepConfig := (Res = IDYES);
      UninstKeepModels := (Res = IDYES);
      if UninstKeepConfig then Log2('KeepConfig=true') else Log2('KeepConfig=false');
      if UninstKeepModels then Log2('KeepModels=true') else Log2('KeepModels=false');
    end;
  end;

  if CurUninstallStep = usPostUninstall then
  begin
    Log2('PostUninstall begin');
    // Use GetEnv instead of ExpandConstant — more reliable in uninstall context
    LocalAppData := GetEnv('LOCALAPPDATA');
    ConfigDir    := LocalAppData + '\OVMS Manager';
    WorkspaceDir := GetEnv('USERPROFILE') + '\ovms-workspace';
    Log2('ConfigDir=' + ConfigDir);
    Log2('WorkspaceDir=' + WorkspaceDir);

    if not UninstKeepConfig then
      RemoveDirIfExists(ConfigDir)
    else
      Log2('Keeping config: ' + ConfigDir);

    if not UninstKeepModels then
      RemoveDirIfExists(WorkspaceDir)
    else
      Log2('Keeping workspace: ' + WorkspaceDir);

    TryDeleteFile(GetEnv('USERPROFILE') + '\ovms-gui.log');
    TryDeleteFile(GetEnv('USERPROFILE') + '\ovms-proxy-gui.log');

    Log2('Removing startup registry key...');
    if RegDeleteValue(HKEY_CURRENT_USER,
      'Software\Microsoft\Windows\CurrentVersion\Run', '{#AppName}') then
      Log2('  OK')
    else
      Log2('  not found or failed');

    Log2('Done.');
  end;
end;
