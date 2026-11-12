# How the app ends, and what the person is told: opens the app (Annotation.exe in the zip, or the
# shortcut Annotation.lnk npm start makes in a clone), ends it one way, and reads the launcher's
# message box, if one comes.
#   server: the server is killed           -> "アプリが途中で止まりました" and the log
#   window: the app's window is killed     -> "アプリの窓が途中で閉じたので…"
#   quit:   quit as the screen's power does -> nothing; everything gone
#   close:  the window's close button       -> nothing; everything gone
# Folder: the app's folder (where Annotation.exe or Annotation.lnk is). Start: what to open there.
# Nothing else of the app may be running. "windows:" names what shows a window besides the app's
# own (2026-11-11: a start by double-click opens no terminal).
param(
  [string]$Folder,
  [ValidateSet('server', 'window', 'quit', 'close')][string]$Case,
  [string]$Start = 'Annotation.exe'
)
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$here = [regex]::Escape($Folder)
# A clone's .venv\Scripts\python(w).exe hands over to uv's Python outside the folder, whose command
# line does not name the folder: the app's Pythons are told by "-m agent_app" too.
function Mine {
  Get-CimInstance Win32_Process | ? {
    $_.Name -ne 'powershell.exe' -and ($_.CommandLine -match $here -or ($_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -match '-m agent_app'))
  }
}
# Of a .venv's two, the one doing the work (outside the folder) first.
function First($name, $pattern) {
  Mine | ? { $_.Name -eq $name -and $_.CommandLine -match $pattern } | Sort-Object { $_.CommandLine -match $here } | Select -First 1
}
Start-Process -FilePath (Join-Path $Folder $Start)
for ($i = 0; $i -lt 120; $i++) { if (Mine | ? { $_.Name -match '^(chrome|msedge)\.exe$' }) { break }; Start-Sleep -Milliseconds 500 }
Start-Sleep 4
$server = First 'python.exe' '-m agent_app"?\s*$'
$window = Mine | ? { $_.Name -match '^(chrome|msedge)\.exe$' -and $_.CommandLine -notmatch '--type=' } | Select -First 1
$launcher = First 'pythonw.exe' 'agent_app\.launch'
'windows: ' + ((Mine | ? { $_.Name -notmatch '^(chrome|msedge)\.exe$' } | % { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue } | ? { $_.MainWindowHandle -ne 0 } | % { $_.ProcessName }) -join ', ')
if ($Case -eq 'server') { Stop-Process -Id $server.ProcessId -Force }
if ($Case -eq 'window') { Stop-Process -Id $window.ProcessId -Force }
# The port the app took (3900, else the next free one) is in its server.port (2026-11-11: 3900 was
# taken by another app, and its quit went there).
$port = (Get-Content (Join-Path $Folder 'agent_app\server.port') -Raw).Trim()
if ($Case -eq 'quit') { Invoke-WebRequest -UseBasicParsing -Method Post -ContentType 'application/json' -Body '{}' "http://127.0.0.1:$port/v1/quit" | Out-Null }
if ($Case -eq 'close') { (Get-Process -Id $window.ProcessId).CloseMainWindow() | Out-Null }
$t = Get-Date
$said = $null
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 500
  $l = Get-Process -Id $launcher.ProcessId -ErrorAction SilentlyContinue
  if (-not $l) { break }
  $l.Refresh()
  if ($l.MainWindowHandle -ne 0) {
    $root = [Windows.Automation.AutomationElement]::FromHandle($l.MainWindowHandle)
    $said = ($root.FindAll([Windows.Automation.TreeScope]::Descendants, [Windows.Automation.Condition]::TrueCondition) | % { $_.Current.Name } | ? { $_ -and $_ -ne 'OK' }) -join ' / '
    Stop-Process -Id $l.Id -Force
    break
  }
}
"${Case}: after " + [Math]::Round(((Get-Date) - $t).TotalSeconds, 1) + 's said: ' + $(if ($said) { $said } else { '(nothing)' })
Start-Sleep 5
'left: ' + ((Mine | % { $_.Name }) -join ', ')
Mine | % { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
