$ErrorActionPreference = "Stop"

Write-Host "1/3 Verify environment"
python tools/verify_environment.py

Write-Host ""
Write-Host "2/3 Static book code audit"
python tools/audit_book_code.py

Write-Host ""
Write-Host "3/3 Warning-enabled full render"
python tools/audit_book_code.py --render
