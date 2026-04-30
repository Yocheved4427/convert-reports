# run-docker.ps1 — Wrapper that bridges the F: drive into Docker via a C: temp dir.
#
# Docker Desktop on Windows cannot directly mount non-C: drives via WSL2.
# This script copies PDFs to C:\Temp first, mounts that directory, then
# copies outputs back.
#
# Usage:
#   .\run-docker.ps1                           # process all PDFs
#   .\run-docker.ps1 -File a_r_9.pdf           # process a single PDF
#   .\run-docker.ps1 -Seed 123 -Location "אשדוד"

param(
    [string]$File     = "",
    [string]$Seed     = "42",
    [string]$Location = ""
)

$ErrorActionPreference = "Stop"

# ── Paths ──────────────────────────────────────────────────────────────────────
$ProjectDir = $PSScriptRoot
$TempBase   = "C:\Temp\convert-reports-docker"
$TempInput  = "$TempBase\input_pdfs"
$TempOutput = "$TempBase\output_pdfs"

# ── Setup temp dirs ────────────────────────────────────────────────────────────
Write-Host "[1/4] Preparing temp directories on C: ..."
Remove-Item -Recurse -Force $TempBase -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $TempInput  | Out-Null
New-Item -ItemType Directory -Force $TempOutput | Out-Null

# ── Copy input PDFs to temp ────────────────────────────────────────────────────
Write-Host "[2/4] Copying input PDFs to $TempInput ..."
if ($File -ne "") {
    $pdfs = @(Get-Item "$ProjectDir\input_pdfs\$File")
} else {
    $pdfs = Get-ChildItem "$ProjectDir\input_pdfs" -Filter "*.pdf"
}
if ($pdfs.Count -eq 0) {
    Write-Error "No PDF files found in $ProjectDir\input_pdfs"
    exit 1
}
$pdfs | Copy-Item -Destination $TempInput
Write-Host "      Copied $($pdfs.Count) PDF(s)."

# ── Build docker args ──────────────────────────────────────────────────────────
# Use Unix-style //c/ paths so Docker Desktop (WSL2 backend) can resolve them.
$InputArg = if ($File -ne "") { "/data/input/$File" } else { "/data/input/" }

$DockerArgs = @(
    "run", "--rm",
    "-v", "//c/Temp/convert-reports-docker/input_pdfs:/data/input",
    "-v", "//c/Temp/convert-reports-docker/output_pdfs:/data/output",
    "attendance-report",
    $InputArg,
    "-o", "/data/output/",
    "--seed", $Seed
)
if ($Location -ne "") {
    $DockerArgs += @("--location", $Location)
}

# ── Run container ──────────────────────────────────────────────────────────────
Write-Host "[3/4] Running Docker container ..."
& docker @DockerArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker container exited with code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# ── Copy outputs back ──────────────────────────────────────────────────────────
Write-Host "[4/4] Copying outputs to $ProjectDir\output_pdfs ..."
Get-ChildItem $TempOutput | Copy-Item -Destination "$ProjectDir\output_pdfs" -Force
$count = (Get-ChildItem $TempOutput).Count
Write-Host "      Copied $count output file(s)."
Write-Host ""
Write-Host "Done. Outputs are in: $ProjectDir\output_pdfs"
