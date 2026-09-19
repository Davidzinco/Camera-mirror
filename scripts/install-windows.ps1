# Invoked by Install-Windows.cmd; execution policy is scoped to that process only.
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Test-Python {
    param([string]$Executable, [string[]]$Prefix = @())
    try {
        $result = & $Executable @Prefix -c 'import sys, struct; assert (3,10) <= sys.version_info[:2] < (3,15) and struct.calcsize(chr(80)) == 8; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) { return [string]($result | Select-Object -Last 1) }
    } catch { }
    return $null
}

function Find-Python {
    $existing = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (Test-Path $existing) {
        $found = Test-Python $existing
        if ($found) { return $found }
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $found = Test-Python -Executable $launcher.Source -Prefix @('-3.12')
        if ($found) { return $found }
    }
    $userPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (Test-Path $userPython) {
        $found = Test-Python $userPython
        if ($found) { return $found }
    }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python -and $python.Source -notlike '*\WindowsApps\*') {
        $found = Test-Python $python.Source
        if ($found) { return $found }
    }
    return $null
}

try {
    $python = Find-Python
    if ($CheckOnly) {
        if (-not $python) { throw 'Python 64-bit tidak ditemukan.' }
        Write-Host "Python ditemukan: $python"
        exit 0
    }
    if (-not $python) {
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
            throw 'Pasang Python 3.12 64-bit dari python.org dan jalankan file ini lagi. Lihat README.md.'
        }
        Write-Host 'Memasang Python 3.12 untuk pengguna ini melalui WinGet...'
        & winget.exe install --id Python.Python.3.12 --exact --source winget --scope user --architecture x64
        if ($LASTEXITCODE -ne 0) { throw 'Instalasi Python melalui WinGet tidak selesai.' }
        $python = Find-Python
        if (-not $python) { throw 'Python sudah dipasang. Tutup jendela ini dan klik installer lagi.' }
    }
    & $python (Join-Path $ProjectRoot 'scripts\bootstrap.py') --launch
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
