$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m pip install -r requirements.txt
# OneDrive puede bloquear la limpieza de build/. Por eso los archivos temporales
# de PyInstaller se generan fuera de la carpeta sincronizada.
$taskBuildRoot = Join-Path $env:LOCALAPPDATA 'TareitasBuild'
$taskDistRoot = Join-Path $PSScriptRoot 'dist-nueva'
New-Item -ItemType Directory -Force -Path $taskBuildRoot | Out-Null
python -m PyInstaller --noconfirm --clean --windowed --name "TareasRecurrentes" --workpath "$taskBuildRoot\work" --specpath "$taskBuildRoot\spec" --distpath "$taskDistRoot" main.py
Write-Host "Listo: $taskDistRoot\TareasRecurrentes\TareasRecurrentes.exe"
