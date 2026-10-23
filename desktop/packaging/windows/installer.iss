; Установщик TG Panel для Windows (Inno Setup 6). Собирается из build.py:
;   ISCC /DAppVersion=… /DSourceDir=… /DOutputDir=… /DIconFile=… /DOutputName=… installer.iss
; Данные (аккаунты) — в %APPDATA%\TG Panel: обновление и удаление программы их не трогают.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E0B6C2A-3F4D-4E8B-9C1A-7D52A1F0B7E4}
AppName=TG Panel
AppVersion={#AppVersion}
AppVerName=TG Panel {#AppVersion}
AppPublisher=TG Panel
AppPublisherURL=https://github.com/Dosash/web_panel_acc
AppSupportURL=https://github.com/Dosash/web_panel_acc/issues
DefaultDirName={autopf}\TG Panel
DefaultGroupName=TG Panel
DisableProgramGroupPage=yes
; установка без прав администратора (в профиль пользователя); можно выбрать «для всех»
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\TG Panel.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
LicenseFile=..\..\..\LICENSE

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\TG Panel"; Filename: "{app}\TG Panel.exe"
Name: "{autodesktop}\TG Panel"; Filename: "{app}\TG Panel.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TG Panel.exe"; Description: "{cm:LaunchProgram,TG Panel}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; убрать автозапуск, если его включали из трея
Filename: "{sys}\reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v ""TG Panel"" /f"; Flags: runhidden; RunOnceId: "RemoveAutostart"
