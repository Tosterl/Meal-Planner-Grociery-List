@echo off
echo Creating desktop shortcut for Meal Planner Pro...

:: Create shortcut using PowerShell
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $shortcut = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Meal Planner Pro.lnk')); $shortcut.TargetPath = '%~dp0start.bat'; $shortcut.WorkingDirectory = '%~dp0'; $shortcut.Description = 'Launch Meal Planner Pro'; $shortcut.IconLocation = 'shell32.dll,170'; $shortcut.Save()"

if errorlevel 1 (
    echo.
    echo  [ERROR] Could not create shortcut automatically.
    echo  You can manually create one:
    echo    1. Right-click Desktop ^> New ^> Shortcut
    echo    2. Browse to: %~dp0start.bat
    echo    3. Name it: Meal Planner Pro
    echo.
) else (
    echo.
    echo  Desktop shortcut created!
    echo  Look for "Meal Planner Pro" on your desktop.
    echo.
)

pause
