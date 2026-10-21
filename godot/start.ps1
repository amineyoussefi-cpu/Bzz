# Launch Godot on this machine, in its own window (the read-only simulation view).
# Usage (PowerShell, from the repository):  powershell -ExecutionPolicy Bypass -File .\godot\start.ps1
# Reads ..\.env if present. The backend (Docker or local) connects to it on GODOT_LISTEN:GODOT_PORT.
# Closing the window stops the simulation; run this script again to relaunch it (the backend reconnects by itself).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path ..\.env) {
    foreach ($line in Get-Content ..\.env) {
        if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$' -and $Matches[2] -ne '') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
        }
    }
}
function Get-Setting($name, $default) { if ([Environment]::GetEnvironmentVariable($name)) { [Environment]::GetEnvironmentVariable($name) } else { $default } }

$want = Get-Setting "GODOT_VERSION" "4.7.2"   # same version as the Docker image
$candidates = @()
if ($env:GODOT_BIN) { $candidates += $env:GODOT_BIN }
foreach ($name in "godot", "godot_console") {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
}
# winget and manual installs
$candidates += Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages", "$env:ProgramFiles", "$env:LOCALAPPDATA\Programs" `
    -Filter "Godot_v*_win64*.exe" -Recurse -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object FullName
$godot = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $godot) { throw "Godot introuvable : installez Godot $want (winget install GodotEngine.GodotEngine) ou definissez GODOT_BIN dans .env." }

# the console build prints the version; the GUI build may not
$console = $godot -replace '\.exe$', '_console.exe' -replace '_console_console', '_console'
$probe = if (Test-Path $console) { $console } else { $godot }
$version = (& $probe --version | Select-Object -First 1)
if (-not ("$version".StartsWith("$want."))) { throw "Godot '$version' trouve ($godot), mais $want est attendu (GODOT_VERSION)." }

if (-not (Test-Path .godot\global_script_class_cache.cfg)) { & $probe --headless --path . --import | Out-Null }

$godotArgs = @("--host=$(Get-Setting 'GODOT_LISTEN' '127.0.0.1')", "--port=$(Get-Setting 'GODOT_PORT' '9876')",
          "--dashboard-url=http://localhost:$(Get-Setting 'DASHBOARD_PORT' '8000')")
$flags = @{ WORLD_WIDTH = "world-width"; WORLD_HEIGHT = "world-height"; DAY_TICKS = "day-ticks";
            FLIGHT_SPEED_FACTOR = "flight-speed-factor"; SWARM_SPEED_MPS = "swarm-speed-mps"; SWARM_CLUSTER_DAYS = "swarm-cluster-days" }
foreach ($var in $flags.Keys) {
    $value = [Environment]::GetEnvironmentVariable($var)
    if ($value) { $godotArgs += "--$($flags[$var])=$value" }
}
$display = if ((Get-Setting "GODOT_DISPLAY" "window") -eq "headless") { @("--headless") } else { @() }

Write-Host "Godot $version ($(Get-Setting 'GODOT_DISPLAY' 'window')) sur $(Get-Setting 'GODOT_LISTEN' '127.0.0.1'):$(Get-Setting 'GODOT_PORT' '9876')"
& $godot @display --path . -- @godotArgs
