#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Cloud DJ — Desktop Installer for Windows
    Turns any Windows machine into a LAN music server.
.DESCRIPTION
    Installs Cloud DJ on your Windows PC:
    - Python virtual environment with all dependencies
    - Windows Firewall rule for port 5050
    - Scheduled Task for auto-start on boot
    - LAN access URL printed at the end
.NOTES
    Run: powershell -ExecutionPolicy Bypass -File install.ps1
    Or right-click → "Run with PowerShell"
#>

$Host.UI.RawUI.WindowTitle = "Cloud DJ Installer"
$Port = if ($env:PORT) { $env:PORT } else { 5050 }
$InstallDir = "$env:USERPROFILE\cloud-dj"
$RepoUrl = "https://github.com/lgnrvz/cloud-dj.git"
$ServiceName = "CloudDJ"

function Write-Info  { Write-Host "[INFO]  $_" -ForegroundColor Cyan }
function Write-Ok    { Write-Host "[OK]    $_" -ForegroundColor Green }
function Write-Warn  { Write-Host "[WARN]  $_" -ForegroundColor Yellow }
function Write-Err   { Write-Host "[ERROR] $_" -ForegroundColor Red }

# ── Banner ──────────────────────────────────────────────────
Clear-Host
Write-Host @"

  ___ _                 _     ___ ___
 / __| |_   __ _ _ _  __| |  / __/ _ \
| (__| ' \ / _\` | ' \/ _\` | | (_| (_) |
 \___|_||_|\__,_|_||_\__,_|  \___\___/
  LAN Music Server Installer — Windows Edition

"@ -ForegroundColor Cyan

# ── Step 1: Check Windows version ───────────────────────────
$WinVer = [Environment]::OSVersion.Version
if ($WinVer.Major -lt 10) {
    Write-Err "Windows 10 or later required (detected: $($WinVer.Major).$($WinVer.Minor))"
    exit 1
}
Write-Ok "Windows $($WinVer.Major).$($WinVer.Minor) detected"

# ── Helper: Install via winget with visible output ──────────
function Install-WithWinget {
    param($Id, $DisplayName, $Url)
    
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Warn "winget not available. Install $DisplayName manually:"
        Write-Host "  $Url" -ForegroundColor Yellow
        return $false
    }
    
    Write-Info "Installing $DisplayName via winget (this may take a minute)..."
    
    # Accept source agreement upfront so it doesn't hang
    winget source update --accept-source-agreements 2>&1 | Out-Null
    
    $proc = Start-Process -FilePath winget -ArgumentList @(
        "install", "--id", $Id, "--silent",
        "--accept-package-agreements", "--accept-source-agreements"
    ) -NoNewWindow -Wait -PassThru
    
    if ($proc.ExitCode -eq 0) {
        Write-Ok "$DisplayName installed via winget"
        return $true
    } else {
        Write-Warn "winget exit code: $($proc.ExitCode) for $DisplayName"
        Write-Warn "Install manually: $Url"
        return $false
    }
}

# ── Helper: Refresh PATH from registry ─────────────────────
function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

# ── Step 2: Check/Install Python ────────────────────────────
Write-Info "Checking Python..."
$python = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }

if (-not $python) {
    $installed = Install-WithWinget -Id "Python.Python.3.11" -DisplayName "Python 3.11" -Url "https://python.org/downloads/"
    if ($installed) {
        Refresh-Path
        Start-Sleep -Seconds 3
        $python = Get-Command python -ErrorAction SilentlyContinue
    }
}
# Also check common install path directly (winget often puts it here)
if (-not $python) {
    $commonPaths = @(
        "$env:ProgramFiles\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python313\python.exe",
        "$env:LocalAppData\Programs\Python\Python311\python.exe",
        "$env:LocalAppData\Programs\Python\Python312\python.exe",
        "$env:LocalAppData\Programs\Python\Python313\python.exe"
    )
    foreach ($p in $commonPaths) {
        if (Test-Path $p) {
            $python = Get-Command $p -ErrorAction SilentlyContinue
            break
        }
    }
}
if (-not $python) {
    Write-Err "Python not found! Install Python 3.11+ from https://python.org/downloads/"
    Write-Host "  Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Yellow
    Write-Host "  Then re-run this installer." -ForegroundColor Yellow
    exit 1
}
Write-Ok "Python: $($python.Source)"

# ── Step 3: Check/Install Node.js ───────────────────────────
Write-Info "Checking Node.js..."
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    $installed = Install-WithWinget -Id "OpenJS.NodeJS.LTS" -DisplayName "Node.js LTS" -Url "https://nodejs.org"
    if ($installed) {
        Refresh-Path
        Start-Sleep -Seconds 3
        $node = Get-Command node -ErrorAction SilentlyContinue
    }
}
if (-not $node) {
    # Try common install paths
    $commonNodePaths = @(
        "$env:ProgramFiles\nodejs\node.exe",
        "${env:ProgramFiles(x86)}\nodejs\node.exe"
    )
    foreach ($p in $commonNodePaths) {
        if (Test-Path $p) {
            $node = Get-Command $p -ErrorAction SilentlyContinue
            break
        }
    }
}
if ($node) {
    Write-Ok "Node.js: $($node.Source)"
} else {
    Write-Warn "Node.js not found — yt-dlp will use slower Python JS runtime"
    Write-Warn "Install from https://nodejs.org for better performance"
}

# ── Step 4: Check/Install ffmpeg ────────────────────────────
Write-Info "Checking ffmpeg..."
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    $installed = Install-WithWinget -Id "Gyan.FFmpeg" -DisplayName "ffmpeg" -Url "https://ffmpeg.org/download.html"
    if ($installed) {
        Refresh-Path
        Start-Sleep -Seconds 3
        $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
    }
}
if ($ffmpeg) {
    Write-Ok "ffmpeg: $($ffmpeg.Source)"
} else {
    Write-Warn "ffmpeg not found — some yt-dlp formats may not work"
    Write-Warn "Install from https://ffmpeg.org/download.html"
}

# ── Step 5: Install yt-dlp via pip ──────────────────────────
Write-Info "Installing yt-dlp (system-wide via pip)..."
try {
    & $python.Source -m pip install --user yt-dlp --quiet 2>&1 | Out-Null
    # Refresh PATH — yt-dlp might be in AppData\Roaming\Python\Scripts
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    Write-Ok "yt-dlp installed"
} catch {
    Write-Warn "pip install yt-dlp failed — will install in venv instead"
}

# ── Step 6: Clone / Pull the repo ───────────────────────────
Write-Info "Setting up application..."

if (Test-Path "$InstallDir") {
    if (Test-Path "$InstallDir\.git") {
        Write-Info "Updating existing installation..."
        Push-Location "$InstallDir"
        git pull --ff-only 2>&1 | Out-Null
        Pop-Location
        Write-Ok "Repository updated"
    } else {
        Write-Warn "$InstallDir exists but isn't a git repo. Removing and re-cloning..."
        Remove-Item -Recurse -Force "$InstallDir"
        git clone $RepoUrl "$InstallDir" 2>&1 | Out-Null
        Write-Ok "Repository cloned"
    }
} else {
    Write-Info "Cloning Cloud DJ to $InstallDir..."
    git clone $RepoUrl "$InstallDir" 2>&1 | Out-Null
    Write-Ok "Repository cloned"
}

Set-Location "$InstallDir"

# ── Step 7: Create Virtual Environment ──────────────────────
Write-Info "Setting up Python virtual environment..."
if (-not (Test-Path ".venv")) {
    & $python.Source -m venv .venv
    Write-Ok "Virtual environment created"
} else {
    Write-Ok "Virtual environment already exists"
}

Write-Info "Installing Python dependencies..."
& ".venv\Scripts\pip" install --upgrade pip --quiet 2>&1 | Out-Null
& ".venv\Scripts\pip" install -r requirements.txt --quiet 2>&1 | Out-Null
& ".venv\Scripts\pip" install yt-dlp --quiet 2>&1 | Out-Null
Write-Ok "Python dependencies installed"

# ── Step 8: Verify paths ────────────────────────────────────
Write-Info "Verifying paths..."
$venvYtdlp = Join-Path (Get-Location) ".venv\Scripts\yt-dlp.exe"
if (Test-Path $venvYtdlp) {
    Write-Ok "Venv yt-dlp: $venvYtdlp"
} else {
    # yt-dlp might be yt-dlp.exe or just yt-dlp (pip installs scripts)
    $venvScripts = Join-Path (Get-Location) ".venv\Scripts"
    $found = Get-ChildItem "$venvScripts\yt-dlp*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        Write-Ok "Venv yt-dlp: $($found.FullName)"
    } else {
        Write-Warn "yt-dlp not found in venv — will install it now"
        & ".venv\Scripts\pip" install yt-dlp --quiet 2>&1 | Out-Null
    }
}

Write-Ok "app.py paths are auto-detected (no manual config needed)"

# ── Step 9: Open Windows Firewall ──────────────────────────
Write-Info "Opening port $Port in Windows Firewall..."
$rule = Get-NetFirewallRule -DisplayName "Cloud DJ (TCP $Port)" -ErrorAction SilentlyContinue
if (-not $rule) {
    try {
        New-NetFirewallRule -DisplayName "Cloud DJ (TCP $Port)" `
            -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow `
            -Profile Private,Domain -ErrorAction Stop | Out-Null
        Write-Ok "Firewall rule created for port $Port"
    } catch {
        Write-Warn "Could not create firewall rule. Run this as Administrator or add manually:"
        Write-Host "  netsh advfirewall firewall add rule name=`"Cloud DJ`" dir=in action=allow protocol=TCP localport=$Port" -ForegroundColor Yellow
    }
} else {
    Write-Ok "Firewall rule already exists"
}

# ── Step 10: Create Scheduled Task for auto-start ──────────
Write-Info "Setting up auto-start via Task Scheduler..."
$existing = Get-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue
if (-not $existing) {
    try {
        $action = New-ScheduledTaskAction -Execute (Resolve-Path ".venv\Scripts\python.exe").Path `
            -Argument "app.py" -WorkingDirectory (Get-Location).Path
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

        Register-ScheduledTask -TaskName $ServiceName -Action $action -Trigger $trigger `
            -Settings $settings -Principal $principal -Force | Out-Null
        Write-Ok "Scheduled Task '$ServiceName' created (starts on boot)"
    } catch {
        Write-Warn "Could not create Scheduled Task. Run as Administrator or set up manually."
        Write-Warn "To auto-start manually: add a shortcut to '.venv\Scripts\python.exe app.py'"
        Write-Host "  in shell:startup" -ForegroundColor Yellow
    }
} else {
    Write-Ok "Scheduled Task '$ServiceName' already exists"
}

# ── Step 11: Generate a startup script (fallback) ──────────
$batContent = @"
@echo off
cd /d "$InstallDir"
start /min "" ".venv\Scripts\python.exe" "app.py"
"@
Set-Content -Path "$InstallDir\start-cloud-dj.bat" -Value $batContent
Write-Ok "Startup script created: $InstallDir\start-cloud-dj.bat"

# ── Step 12: Start the server ──────────────────────────────
# Check if something is already listening on our port
$portInUse = $false
try {
    $listener = [System.Net.Sockets.TcpClient]::new()
    $listener.ConnectAsync("127.0.0.1", $Port).Wait(1000) | Out-Null
    $portInUse = $listener.Connected
    $listener.Close()
} catch { }
if (-not $portInUse) {
    Write-Info "Starting Cloud DJ server..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = (Resolve-Path ".venv\Scripts\python.exe").Path
    $psi.Arguments = "app.py"
    $psi.WorkingDirectory = (Get-Location).Path
    $psi.UseShellExecute = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Minimized
    $proc = [System.Diagnostics.Process]::Start($psi)
    Write-Ok "Server started (PID: $($proc.Id))"
} else {
    Write-Ok "Server is already running"
}

# ── Step 13: Wait and verify ───────────────────────────────
Write-Info "Verifying server..."
Start-Sleep -Seconds 4

try {
    $response = Invoke-WebRequest -Uri "http://localhost:$Port" -TimeoutSec 5 -UseBasicParsing
    if ($response.StatusCode -eq 200 -or $response.StatusCode -eq 302) {
        Write-Ok "Server is responding on http://localhost:$Port"
    }
} catch {
    Write-Warn "Server may not be ready yet. Check log file: $InstallDir\server.log"
}

# ── Step 14: Get LAN IP ────────────────────────────────────
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -like "192.*" -or $_.IPAddress -like "10.*" -or ($_.IPAddress -like "172.*" -and $_.IPAddress -like "172.1[6-9].*")
}).IPAddress | Select-Object -First 1
if (-not $lanIp) { $lanIp = "localhost" }

# ── Done ───────────────────────────────────────────────────
$splat = @{
    Object = @(
        [PSCustomObject]@{ Key = "Local access"; Value = "http://localhost:$Port" }
        [PSCustomObject]@{ Key = "LAN access";   Value = "http://${lanIp}:$Port" }
        [PSCustomObject]@{ Key = "Admin user";   Value = "admin" }
        [PSCustomObject]@{ Key = "Admin pass";   Value = "djadmin123" }
        [PSCustomObject]@{ Key = "Install dir";  Value = $InstallDir }
        [PSCustomObject]@{ Key = "Start script"; Value = "$InstallDir\start-cloud-dj.bat" }
    )
}
Write-Host @"

╔══════════════════════════════════════════════════════════╗
║              INSTALLATION COMPLETE!                      ║
╚══════════════════════════════════════════════════════════╝

"@ -ForegroundColor Green
$splat.Object | Format-Table -HideTableHeaders -AutoSize -Wrap

Write-Host @"

  Other devices on your network open:
  http://${lanIp}:$Port

  Commands:
    Start:            $InstallDir\start-cloud-dj.bat
    Stop:             Task Manager → End "Python" process
    Auto-start:       Windows → Task Scheduler → Task Scheduler Library → CloudDJ
    View logs:        $InstallDir\server.log
    Restart server:   Stop the process, then run start-cloud-dj.bat

  Change port:
    \$env:PORT=9090; powershell -File install.ps1

Happy spinning! 🎧

"@ -ForegroundColor Cyan
