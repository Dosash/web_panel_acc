; Установщик TG Panel для Windows (Inno Setup 6) — программа на Tauri + WebView2 из desktop-win. Собирается build.ps1:
;   ISCC /DAppVersion=… /DSourceDir=… /DOutputDir=… /DIconFile=… /DOutputName=… /DWebView2Setup=… installer.iss
; AppId, папка и права — как у прежнего установщика (desktop/packaging/windows/installer.iss): новая версия ставится
; поверх программы на PyQt5 (её обновление запускает этот setup.exe с /SILENT) и убирает её _internal.
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
VersionInfoVersion={#AppVersion}
VersionInfoDescription=TG Panel — установщик
DefaultDirName={autopf}\TG Panel
DefaultGroupName=TG Panel
DisableProgramGroupPage=yes
; установка без прав администратора (в профиль пользователя); можно выбрать «для всех»
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; WebView2 — Windows 10 и новее
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\TG Panel.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; запущенную программу установщик закрывает сам (при /SILENT и /VERYSILENT — без вопросов)
CloseApplications=yes
RestartApplications=no
LicenseFile=..\LICENSE

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; программа на PyQt5 держала всё в _internal; серверную часть ставим заново целиком — файлы её прежних
; версий (например, dist-info старых пакетов) мешали бы новой
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\server"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; загрузчик WebView2 Runtime (Evergreen): ставится, только если WebView2 на компьютере нет
Source: "{#WebView2Setup}"; DestName: "MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy

[Icons]
; AppUserModelID — тот же, что задаёт программа: уведомления от имени «TG Panel»
Name: "{autoprograms}\TG Panel"; Filename: "{app}\TG Panel.exe"; AppUserModelID: "TGPanel.Desktop"
Name: "{autodesktop}\TG Panel"; Filename: "{app}\TG Panel.exe"; Tasks: desktopicon; AppUserModelID: "TGPanel.Desktop"

[Run]
Filename: "{app}\TG Panel.exe"; Description: "{cm:LaunchProgram,TG Panel}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; убрать автозапуск, если его включали из трея
Filename: "{sys}\reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v ""TG Panel"" /f"; Flags: runhidden; RunOnceId: "RemoveAutostart"

[Code]
const
  WebView2Key = '\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasVersion(Root: Integer; Key: String): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0');
end;

function WebView2Installed: Boolean;
begin
  Result := HasVersion(HKLM, 'SOFTWARE\WOW6432Node' + WebView2Key) or HasVersion(HKLM, 'SOFTWARE' + WebView2Key)
    or HasVersion(HKCU, 'Software' + WebView2Key);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if (CurStep = ssPostInstall) and not WebView2Installed then begin
    if not WizardSilent then
      WizardForm.StatusLabel.Caption := 'Установка Microsoft Edge WebView2 Runtime…';
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    // без прав администратора загрузчик ставит WebView2 для текущего пользователя
    if Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE,
            ewWaitUntilTerminated, Code) then
      Log(Format('WebView2: загрузчик завершился с кодом %d', [Code]))
    else
      Log('WebView2: загрузчик не запустился');
  end;
end;
