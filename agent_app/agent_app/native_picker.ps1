$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$options = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__OPTIONS__')) | ConvertFrom-Json
Add-Type -AssemblyName PresentationFramework
# The folder dialog hides files, so a file dialog shows the folder's images. Open with the
# prefilled name (no such file) returns '<folder>\<name>': the whole folder.
$dialog = [Microsoft.Win32.OpenFileDialog]::new()
$dialog.Title = $options.title
$dialog.Filter = "$($options.patterns)|$($options.patterns)"
$dialog.Multiselect = $true
$dialog.CheckFileExists = $false
$dialog.AddExtension = $false
$dialog.FileName = $options.whole_folder
$dialog.InitialDirectory = $options.directory
# An owned window keeps the common dialog in front; never seize another app's window.
$owner = [System.Windows.Window]::new()
$owner.Width = 1
$owner.Height = 1
$owner.WindowStyle = 'None'
$owner.ShowInTaskbar = $false
$owner.WindowStartupLocation = 'CenterScreen'
$owner.Topmost = $true
$owner.Show()
try {
    $accepted = $dialog.ShowDialog($owner)
    $paths = @()
    if ($accepted) {
        $paths = @($dialog.FileNames)
    }
    ConvertTo-Json -Compress -InputObject @{ paths = @($paths) }
} finally {
    $owner.Close()
}
