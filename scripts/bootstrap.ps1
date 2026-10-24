$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = (Get-Command python).Source
$Version = & $Python --version
if ($Version -ne 'Python 3.11.9') {
    throw "ArmoredCreator requer Python 3.11.9; encontrado: $Version"
}
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $VenvPython) {
    throw 'O ambiente .venv já existe. Preserve-o e revise antes de recriar.'
}
Push-Location $ProjectRoot
try {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar .venv' }
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao atualizar pip' }
    & $VenvPython -m pip install -r requirements-runtime311.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências unificadas' }
    & $VenvPython -m pip install --no-build-isolation --no-deps .
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar ArmoredCreator' }
    & $VenvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'pip check encontrou dependências incompatíveis' }
} finally {
    Pop-Location
}
