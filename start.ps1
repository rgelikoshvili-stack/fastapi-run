# Load from .env
Get-Content .env | ForEach-Object {
    if ($_ -match "^([^=]+)=(.+)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}
python -m uvicorn main:app --reload
