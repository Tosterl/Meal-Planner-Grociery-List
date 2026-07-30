$desktopPath = [Environment]::GetFolderPath('Desktop')
$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut("$desktopPath\Meal Planner Pro.lnk")
$shortcut.TargetPath = Join-Path $PSScriptRoot "start.bat"
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = "Launch Meal Planner Pro"
$iconPath = Join-Path $PSScriptRoot "meal-planner.ico"
if (Test-Path $iconPath) {
    $shortcut.IconLocation = $iconPath
} else {
    $shortcut.IconLocation = "shell32.dll,170"
}
$shortcut.Save()
Write-Host "Desktop shortcut created at: $desktopPath\Meal Planner Pro.lnk"
