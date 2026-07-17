#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Cloud-DJ — Desktop Installer for Windows
    Turns any Windows machine into a LAN music server.
.DESCRIPTION
    Installs Cloud-DJ on your Windows PC:
    - Python virtual environment with all dependencies
    - Windows Firewall rule for port 5050
    - Scheduled Task for auto-start on boot
    - LAN access URL printed at the end
.NOTES
    Run: powershell -ExecutionPolicy Bypass -File install.ps1
    Or right-click → "Run with PowerShell"
#>

$Host.UI.RawUI.WindowTitle = "Cloud-DJ Installer"
$Port = if ($env:PORT) { $env:PORT } else { 5050 }
$InstallDir = "$env:USERPROFILE\cloud-dj"
$RepoUrl = "https://github.com/lgnrvz/cloud-dj.git"
$ServiceName = "CloudDJ"
$AllOk = $true  # Tracks if everything succeeded

function Write-Info  { Write-Host "[INFO]  $_" -ForegroundColor Cyan }
function Write-Ok    { Write-Host "[OK]    $_" -ForegroundColor Green }
function Write-Warn  { Write-Host "[WARN]  $_" -ForegroundColor Yellow }
function Write-Err   { Write-Host "[ERROR] $_" -ForegroundColor Red; $script:AllOk = $false }

# Quick-check: does a command exist (not the Microsoft Store stub)?
function Test-RealCommand {
    param($Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    # On Windows 10/11, the Microsoft Store python stub is a 0-byte exe in
    # %LOCALAPPDATA%\Microsoft\WindowsApps that just opens the Store.
    # Real Python lives elsewhere. Skip it if it's from WindowsApps.
    $source = $cmd.Source
    if ($source -and $source -like "*WindowsApps*") {
        return $null  # This is the Store stub, ignore it
    }
    # Make sure it actually runs
    try {
        $result = & $source --version 2>&1 | Out-String
        if ($result -match "\d+\.\d+") {
            return $cmd
        }
    } catch { }
    return $null
}

# Install via winget with visible output
function Install-WithWinget {
    param($Id, $DisplayName, $Url)

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Warn "winget not available. Install $DisplayName manually:"
        Write-Host "  $Url" -ForegroundColor Yellow
        return $false
    }

    Write-Info "Installing $DisplayName via winget (this may take a minute)..."
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

# Refresh PATH from registry so newly-installed tools are found
function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

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

# ── Step 2: Check/Install Git ───────────────────────────────
Write-Info "Checking Git..."
$git = Test-RealCommand "git"
if (-not $git) {
    $installed = Install-WithWinget -Id "Git.Git" -DisplayName "Git" -Url "https://git-scm.com/download/win"
    if ($installed) {
        Refresh-Path
        Start-Sleep -Seconds 3
        $git = Test-RealCommand "git"
    }
}
if ($git) {
    Write-Ok "Git: $($git.Source)"
} else {
    Write-Err "Git is required. Install from https://git-scm.com/download/win then re-run."
    exit 1
}

# ── Step 3: Check/Install Python ────────────────────────────
Write-Info "Checking Python..."
$python = Test-RealCommand "python3"
if (-not $python) { $python = Test-RealCommand "python" }

if (-not $python) {
    $installed = Install-WithWinget -Id "Python.Python.3.11" -DisplayName "Python 3.11" -Url "https://python.org/downloads/"
    if ($installed) {
        Refresh-Path
        Start-Sleep -Seconds 4
        $python = Test-RealCommand "python"
    }
}
# Also check common install paths directly (winget often puts it here)
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
            try {
                $ver = & $p --version 2>&1
                if ($ver -match "\d+\.\d+") {
                    $python = Get-Command $p
                    break
                }
            } catch { }
        }
    }
}
if (-not $python) {
    Write-Err "Python not found!"
    Write-Host "  1. Download Python from: https://python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  2. Run the installer — CHECK 'Add Python to PATH'" -ForegroundColor Yellow
    Write-Host "  3. RESTART PowerShell, then run this installer again" -ForegroundColor Yellow
    exit 1
}
Write-Ok "Python: $($python.Source)"

# ── Step 4: Check/Install Node.js ───────────────────────────
Write-Info "Checking Node.js..."
$node = Test-RealCommand "node"
if (-not $node) {
    $installed = Install-WithWinget -Id "OpenJS.NodeJS.LTS" -DisplayName "Node.js LTS" -Url "https://nodejs.org"
    if ($installed) {
        Refresh-Path
        Start-Sleep -Seconds 3
        $node = Test-RealCommand "node"
    }
}
if (-not $node) {
    $commonNodePaths = @(
        "$env:ProgramFiles\nodejs\node.exe",
        "${env:ProgramFiles(x86)}\nodejs\node.exe"
    )
    foreach ($p in $commonNodePaths) {
        if (Test-Path $p) { $node = Get-Command $p; break }
    }
}
if ($node) {
    Write-Ok "Node.js: $($node.Source)"
} else {
    Write-Warn "Node.js not found — yt-dlp will use slower Python JS runtime"
    Write-Warn "Install from https://nodejs.org for better performance"
}

# ── Step 5: Check/Install ffmpeg ────────────────────────────
Write-Info "Checking ffmpeg..."
$ffmpeg = Test-RealCommand "ffmpeg"
if (-not $ffmpeg) {
    $installed = Install-WithWinget -Id "Gyan.FFmpeg" -DisplayName "ffmpeg" -Url "https://ffmpeg.org/download.html"
    if ($installed) {
        Refresh-Path
        Start-Sleep -Seconds 3
        $ffmpeg = Test-RealCommand "ffmpeg"
    }
}
if ($ffmpeg) {
    Write-Ok "ffmpeg: $($ffmpeg.Source)"
} else {
    Write-Warn "ffmpeg not found — some yt-dlp formats may not work"
    Write-Warn "Install from https://ffmpeg.org/download.html"
}

# ── Step 6: Clone / Pull the repo ───────────────────────────
Write-Info "Setting up application..."
if (Test-Path "$InstallDir\.git") {
    Push-Location "$InstallDir"
    git pull --ff-only 2>&1 | Out-Null
    Pop-Location
    Write-Ok "Repository updated"
} else {
    if (Test-Path "$InstallDir") {
        Remove-Item -Recurse -Force "$InstallDir"
    }
    Write-Info "Cloning Cloud-DJ to $InstallDir..."
    git clone $RepoUrl "$InstallDir" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to clone repository. Check your internet connection."
        exit 1
    }
    Write-Ok "Repository cloned"
}

Set-Location "$InstallDir"

# ── Step 7: Create Virtual Environment ──────────────────────
Write-Info "Setting up Python virtual environment..."
if (-not (Test-Path ".venv")) {
    & $python.Source -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create virtual environment. Is Python installed properly?"
        exit 1
    }
    Write-Ok "Virtual environment created"
} else {
    Write-Ok "Virtual environment already exists"
}

# Define pip path — use .exe extension to avoid PowerShell module-resolution nonsense
$pipExe = Join-Path (Get-Location) ".venv\Scripts\pip.exe"
if (-not (Test-Path $pipExe)) {
    # Fallback: pip might be pip3.exe
    $pipExe = Join-Path (Get-Location) ".venv\Scripts\pip3.exe"
}
if (-not (Test-Path $pipExe)) {
    Write-Err "pip not found in virtual environment (.venv\Scripts\pip.exe)"
    exit 1
}

Write-Info "Installing Python dependencies..."
& $pipExe install --upgrade pip --quiet 2>&1 | Out-Null
& $pipExe install -r requirements.txt --quiet 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warn "pip install had issues — retrying with verbose output..."
    & $pipExe install -r requirements.txt 2>&1
}
& $pipExe install yt-dlp --quiet 2>&1 | Out-Null
Write-Ok "Python dependencies installed"

# ── Step 8: Verify venv paths ──────────────────────────────
$venvPython = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Err "Virtual environment is broken — missing python.exe in .venv\Scripts"
    exit 1
}
$venvYtdlp = Join-Path (Get-Location) ".venv\Scripts\yt-dlp.exe"
if (-not (Test-Path $venvYtdlp)) {
    $found = Get-ChildItem (Join-Path (Get-Location) ".venv\Scripts\yt-dlp*") -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $venvYtdlp = $found.FullName
    } else {
        Write-Warn "yt-dlp not found in venv — installing now"
        & $pipExe install yt-dlp 2>&1 | Out-Null
    }
}
Write-Ok "Venv Python: $venvPython"
Write-Ok "app.py auto-detects yt-dlp and node (no manual config needed)"

# ── Step 9: Open Windows Firewall ──────────────────────────
Write-Info "Opening port $Port in Windows Firewall..."
try {
    $rule = Get-NetFirewallRule -DisplayName "Cloud-DJ (TCP $Port)" -ErrorAction SilentlyContinue
    if (-not $rule) {
        New-NetFirewallRule -DisplayName "Cloud-DJ (TCP $Port)" `
            -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow `
            -Profile Private,Domain -ErrorAction Stop | Out-Null
        Write-Ok "Firewall rule created for port $Port"
    } else {
        Write-Ok "Firewall rule already exists"
    }
} catch {
    Write-Warn "Could not create firewall rule. To add manually:"
    Write-Host "  netsh advfirewall firewall add rule name=`"Cloud-DJ`" dir=in action=allow protocol=TCP localport=$Port" -ForegroundColor Yellow
}

# ── Step 10: Create Scheduled Task for auto-start ──────────
Write-Info "Setting up auto-start via Task Scheduler..."
try {
    $existing = Get-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue
    if (-not $existing) {
        $action = New-ScheduledTaskAction -Execute $venvPython `
            -Argument "app.py" -WorkingDirectory (Get-Location).Path
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $ServiceName -Action $action -Trigger $trigger `
            -Settings $settings -Principal $principal -Force | Out-Null
        Write-Ok "Scheduled Task '$ServiceName' created (starts on boot)"
    } else {
        Write-Ok "Scheduled Task '$ServiceName' already exists"
    }
} catch {
    Write-Warn "Could not create Scheduled Task. Run as Administrator or set up manually."
    Write-Warn "To auto-start: add $InstallDir\start-cloud-dj.bat to shell:startup"
}

# ── Step 11: Generate startup script ───────────────────────
$batContent = @"
@echo off
cd /d "$InstallDir"
start /min "" "$venvPython" "app.py"
"@
Set-Content -Path "$InstallDir\start-cloud-dj.bat" -Value $batContent
Write-Ok "Startup script: $InstallDir\start-cloud-dj.bat"

# ── Step 12: Start the server ──────────────────────────────
$portInUse = $false
try {
    $listener = New-Object System.Net.Sockets.TcpClient
    $listener.ConnectAsync("127.0.0.1", $Port).Wait(1000) | Out-Null
    $portInUse = $listener.Connected
    $listener.Close()
} catch { }

if (-not $portInUse) {
    Write-Info "Starting Cloud-DJ server..."
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $venvPython
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
    Write-Warn "Server may not be ready yet. Try: http://localhost:$Port"
}

# ── Step 14: Get LAN IP ────────────────────────────────────
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -like "192.*" -or $_.IPAddress -like "10.*" -or ($_.IPAddress -like "172.*" -and $_.IPAddress -like "172.1[6-9].*")
}).IPAddress | Select-Object -First 1
if (-not $lanIp) { $lanIp = "localhost" }

# ── Done ───────────────────────────────────────────────────
Write-Host @"

========================================================
             INSTALLATION COMPLETE!
========================================================

"@ -ForegroundColor Green

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
$splat.Object | Format-Table -HideTableHeaders -AutoSize -Wrap

Write-Host @"

  Other devices on your network open:
  http://${lanIp}:$Port

  Commands:
    Start:            $InstallDir\start-cloud-dj.bat
    Stop:             Task Manager - End "Python" process
    Auto-start:       Task Scheduler - Task Scheduler Library - CloudDJ
    Restart server:   Stop the process, then run start-cloud-dj.bat

  Change port:
    `$env:PORT=9090; powershell -File install.ps1

Happy spinning! 🎧

"@ -ForegroundColor Cyan
