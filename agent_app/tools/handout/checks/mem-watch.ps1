# Every 2 s until the stop file appears: free memory, the commit room, and the memory (working
# set, private) of the app's server, every program it started (the workers' CLIs and their
# Python), and the app's window (Chrome or Edge), into a CSV.
# Folder: the app's folder (where Annotation.exe is).
param([string]$Folder, [string]$Out, [string]$StopFile)
$here = [regex]::Escape($Folder)
"time,free_mb,commit_room_mb,server_ws,server_priv,children,children_ws,children_priv,largest_child_ws,child_names,window_ws,window_priv" | Out-File $Out -Encoding utf8
while (-not (Test-Path $StopFile)) {
  $all = Get-CimInstance Win32_Process
  $os = Get-CimInstance Win32_OperatingSystem
  $server = $all | ? { $_.Name -eq 'python.exe' -and $_.CommandLine -match $here -and $_.CommandLine -match '-m agent_app$' } | Select -First 1
  $kids = @()
  if ($server) {
    $ids = @($server.ProcessId)
    do {
      $new = @($all | ? { $ids -contains $_.ParentProcessId -and $ids -notcontains $_.ProcessId })
      $kids += $new
      $ids += $new | % { $_.ProcessId }
    } while ($new.Count)
  }
  $window = @($all | ? { $_.Name -match '^(chrome|msedge)\.exe$' -and $_.CommandLine -match $here })
  $mb = 1MB
  $names = ($kids | Group-Object Name | % { "$($_.Name)x$($_.Count)" }) -join ' '
  @(
    (Get-Date -Format 'HH:mm:ss'),
    [int]($os.FreePhysicalMemory / 1KB),
    [int]($os.FreeVirtualMemory / 1KB),
    $(if ($server) { [int]($server.WorkingSetSize / $mb) } else { 0 }),
    $(if ($server) { [int]($server.PrivatePageCount / $mb) } else { 0 }),
    $kids.Count,
    [int](($kids | Measure-Object WorkingSetSize -Sum).Sum / $mb),
    [int](($kids | Measure-Object PrivatePageCount -Sum).Sum / $mb),
    [int](($kids | Measure-Object WorkingSetSize -Maximum).Maximum / $mb),
    $names,
    [int](($window | Measure-Object WorkingSetSize -Sum).Sum / $mb),
    [int](($window | Measure-Object PrivatePageCount -Sum).Sum / $mb)
  ) -join ',' | Out-File $Out -Append -Encoding utf8
  Start-Sleep 2
}
