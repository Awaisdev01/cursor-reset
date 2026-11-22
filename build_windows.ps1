# Build cursor-reset.exe for Windows (run on Windows: powershell -File build_windows.ps1)
pip install pyinstaller
pyinstaller --onefile --windowed --name cursor-reset gui.py
Write-Host "✔ dist\cursor-reset.exe"
