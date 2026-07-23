#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Cloud-DJ — Desktop Installer for Windows
    Fully automatic — installs everything needed.
.DESCRIPTION
    Installs Cloud-DJ on your Windows PC:
    - Auto-downloads & installs Python, Git, Node.js, ffmpeg, yt-dlp if missing
    - Python virtual environment with all dependencies
    - Windows Firewall rule for port 5050
    - Scheduled Task for auto-start on boot
    - LAN access URL printed at the end
.NOTES
    Run: powershell -ExecutionPolicy Bypass -File install.ps1
    Or right-click -> "Run with PowerShell"
#>

$Host.UI.RawUI.WindowTitle = "Cloud-DJ Installer"
$Port = if ($env:PORT) { $env:PORT } else { 5050 }
$InstallDir = "$env:USERPROFILE\cloud-dj"
$RepoUrl = "https://github.com/lgnrvz/cloud-dj.git"
$ServiceName = "CloudDJ"
$AllOk = $true

# Force TLS 1.2 — GitHub and python.org require it
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Info  { Write-Host "[INFO]  $_" -ForegroundColor Cyan }
function Write-Ok    { Write-Host "[OK]    $_" -ForegroundColor Green }
function Write-Warn  { Write-Host "[WARN]  $_" -ForegroundColor Yellow }
function Write-Err   { Write-Host "[ERROR] $_" -ForegroundColor Red; $script:AllOk = $false }

# Install via winget (preferred — works on locked-down networks)
function Install-WithWinget {
    param($Id, $DisplayName)

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Warn "winget not available for $DisplayName"
        return $false
    }

    Write-Info "Installing $DisplayName via winget..."
    winget source update --accept-source-agreements 2>&1 | Out-Null

    $proc = Start-Process -FilePath winget -ArgumentList @(
        "install", "--id", $Id, "--silent",
        "--accept-package-agreements", "--accept-source-agreements"
    ) -NoNewWindow -Wait -PassThru

    if ($proc.ExitCode -eq 0) {
        Refresh-Path
        Start-Sleep -Seconds 3
        Write-Ok "$DisplayName installed via winget"
        return $true
    } else {
        Write-Warn "winget exit code: $($proc.ExitCode) for $DisplayName"
        return $false
    }
}

# Check if a real command exists (NOT the Microsoft Store stub)
function Test-RealCommand {
    param($Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) { return $null }
    $source = $cmd.Source
    if ($source -and $source -like "*WindowsApps*") {
        return $null  # Microsoft Store stub — skip
    }
    # Verify it actually runs
    try { $ver = & $source --version 2>&1; if ($ver -match "\d+\.\d+") { return $cmd } } catch { }
    return $null
}

# Refresh PATH from registry
function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

# Download and silently install a tool
function Install-Direct {
    param(
        $Name,              # Display name
        $Url,               # Download URL
        $InstallerArgs,     # Silent install arguments
        $ExeName,           # What exe name to check after install
        [string[]]$FallbackPaths  # Where to look if not on PATH
    )

    Write-Info "Downloading $Name..."
    $tempDir = "$env:TEMP\cloud-dj-install"
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
    $installer = "$tempDir\$Name-installer.exe"

    try {
        # Force TLS 1.2 one more time (some PowerShell versions reset it)
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        # Download with progress bar
        Invoke-WebRequest -Uri $Url -OutFile $installer -UseBasicParsing
        $fileSize = (Get-Item $installer).Length
        if ($fileSize -lt 1MB) {
            throw "Downloaded file is too small ($([math]::Round($fileSize/1KB,0)) KB) — probably an error page"
        }
        Write-Ok "Downloaded $Name ($([math]::Round($fileSize / 1MB, 1)) MB)"
    } catch {
        Write-Warn "Direct download failed: $_"
        # Try via curl.exe if Invoke-WebRequest failed (common on locked-down Windows)
        if (Get-Command curl -ErrorAction SilentlyContinue) {
            Write-Info "Retrying with curl.exe..."
            curl.exe -L -o "$installer" "$Url" 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0 -and (Test-Path $installer)) {
                $fileSize = (Get-Item $installer).Length
                if ($fileSize -gt 1MB) {
                    Write-Ok "Downloaded $Name via curl ($([math]::Round($fileSize/1MB,1)) MB)"
                } else {
                    Write-Warn "curl download too small ($([math]::Round($fileSize/1KB,0)) KB) — likely an error page"
                    Write-Warn "Please install $Name manually: $(Split-Path $Url -Parent)"
                    return $false
                }
            } else {
                Write-Warn "curl download also failed."
                Write-Warn "Please install $Name manually: $(Split-Path $Url -Parent)"
                return $false
            }
        } else {
            Write-Warn "Please install $Name manually: $(Split-Path $Url -Parent)"
            return $false
        }
    }

    Write-Info "Installing $Name (silent)..."

    # For Python, make sure we pass install options
    if ($Name -eq "Python") {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $installer
        $psi.Arguments = $InstallerArgs
        $psi.UseShellExecute = $true  # Needed for admin elevation
        $psi.Verb = "runas"  # Request admin
        $proc = [System.Diagnostics.Process]::Start($psi)
        if (-not $proc) {
            Write-Warn "Could not start $Name installer. Try running PowerShell as Administrator."
            return $false
        }
        $proc.WaitForExit()
    } else {
        $proc = Start-Process -FilePath $installer -ArgumentList $InstallerArgs -Wait -PassThru
    }

    if ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne 1641 -and $proc.ExitCode -ne 3010) {
        Write-Warn "$Name installer exit code: $($proc.ExitCode) (may still have succeeded)"
    }

    # Refresh PATH and wait for install to settle
    Refresh-Path
    Start-Sleep -Seconds 4

    # Check if it worked
    $check = Test-RealCommand $ExeName
    if (-not $check -and $FallbackPaths) {
        foreach ($fp in $FallbackPaths) {
            if (Test-Path $fp) { $check = Get-Command $fp; break }
        }
    }
    if ($check) {
        Write-Ok "$Name installed"
        return $true
    } else {
        Write-Warn "$Name install may have failed. Try installing manually from $Url"
        return $false
    }
}

# ── Banner ──────────────────────────────────────────────────
Clear-Host
Write-Host @"
   ╔═══════════════════════════════╗
   ║  CLOUD-DJ                     ║
   ╚═══════════════════════════════╝
Cloud-DJ LAN Music Server Installer — Windows Edition
"@ -ForegroundColor Cyan

# ── Step 1: Check Windows version ───────────────────────────
$WinVer = [Environment]::OSVersion.Version
if ($WinVer.Major -lt 10) {
    Write-Err "Windows 10 or later required (detected: $($WinVer.Major).$($WinVer.Minor))"
    pause; exit 1
}
Write-Ok "Windows $($WinVer.Major).$($WinVer.Minor) detected"

# ── Step 2: Install Git ─────────────────────────────────────
Write-Info "Checking Git..."
$git = Test-RealCommand "git"
if (-not $git) {
    Write-Warn "Git not found"
    # Try winget first (works on most networks)
    $installed = Install-WithWinget -Id "Git.Git" -DisplayName "Git"
    if ($installed) { $git = Test-RealCommand "git" }
    
    # Fall back to direct download
    if (-not $git) {
        Write-Info "Trying direct download..."
        $installed = Install-Direct -Name "Git" `
            -Url "https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.3/Git-2.55.0.3-64-bit.exe" `
            -InstallerArgs "/VERYSILENT /NORESTART /SUPPRESSMSGBOXES" `
            -ExeName "git" `
            -FallbackPaths @("$env:ProgramFiles\Git\bin\git.exe", "${env:ProgramFiles(x86)}\Git\bin\git.exe")
        if ($installed) { $git = Test-RealCommand "git" }
    }
    
    if (-not $git) {
        Write-Err "Could not install Git automatically."
        Write-Host "  Install Git manually from: https://git-scm.com/download/win" -ForegroundColor Yellow
        Write-Host "  Use ALL default options, then re-run this installer." -ForegroundColor Yellow
        pause; exit 1
    }
}
Write-Ok "Git: $($git.Source)"

# ── Step 3: Install Python ──────────────────────────────────
Write-Info "Checking Python..."
$python = Test-RealCommand "python3"
if (-not $python) { $python = Test-RealCommand "python" }

if (-not $python) {
    Write-Warn "Python not found (or Microsoft Store stub detected)"

    # Remove the Microsoft Store stubs that block real Python installation
    $stubPaths = @(
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\python3.exe"
    )
    $stubsRemoved = $false
    foreach ($stub in $stubPaths) {
        if (Test-Path $stub) {
            try {
                # Take ownership and remove the stub files
                takeown /f "$stub" /a 2>&1 | Out-Null
                icacls "$stub" /grant "*S-1-5-32-544:F" 2>&1 | Out-Null
                Remove-Item -Force "$stub" 2>&1 | Out-Null
                if (-not (Test-Path $stub)) {
                    Write-Ok "Removed Store stub: $stub"
                    $stubsRemoved = $true
                }
            } catch {
                Write-Warn "Could not remove Store stub: $stub"
                Write-Warn "  To fix manually: Settings > Apps > Advanced app settings > App execution aliases"
                Write-Warn "  Turn OFF 'python.exe' and 'python3.exe'"
            }
        }
    }
    if ($stubsRemoved) { Refresh-Path }

    # Try winget first (works on most networks)
    $installed = Install-WithWinget -Id "Python.Python.3.12" -DisplayName "Python 3.12"
    if ($installed) {
        $python = Test-RealCommand "python"
        if (-not $python) {
            foreach ($p in @("$env:ProgramFiles\Python312\python.exe", "$env:LocalAppData\Programs\Python\Python312\python.exe")) {
                if (Test-Path $p) { $python = Get-Command $p; break }
            }
        }
    }
    
    # Fall back to direct download
    if (-not $python) {
        Write-Info "Trying direct download from python.org..."
        $installed = Install-Direct -Name "Python" `
            -Url "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" `
            -InstallerArgs "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" `
            -ExeName "python" `
            -FallbackPaths @(
                "$env:ProgramFiles\Python312\python.exe",
                "$env:LocalAppData\Programs\Python\Python312\python.exe"
            )
        if ($installed) {
            $python = Test-RealCommand "python"
            if (-not $python) {
                foreach ($p in @("$env:ProgramFiles\Python312\python.exe", "$env:LocalAppData\Programs\Python\Python312\python.exe")) {
                    if (Test-Path $p) { $python = Get-Command $p; break }
                }
            }
        }
    }
}

if (-not $python) {
    Write-Err "Python could not be installed automatically."
    Write-Host "  Download Python 3.12 from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  CHECK 'Add Python to PATH' during install." -ForegroundColor Yellow
    Write-Host "  Then re-run this installer." -ForegroundColor Yellow
    pause; exit 1
}
Write-Ok "Python: $($python.Source)"

# ── Step 4: Install Node.js ─────────────────────────────────
Write-Info "Checking Node.js..."
$node = Test-RealCommand "node"
if (-not $node) {
    Write-Warn "Node.js not found — will install it"
    $installed = Install-Direct -Name "NodeJS" `
        -Url "https://nodejs.org/dist/v22.12.0/node-v22.12.0-x64.msi" `
        -InstallerArgs "/qn /norestart" `
        -ExeName "node" `
        -FallbackPaths @("$env:ProgramFiles\nodejs\node.exe")
    if ($installed) { $node = Test-RealCommand "node" }
}
if ($node) {
    Write-Ok "Node.js: $($node.Source)"
} else {
    Write-Warn "Node.js not found — yt-dlp will use slower Python JS runtime"
}

# ── Step 5: Install ffmpeg ──────────────────────────────────
Write-Info "Checking ffmpeg..."
$ffmpeg = Test-RealCommand "ffmpeg"
if (-not $ffmpeg) {
    Write-Warn "ffmpeg not found — will install it"
    # ffmpeg via direct download is trickier (zip extraction + PATH)
    # Try winget first (it handled ffmpeg well in testing)
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "Installing ffmpeg via winget..."
        winget source update --accept-source-agreements 2>&1 | Out-Null
        $proc = Start-Process -FilePath winget -ArgumentList @(
            "install", "--id", "Gyan.FFmpeg", "--silent",
            "--accept-package-agreements", "--accept-source-agreements"
        ) -NoNewWindow -Wait -PassThru
        if ($proc.ExitCode -eq 0) {
            Refresh-Path; Start-Sleep -Seconds 3
            $ffmpeg = Test-RealCommand "ffmpeg"
        }
    }
    if (-not $ffmpeg) {
        Write-Warn "Could not install ffmpeg automatically."
        Write-Warn "Some yt-dlp formats may not work. Install from https://ffmpeg.org"
    }
}
if ($ffmpeg) { Write-Ok "ffmpeg: $($ffmpeg.Source)" }
else { Write-Warn "ffmpeg not found — some yt-dlp formats may not work" }

# ── Step 6: Install yt-dlp ──────────────────────────────────
Write-Info "Installing yt-dlp (system-wide via pip)..."
try {
    & $python.Source -m pip install --user yt-dlp --quiet 2>&1 | Out-Null
    Refresh-Path
    Write-Ok "yt-dlp installed"
} catch {
    Write-Warn "yt-dlp system install failed — will install in venv later"
}

# ── Step 7: Clone / Pull the repo ───────────────────────────
Write-Info "Setting up application..."
if (Test-Path "$InstallDir\.git") {
    Push-Location "$InstallDir"
    git pull --ff-only 2>&1 | Out-Null
    Pop-Location
    Write-Ok "Repository updated"
} else {
    if (Test-Path "$InstallDir") { Remove-Item -Recurse -Force "$InstallDir" }
    Write-Info "Cloning Cloud-DJ to $InstallDir..."
    git clone $RepoUrl "$InstallDir" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to clone repository. Check internet connection."
        pause; exit 1
    }
    Write-Ok "Repository cloned"
}

Set-Location "$InstallDir"

# ── Step 8: Create Virtual Environment ──────────────────────
Write-Info "Setting up Python virtual environment..."
if (-not (Test-Path ".venv")) {
    & $python.Source -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create virtual environment."
        pause; exit 1
    }
    Write-Ok "Virtual environment created"
} else {
    Write-Ok "Virtual environment already exists"
}

$venvPython = Join-Path (Get-Location) ".venv\Scripts\python.exe"
$pipExe = Join-Path (Get-Location) ".venv\Scripts\pip.exe"
if (-not (Test-Path $pipExe)) { $pipExe = Join-Path (Get-Location) ".venv\Scripts\pip3.exe" }
if (-not (Test-Path $pipExe)) {
    Write-Err "pip not found in virtual environment"
    pause; exit 1
}

Write-Info "Installing Python dependencies..."
& $pipExe install --upgrade pip --quiet 2>&1 | Out-Null
& $pipExe install -r requirements.txt --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "pip install had issues — showing output:"
    & $pipExe install -r requirements.txt 2>&1 | Out-Host
}
& $pipExe install yt-dlp --quiet 2>&1 | Out-Null
Write-Ok "Python dependencies installed"

# ── Step 9: Verify venv ──────────────────────────────────
if (-not (Test-Path $venvPython)) {
    Write-Err "Virtual environment is broken — missing python.exe"
    pause; exit 1
}
$venvYtdlp = Join-Path (Get-Location) ".venv\Scripts\yt-dlp.exe"
if (-not (Test-Path $venvYtdlp)) {
    $found = Get-ChildItem (Join-Path (Get-Location) ".venv\Scripts\yt-dlp*") -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $found) { & $pipExe install yt-dlp 2>&1 | Out-Null }
}
Write-Ok "Venv Python: $venvPython"
Write-Ok "app.py auto-detects all tools (no manual config needed)"

# ── Step 10: Open Windows Firewall ──────────────────────────
Write-Info "Opening port $Port in Windows Firewall..."
try {
    $rule = Get-NetFirewallRule -DisplayName "Cloud-DJ (TCP $Port)" -ErrorAction SilentlyContinue
    if (-not $rule) {
        New-NetFirewallRule -DisplayName "Cloud-DJ (TCP $Port)" `
            -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow `
            -Profile Private,Domain -ErrorAction Stop | Out-Null
        Write-Ok "Firewall rule created"
    } else {
        Write-Ok "Firewall rule already exists"
    }
} catch {
    Write-Warn "Could not create firewall rule."
    Write-Host "  To add manually: netsh advfirewall firewall add rule name=`"Cloud-DJ`" dir=in action=allow protocol=TCP localport=$Port" -ForegroundColor Yellow
}

# ── Step 11: Create Scheduled Task for auto-start ──────────
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
        Write-Ok "Scheduled Task '$ServiceName' created"
    } else {
        Write-Ok "Scheduled Task already exists"
    }
} catch {
    Write-Warn "Could not create Scheduled Task. Run as Administrator or use the startup script instead."
}

# ── Step 12: Generate startup script ───────────────────────
$batContent = @"
@echo off
cd /d "$InstallDir"
start /min "" "$venvPython" "app.py"
"@
Set-Content -Path "$InstallDir\start-cloud-dj.bat" -Value $batContent
Write-Ok "Startup script: $InstallDir\start-cloud-dj.bat"

# ── Step 12b: Create Desktop shortcut ──────────────────────
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = "$desktopPath\Cloud-DJ.lnk"
try {
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "cmd.exe"
    $shortcut.Arguments = "/c start /min """" ""$venvPython"" ""$InstallDir\app.py"""
    $shortcut.WorkingDirectory = "$InstallDir"
    $shortcut.Description = "Cloud-DJ LAN Music Server"
    $shortcut.WindowStyle = 7  # Minimized
    $shortcut.Save()
    Write-Ok "Desktop shortcut: $shortcutPath"
} catch {
    Write-Warn "Could not create desktop shortcut: $_"
}

# ── Step 13: Start the server ──────────────────────────────
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
    Write-Ok "Server is already running on port $Port"
}

# ── Step 14: Wait and verify ───────────────────────────────
Write-Info "Verifying server..."
Start-Sleep -Seconds 5
try {
    $response = Invoke-WebRequest -Uri "http://localhost:$Port" -TimeoutSec 5 -UseBasicParsing
    if ($response.StatusCode -eq 200 -or $response.StatusCode -eq 302) {
        Write-Ok "Server is responding on http://localhost:$Port"
    }
} catch {
    Write-Warn "Server may not be ready yet. Try: http://localhost:$Port"
}

# ── Step 15: Get LAN IP ────────────────────────────────────
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
