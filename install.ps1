param(
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"

function Find-Python {
    $python = Get-Command py -ErrorAction SilentlyContinue
    if ($python) { return "py" }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return "python" }
    throw "Python 3.10 or newer is required. Install it from https://www.python.org/downloads/windows/"
}

$python = Find-Python
$version = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$version -lt [version]"3.10") {
    throw "OpenTune requires Python 3.10 or newer; found $version."
}

if (-not $SkipDependencies) {
    $commands = @{
        "mpv" = "mpv (audio playback)"
        "yt-dlp" = "yt-dlp (YouTube search and metadata)"
        "ffmpeg" = "ffmpeg (optional downloads)"
    }
    $missing = @($commands.Keys | Where-Object { -not (Get-Command $_ -ErrorAction SilentlyContinue) })
    if ($missing.Count -gt 0) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) {
            throw "Missing $($missing -join ', '). Install them and put them on PATH, or install App Installer to use winget."
        }
        # These IDs are the commonly published winget packages. If a package
        # ID changes, winget prints the failure and the user can install the
        # corresponding tool manually before rerunning with -SkipDependencies.
        $packageIds = @{
            "mpv" = "shinchiro.mpv"
            "yt-dlp" = "yt-dlp.yt-dlp"
            "ffmpeg" = "Gyan.FFmpeg"
        }
        foreach ($name in $missing) {
            Write-Host "Installing $($commands[$name])..."
            & winget install --id $packageIds[$name] --exact --accept-source-agreements --accept-package-agreements
        }
    }
}

Write-Host "Installing OpenTune in an isolated pipx environment..."
& $python -m pip install --user --upgrade pipx
& $python -m pipx ensurepath | Out-Host
& $python -m pipx install --force ".[windows]"

Write-Host ""
Write-Host "OpenTune is installed. Restart PowerShell if `opentune` is not found yet."
Write-Host "Try: opentune --help"
