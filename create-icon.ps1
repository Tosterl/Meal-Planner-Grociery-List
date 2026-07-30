Add-Type -AssemblyName System.Drawing

$pngPath = Join-Path $PSScriptRoot "Meal plan icon with healthy food.png"
$iconPath = Join-Path $PSScriptRoot "meal-planner.ico"

if (-not (Test-Path $pngPath)) {
    Write-Host "ERROR: Could not find '$pngPath'"
    exit 1
}

$srcBmp = New-Object System.Drawing.Bitmap($pngPath)

# Scale to 128x128
$size = 128
$bmp = New-Object System.Drawing.Bitmap($size, $size)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = 'HighQuality'
$g.InterpolationMode = 'HighQualityBicubic'
$g.Clear([System.Drawing.Color]::Transparent)
$g.DrawImage($srcBmp, 0, 0, $size, $size)
$g.Dispose()
$srcBmp.Dispose()

$hIcon = $bmp.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($hIcon)
$fs = New-Object System.IO.FileStream($iconPath, [System.IO.FileMode]::Create)
$icon.Save($fs)
$fs.Close()
$fs.Dispose()
$icon.Dispose()
$bmp.Dispose()

Write-Host "Icon created: $iconPath"

# Update desktop shortcut
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopPath "Meal Planner Pro.lnk"
$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $PSScriptRoot "start.bat"
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = "Launch Meal Planner Pro"
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Save()
Write-Host "Desktop shortcut updated!"
