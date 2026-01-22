# Activate venv (handles Conda conflict)
# Usage: . .\activate.ps1

# Deactivate Conda if active
if ($env:CONDA_DEFAULT_ENV) {
    conda deactivate
}

# Remove Conda's deactivate command (can be alias, function, or cmdlet)
Remove-Item Alias:deactivate -ErrorAction SilentlyContinue
Remove-Item Function:deactivate -ErrorAction SilentlyContinue

# Create a temporary deactivate function that accepts -nondestructive
# This overrides Conda's Exit-CondaEnvironment
function global:deactivate {
    param([switch]$nondestructive)
    # Do nothing - just a placeholder to avoid Conda conflict
}

# Activate the venv (this will replace our dummy deactivate with its own)
& "$PSScriptRoot\venv\Scripts\Activate.ps1"
