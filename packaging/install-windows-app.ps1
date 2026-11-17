$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Vbs = Join-Path $Root "scripts\nfl-board.vbs"
$Ico = Join-Path $Root "assets\nfl-board.ico"
if (-not (Test-Path $Vbs)) { throw "Missing launcher: $Vbs" }

$Wsh = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath("Desktop")
$StartMenu = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"

function New-NflShortcut([string]$Path) {
    $sc = $Wsh.CreateShortcut($Path)
    $sc.TargetPath = (Join-Path $env:SystemRoot "System32\wscript.exe")
    $sc.Arguments = "//nologo `"$Vbs`""
    $sc.WorkingDirectory = $Root
    $sc.WindowStyle = 7
    $sc.Description = "Weekly NFL matchup board"
    if (Test-Path $Ico) { $sc.IconLocation = $Ico }
    $sc.Save()
}

New-NflShortcut (Join-Path $Desktop "NFL Board.lnk")
New-NflShortcut (Join-Path $StartMenu "NFL Board.lnk")
Write-Host "Shortcuts ready: Desktop and Start Menu -> NFL Board"
