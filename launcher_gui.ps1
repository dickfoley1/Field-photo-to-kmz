Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $scriptRoot "drone_images_to_kmz.py"
$venvPythonw = Join-Path $scriptRoot ".venv\Scripts\pythonw.exe"
$venvPython = Join-Path $scriptRoot ".venv\Scripts\python.exe"

$exiftoolPath = $null
if (Test-Path (Join-Path $scriptRoot "exiftool.exe")) {
    $exiftoolPath = Join-Path $scriptRoot "exiftool.exe"
}
elseif (Test-Path (Join-Path $scriptRoot "exiftool\\exiftool.exe")) {
    $exiftoolPath = Join-Path $scriptRoot "exiftool\\exiftool.exe"
}

$pythonCommands = @(
    @{ FilePath = $venvPythonw; Arguments = @($scriptPath, "--gui") },
    @{ FilePath = $venvPython; Arguments = @($scriptPath, "--gui") },
    @{ FilePath = "pyw"; Arguments = @("-3", $scriptPath, "--gui") },
    @{ FilePath = "pythonw"; Arguments = @($scriptPath, "--gui") },
    @{ FilePath = "py"; Arguments = @("-3", $scriptPath, "--gui") },
    @{ FilePath = "python"; Arguments = @($scriptPath, "--gui") }
)

foreach ($command in $pythonCommands) {
    if ($command.FilePath -like "*\*" -and -not (Test-Path $command.FilePath)) {
        continue
    }
    $arguments = @($command.Arguments)
    if ($exiftoolPath) {
        $arguments += @("--exiftool", $exiftoolPath)
    }

    try {
        $proc = Start-Process -FilePath $command.FilePath -ArgumentList $arguments -PassThru -WindowStyle Hidden -ErrorAction Stop
        if ($proc) {
            exit 0
        }
    }
    catch {
    }
}

[System.Windows.Forms.MessageBox]::Show(
    "Python 3 was not found. Install Python 3 and retry.",
    "Field Photo to KMZ Studio",
    "OK",
    "Error"
) | Out-Null
exit 1
