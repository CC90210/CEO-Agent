# Bravo Terminal IDE Launcher
$env:OLLAMA_LLM_LIBRARY = "cpu"
$env:OLLAMA_NUM_GPU = "0"
$env:OLLAMA_VULKAN = "false"
$env:OLLAMA_GPU_DRIVER = "cpu"
$env:OLLAMA_HOST = "http://127.0.0.1:11434"
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "Starting Bravo Terminal IDE Harness..." -ForegroundColor Cyan
python (Join-Path $PSScriptRoot "scripts\bravo_cli.py")
