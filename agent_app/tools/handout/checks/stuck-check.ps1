# The server ends when quit although connections were never counted out (2026-10-30: Windows'
# asyncio raised closing a connection a client had cut, and the quit server waited forever):
# reset_server.py makes every closing connection fail so, close.py makes 5 connections, and
# the server is quit. Before the fix it was still running after 20 s; now it ends within 4 s.
# Folder: the app's folder (where Annotation.exe is). Nothing else of the app may be running.
param([string]$Folder)
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$py = Join-Path $Folder 'python-windows\python.exe'
$log = Join-Path $Folder 'agent_app\server.log'
$before = if (Test-Path $log) { (Get-Content $log -Encoding UTF8).Count } else { 0 }
$p = Start-Process -FilePath $py -ArgumentList (Join-Path $PSScriptRoot 'reset_server.py') -WorkingDirectory (Join-Path $Folder 'agent_app') -WindowStyle Hidden -PassThru
for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:3900/health | Out-Null; break } catch { Start-Sleep -Milliseconds 300 } }
& $py (Join-Path $PSScriptRoot 'close.py') 3900 5
Start-Sleep 1
$t = Get-Date
Invoke-WebRequest -UseBasicParsing -Method Post -ContentType 'application/json' -Body '{}' http://127.0.0.1:3900/v1/quit | Out-Null
$ended = $p.WaitForExit(20000)
"ended: $ended after " + [Math]::Round(((Get-Date) - $t).TotalSeconds, 1) + 's'
$lines = Get-Content $log -Encoding UTF8 | Select-Object -Skip $before
'resets in the log: ' + @($lines | Select-String 'ConnectionResetError').Count
if (-not $ended) { Stop-Process -Id $p.Id -Force; 'stopped by the check' }
