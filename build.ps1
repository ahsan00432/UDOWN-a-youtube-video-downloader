$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    throw 'Create the project environment first: py -m venv .venv'
}

& $python -m pip install -r (Join-Path $PSScriptRoot 'build-requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

& $python (Join-Path $PSScriptRoot 'make_icon.py')
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }

Push-Location $PSScriptRoot
try {
    & $python -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name udown --icon assets\udown.ico `
        --collect-all yt_dlp --add-data 'assets\udown.ico;assets' udown.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    Compress-Archive -Path browser_extension\* `
        -DestinationPath dist\udown-browser-extension.zip -Force
} finally {
    Pop-Location
}

Write-Host "Built: $(Join-Path $PSScriptRoot 'dist\udown.exe')"