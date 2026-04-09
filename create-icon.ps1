# Download the Twemoji (Twitter open-source) fork+knife+plate emoji as PNG
# Then convert to .ico for the desktop shortcut

$pngUrl = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f37d.png"
$pngPath = Join-Path $PSScriptRoot "meal-planner.png"
$iconPath = Join-Path $PSScriptRoot "meal-planner.ico"

Write-Host "Downloading emoji image..."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $pngUrl -OutFile $pngPath

if (-not (Test-Path $pngPath)) {
    Write-Host "Download failed! Trying backup URL..."
    $pngUrl2 = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f37d.png"
    Invoke-WebRequest -Uri $pngUrl2 -OutFile $pngPath
}

if (-not (Test-Path $pngPath)) {
    Write-Host "ERROR: Could not download emoji image"
    exit 1
}

Write-Host "Converting to .ico..."
Add-Type -AssemblyName System.Drawing

$srcBmp = New-Object System.Drawing.Bitmap($pngPath)

# Scale to 128x128 for a crisp icon
$size = 128
$bmp = New-Object System.Drawing.Bitmap($size, $size)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = 'HighQuality'
$g.InterpolationMode = 'HighQualityBicubic'
$g.Clear([System.Drawing.Color]::Transparent)
$g.DrawImage($srcBmp, 8, 8, 112, 112)
$g.Dispose()
$srcBmp.Dispose()

# Save as .ico
$hIcon = $bmp.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($hIcon)
$fs = New-Object System.IO.FileStream($iconPath, [System.IO.FileMode]::Create)
$icon.Save($fs)
$fs.Close()
$fs.Dispose()
$icon.Dispose()
$bmp.Dispose()

# Clean up PNG
Remove-Item $pngPath -ErrorAction SilentlyContinue

$fileSize = (Get-Item $iconPath).Length
Write-Host "Icon created: $iconPath ($fileSize bytes)"

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
Write-Host "Right-click Desktop > Refresh if needed"
