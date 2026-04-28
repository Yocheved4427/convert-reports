# run-docker.ps1 — Wrapper that bridges the F: drive into Docker via a C: temp dir.
# Usage: .\run-docker.ps1 [--seed 123] [--location "some place"]

param(
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
$pdfs = Get-ChildItem "$ProjectDir\input_pdfs" -Filter "*.pdf"
if ($pdfs.Count -eq 0) {
    Write-Error "No PDF files found in $ProjectDir\input_pdfs"
    exit 1
}
$pdfs | Copy-Item -Destination $TempInput
Write-Host "      Copied $($pdfs.Count) PDF(s)."

# ── Build docker args ──────────────────────────────────────────────────────────
$DockerArgs = @(
    "run", "--rm",
    "-v", "//c/Temp/convert-reports-docker/input_pdfs:/app/input_pdfs",
    "-v", "//c/Temp/convert-reports-docker/output_pdfs:/app/output_pdfs",
    "convert-reports",
    "--input", "input_pdfs/",
    "--output", "output_pdfs/",
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

# ── Cleanup ────────────────────────────────────────────────────────────────────
Remove-Item -Recurse -Force $TempBase -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done. Output files are in: $ProjectDir\output_pdfs"
