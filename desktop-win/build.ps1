<#
Сборка TG Panel для Windows (desktop-win) одной командой:

    powershell -ExecutionPolicy Bypass -File desktop-win\build.ps1

Нужны: Rust (stable-x86_64-pc-windows-msvc) с Visual Studio Build Tools (C++), Tauri CLI 2 (cargo tauri),
Python 3.12, Inno Setup 6. Результат — в desktop-win\release\:
    TG-Panel-<версия>-windows-x64-setup.exe     установщик (Inno Setup, тот же AppId, что у прежней программы)
    TG-Panel-<версия>-windows-x64-portable.zip  переносная версия: папка «TG Panel» с portable.txt
    TG-Panel-<версия>-SHA256SUMS.txt            контрольные суммы — по ним программа проверяет обновление
Версия — VERSION из app\config.py.

-Python <путь>  Python 3.12 для серверной части. По умолчанию — desktop-win\.venv (создаётся через py -3.12),
                в CI (переменная CI) — python из PATH.
#>
param([string]$Python = "")

$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$Root = Split-Path $Here
$Build = Join-Path $Here "build"
$Release = Join-Path $Here "release"
$Version = (Select-String -Path "$Root\app\config.py" -Pattern '^VERSION = "([^"]+)"').Matches[0].Groups[1].Value
$Name = "TG-Panel-$Version-windows-x64"
# консоль Windows не в UTF-8 — русский вывод Python и cargo иначе превращается в кракозябры
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Run([string]$exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "$exe $($arguments -join ' ') — код $LASTEXITCODE" }
}
function Find-Iscc {
    $cmd = Get-Command ISCC -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, "$env:LOCALAPPDATA\Programs")) {
        if ($base -and (Test-Path "$base\Inno Setup 6\ISCC.exe")) { return "$base\Inno Setup 6\ISCC.exe" }
    }
    throw "Inno Setup 6 не найден (winget install JRSoftware.InnoSetup)"
}
function Size($path) {
    $bytes = if ((Get-Item $path).PSIsContainer) { (Get-ChildItem $path -Recurse -File | Measure-Object Length -Sum).Sum } else { (Get-Item $path).Length }
    "{0:N1} МБ" -f ($bytes / 1MB)
}

Write-Host "TG Panel $Version для Windows (Tauri + WebView2)"
New-Item -ItemType Directory -Force $Build, $Release | Out-Null

Step "Python для серверной части"
if (-not $Python) {
    $venv = "$Here\.venv\Scripts\python.exe"
    if (Test-Path $venv) { $Python = $venv }
    elseif ($env:CI) { $Python = (Get-Command python).Source }
    else { Run py @("-3.12", "-m", "venv", "$Here\.venv"); $Python = $venv }
}
Run $Python @("-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", "$Here\server\requirements.txt")
& $Python --version

Step "Значки из desktop\icon.svg"
Push-Location "$Here\shell"
try { Run cargo @("tauri", "icon", "$Root\desktop\icon.svg", "-o", "icons") } finally { Pop-Location }
Remove-Item -Recurse -Force "$Here\shell\icons\android", "$Here\shell\icons\ios" -ErrorAction SilentlyContinue
Copy-Item "$Here\shell\icons\icon.ico" "$Build\icon.ico" -Force

Step "Сведения о версии серверной части"
$nums = (@([regex]::Matches($Version, '\d+') | ForEach-Object { $_.Value }) + @(0, 0, 0, 0))[0..3] -join ", "
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($nums), prodvers=($nums), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041904B0', [
      StringStruct('CompanyName', 'TG Panel'),
      StringStruct('FileDescription', 'TG Panel — серверная часть'),
      StringStruct('FileVersion', '$Version'),
      StringStruct('InternalName', 'tg-panel-server'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'tg-panel-server.exe'),
      StringStruct('ProductName', 'TG Panel'),
      StringStruct('ProductVersion', '$Version')])]),
    VarFileInfo([VarStruct('Translation', [1049, 1200])])
  ]
)
"@ | Set-Content "$Build\server_version_info.txt" -Encoding UTF8

Step "Серверная часть (PyInstaller)"
Run $Python @("-m", "PyInstaller", "$Here\server\tg-panel-server.spec", "--noconfirm", "--clean",
              "--distpath", "$Build\dist", "--workpath", "$Build\pyinstaller")
$Server = "$Build\dist\tg-panel-server"
Step "Самопроверка серверной части: импорт панели и чтение tdata (QtCore)"
$check = Start-Process "$Server\tg-panel-server.exe" -ArgumentList "--self-test" -Wait -PassThru -NoNewWindow
if ($check.ExitCode -ne 0) { throw "tg-panel-server.exe --self-test — код $($check.ExitCode)" }
$qt = Get-ChildItem $Server -Recurse -File | Where-Object { $_.Name -match '^Qt5\w+\.dll$|WebEngine' } | ForEach-Object { $_.Name }
Write-Host "Qt в сборке: $($qt -join ', ')"

Step "Оболочка (cargo tauri build)"
Push-Location "$Here\shell"
try {
    $config = '{"version":"' + $Version + '"}'
    # без бандлеров Tauri: установщик делает Inno Setup
    Run cargo @("tauri", "build", "--no-bundle", "--ci", "--config", $config)
} finally { Pop-Location }
$ShellExe = "$Here\shell\target\release\tg-panel.exe"

Step "Папка программы"
$Stage = "$Build\TG Panel"
Remove-Item -Recurse -Force $Stage -ErrorAction SilentlyContinue
New-Item -ItemType Directory $Stage | Out-Null
Copy-Item $ShellExe "$Stage\TG Panel.exe"
Copy-Item -Recurse $Server "$Stage\server"

Step "Переносная версия: $Name-portable.zip"
$PortableRoot = "$Build\portable"
Remove-Item -Recurse -Force $PortableRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory $PortableRoot | Out-Null
Copy-Item -Recurse $Stage "$PortableRoot\TG Panel"
# с этим файлом данные хранятся рядом с программой (флешка), а не в %APPDATA%
[IO.File]::WriteAllText("$PortableRoot\TG Panel\portable.txt",
    "Данные TG Panel хранятся в папке data рядом с программой.`nУдалите этот файл, чтобы хранить их в %APPDATA%\TG Panel.`n",
    (New-Object Text.UTF8Encoding $false))
$Zip = "$Release\$Name-portable.zip"
Remove-Item $Zip -ErrorAction SilentlyContinue
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::Open($Zip, "Create")
try {
    # пути в архиве — через «/»: так их понимают и прежняя программа (Python zipfile), и новая
    Get-ChildItem "$PortableRoot\TG Panel" -Recurse -File | ForEach-Object {
        $entry = "TG Panel/" + $_.FullName.Substring("$PortableRoot\TG Panel\".Length).Replace('\', '/')
        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $_.FullName, $entry, "Optimal")
    }
} finally { $archive.Dispose() }

Step "Загрузчик WebView2 Runtime"
$WebView2 = "$Build\MicrosoftEdgeWebview2Setup.exe"
if (-not (Test-Path $WebView2)) {
    Invoke-WebRequest "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $WebView2 -UseBasicParsing
}

Step "Установщик: $Name-setup.exe"
Run (Find-Iscc) @("/Q", "/DAppVersion=$Version", "/DSourceDir=$Stage", "/DOutputDir=$Release",
                  "/DIconFile=$Build\icon.ico", "/DOutputName=$Name-setup", "/DWebView2Setup=$WebView2",
                  "$Here\installer.iss")

Step "Контрольные суммы"
$Sums = "$Release\TG-Panel-$Version-SHA256SUMS.txt"
$lines = foreach ($f in @("$Release\$Name-setup.exe", $Zip)) {
    "{0}  {1}" -f (Get-FileHash $f -Algorithm SHA256).Hash.ToLower(), (Split-Path $f -Leaf)
}
[IO.File]::WriteAllText($Sums, ($lines -join "`n") + "`n", (New-Object Text.UTF8Encoding $false))

Step "Готово"
Write-Host ("  оболочка TG Panel.exe        {0}" -f (Size "$Stage\TG Panel.exe"))
Write-Host ("  серверная часть server\      {0}" -f (Size "$Stage\server"))
Write-Host ("  папка программы              {0}" -f (Size $Stage))
foreach ($f in Get-ChildItem $Release -File | Where-Object { $_.Name -like "*$Version*" }) {
    Write-Host ("  {0,-48} {1}" -f $f.Name, (Size $f.FullName))
}
