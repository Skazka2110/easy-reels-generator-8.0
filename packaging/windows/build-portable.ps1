[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath"
    }
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "This build script must run on 64-bit Windows 10 or Windows 11."
}

$BasePython = $null
$BasePythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($Version in @("3.13", "3.12", "3.11")) {
        & py "-$Version" -c "import sys; raise SystemExit(0 if sys.maxsize > 2**32 else 1)" *> $null
        if ($LASTEXITCODE -eq 0) {
            $BasePython = "py"
            $BasePythonArgs = @("-$Version")
            break
        }
    }
}
if (-not $BasePython -and (Get-Command python -ErrorAction SilentlyContinue)) {
    & python -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) and sys.maxsize > 2**32 else 1)" *> $null
    if ($LASTEXITCODE -eq 0) {
        $BasePython = "python"
        $BasePythonArgs = @()
    }
}
if (-not $BasePython) {
    throw "A supported 64-bit Python was not found. Install Python 3.13 x64 from python.org. Python 3.14 cannot build this release."
}

Invoke-Checked $BasePython ($BasePythonArgs + @(
    "-c",
    "import sys; assert (3, 11) <= sys.version_info[:2] < (3, 14), 'Python 3.11, 3.12 or 3.13 is required'; assert sys.maxsize > 2**32, '64-bit Python is required'"
))

$Venv = Join-Path $Root ".windows-build-venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (Test-Path $VenvPython) {
    & $VenvPython -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) and sys.maxsize > 2**32 else 1)" *> $null
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -LiteralPath $Venv -Recurse -Force
    }
}
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating an isolated build environment..." -ForegroundColor Cyan
    Invoke-Checked $BasePython ($BasePythonArgs + @("-m", "venv", $Venv))
}

Write-Host "Installing build dependencies..." -ForegroundColor Cyan
Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked $VenvPython @(
    "-m", "pip", "install", "--upgrade",
    "-r", (Join-Path $Root "packaging\windows\requirements-build.txt"),
    $Root
)

$BuildRoot = Join-Path $Root "build\windows"
$StageRoot = Join-Path $Root "artifacts\windows\staging"
if (Test-Path $BuildRoot) {
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force
}
if (Test-Path $StageRoot) {
    Remove-Item -LiteralPath $StageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $BuildRoot, $StageRoot -Force | Out-Null

Write-Host "Building the application..." -ForegroundColor Cyan
Invoke-Checked $VenvPython @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--workpath", $BuildRoot,
    "--distpath", $StageRoot,
    (Join-Path $Root "packaging\windows\EasyReelsGenerator.spec")
)

$PortableDir = Join-Path $StageRoot "Easy Reels Generator"
if (-not (Test-Path (Join-Path $PortableDir "Easy Reels Generator.exe"))) {
    throw "PyInstaller did not create the expected executable."
}

Write-Host "Adding project folders, workbook, settings and fonts..." -ForegroundColor Cyan
Copy-Item -Path (Join-Path $Root "portable_template\*") -Destination $PortableDir -Recurse -Force
foreach ($DirectoryName in @(
    "videos", "videos\top", "videos\bottom", "music", "fonts", "overlays",
    "ready", "preview", "logs", "backups", "licenses"
)) {
    New-Item -ItemType Directory -Path (Join-Path $PortableDir $DirectoryName) -Force | Out-Null
}

$CacheRoot = Join-Path $Root ".windows-build-cache"
$FfmpegZip = Join-Path $CacheRoot "ffmpeg-release-essentials.zip"
$FfmpegExtract = Join-Path $CacheRoot "ffmpeg"
New-Item -ItemType Directory -Path $CacheRoot -Force | Out-Null
if (-not (Test-Path $FfmpegZip)) {
    Write-Host "Downloading portable FFmpeg..." -ForegroundColor Cyan
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $FfmpegZip
}
if (Test-Path $FfmpegExtract) {
    Remove-Item -LiteralPath $FfmpegExtract -Recurse -Force
}
Expand-Archive -LiteralPath $FfmpegZip -DestinationPath $FfmpegExtract -Force

$FfmpegExe = Get-ChildItem -Path $FfmpegExtract -Filter "ffmpeg.exe" -File -Recurse | Select-Object -First 1
$FfprobeExe = Get-ChildItem -Path $FfmpegExtract -Filter "ffprobe.exe" -File -Recurse | Select-Object -First 1
if (-not $FfmpegExe -or -not $FfprobeExe) {
    throw "ffmpeg.exe and ffprobe.exe were not found in the downloaded archive."
}
Copy-Item -LiteralPath $FfmpegExe.FullName -Destination (Join-Path $PortableDir "ffmpeg.exe") -Force
Copy-Item -LiteralPath $FfprobeExe.FullName -Destination (Join-Path $PortableDir "ffprobe.exe") -Force

$ThirdParty = Join-Path $PortableDir "Third-party licenses"
New-Item -ItemType Directory -Path $ThirdParty -Force | Out-Null
$FfmpegLicense = Get-ChildItem -Path $FfmpegExtract -File -Recurse |
    Where-Object { $_.Name -match "^LICENSE(\.|$)" } |
    Select-Object -First 1
if ($FfmpegLicense) {
    Copy-Item -LiteralPath $FfmpegLicense.FullName -Destination (Join-Path $ThirdParty "FFmpeg-LICENSE.txt") -Force
}
@"
FFmpeg is included as a separate executable component.
Windows build source: https://www.gyan.dev/ffmpeg/builds/
Upstream project: https://ffmpeg.org/
"@ | Set-Content -LiteralPath (Join-Path $ThirdParty "FFmpeg-INFO.txt") -Encoding UTF8

$ArtifactsRoot = Join-Path $Root "artifacts\windows"
$ZipPath = Join-Path $ArtifactsRoot "Easy_Reels_Generator_Windows_x64_v080.zip"
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Write-Host "Creating the portable ZIP archive..." -ForegroundColor Cyan
Compress-Archive -Path (Join-Path $PortableDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "Build completed successfully:" -ForegroundColor Green
Write-Host $ZipPath -ForegroundColor Green
