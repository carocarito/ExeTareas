$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --windowed --name "TareasRecurrentes" main.py
Write-Host "Listo: $PSScriptRoot\dist\TareasRecurrentes\TareasRecurrentes.exe"
