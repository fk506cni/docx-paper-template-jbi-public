@echo on
REM === Repair docx and convert to PDF using Word (debug mode) ===
REM
REM Usage:
REM   1. Drag and drop a .docx file onto this batch file
REM   2. Double-click: auto-selects the newest .docx in the same folder
REM
REM Requires: Microsoft Word installed

echo [DEBUG] Script started
echo [DEBUG] Batch file location: %~dp0
echo [DEBUG] Argument 1: "%~1"
echo [DEBUG] TEMP directory: %TEMP%
echo.

if not "%~1"=="" (
    set "INPUT=%~f1"
    echo [DEBUG] Using drag-and-drop input: %~f1
    goto :run
)

REM No argument -- find the newest .docx in the batch file directory
echo [DEBUG] No argument provided, searching for .docx files...
set "SEARCH_DIR=%~dp0"
echo [DEBUG] Search directory: %SEARCH_DIR%
set "INPUT="

for /f "delims=" %%F in ('dir /b /o-d /a-d "%SEARCH_DIR%*.docx" 2^>nul') do (
    if not defined INPUT (
        set "INPUT=%SEARCH_DIR%%%F"
        echo [DEBUG] Found docx: %%F
    )
)

if not defined INPUT (
    echo [ERROR] No .docx file found in %SEARCH_DIR%
    echo [DEBUG] dir listing of %SEARCH_DIR%:
    dir /b "%SEARCH_DIR%" 2>nul
    pause
    exit /b 1
)

:run
echo.
echo ============================================
echo [DEBUG] INPUT = %INPUT%
echo ============================================
echo.

REM Check if input file actually exists
if not exist "%INPUT%" (
    echo [ERROR] Input file does not exist: %INPUT%
    pause
    exit /b 1
)
echo [DEBUG] Input file exists: OK

REM Check PowerShell availability
echo [DEBUG] Checking PowerShell...
where powershell >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PowerShell not found in PATH
    pause
    exit /b 1
)
echo [DEBUG] PowerShell found: OK

REM Write embedded PowerShell script to temp file
set "PS1=%TEMP%\word-to-pdf_%RANDOM%.ps1"
echo [DEBUG] Temp PS1 path: %PS1%

echo [DEBUG] Writing PowerShell script to temp file...
echo param([Parameter(Mandatory=$true, Position=0)][string]$InputFile) > "%PS1%"
echo $InputFile = (Resolve-Path $InputFile).Path >> "%PS1%"
echo $OutputFile = [System.IO.Path]::ChangeExtension($InputFile, '.pdf') >> "%PS1%"
echo Write-Host "Input:  $InputFile" >> "%PS1%"
echo Write-Host "Output: $OutputFile" >> "%PS1%"
echo Write-Host '' >> "%PS1%"
echo $word = $null >> "%PS1%"
echo try { >> "%PS1%"
echo     $word = New-Object -ComObject Word.Application >> "%PS1%"
echo     $word.Visible = $false >> "%PS1%"
echo     $word.DisplayAlerts = 0 >> "%PS1%"
echo     Write-Host 'Opening and repairing...' >> "%PS1%"
echo     $doc = $word.Documents.Open($InputFile, $false, $false, $false, '', '', $false, '', '', 0, [Type]::Missing, $false, $true) >> "%PS1%"
echo     Write-Host 'Exporting as PDF...' >> "%PS1%"
rem --- ExportAsFixedFormat (OptimizeFor=Print) rather than SaveAs2 ---
rem   Keeps this tool on the same export path as watch-and-convert.ps1.
rem   SaveAs2 cannot state the export quality. Falls back to SaveAs2 on error.
echo     $exported = $false >> "%PS1%"
echo     try { >> "%PS1%"
echo         $doc.ExportAsFixedFormat($OutputFile, 17, $false, 0, 0, 1, 1, 0, $true, $true, 0, $true, $true, $false) >> "%PS1%"
echo         $exported = $true >> "%PS1%"
echo     } catch { >> "%PS1%"
echo         Write-Host 'ExportAsFixedFormat failed:' $_.Exception.Message -ForegroundColor Yellow >> "%PS1%"
echo     } >> "%PS1%"
echo     if (-not $exported) { $doc.SaveAs2($OutputFile, 17) } >> "%PS1%"
echo     $doc.Close($false) >> "%PS1%"
echo     Write-Host '' >> "%PS1%"
echo     Write-Host 'Done:' $OutputFile -ForegroundColor Green >> "%PS1%"
echo } catch { >> "%PS1%"
echo     Write-Host 'Error:' $_.Exception.Message -ForegroundColor Red >> "%PS1%"
echo     exit 1 >> "%PS1%"
echo } finally { >> "%PS1%"
echo     if ($word) { >> "%PS1%"
echo         $word.Quit() >> "%PS1%"
echo         [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) ^| Out-Null >> "%PS1%"
echo     } >> "%PS1%"
echo     [GC]::Collect() >> "%PS1%"
echo } >> "%PS1%"

echo [DEBUG] Temp PS1 written: OK
echo [DEBUG] Temp PS1 file size:
dir "%PS1%" 2>nul | findstr /i "word-to-pdf"
echo.

echo [DEBUG] Contents of generated PS1:
echo -------- PS1 START --------
type "%PS1%"
echo.
echo -------- PS1 END ----------
echo.

echo [DEBUG] Launching PowerShell...
echo [DEBUG] Command: powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" "%INPUT%"
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" "%INPUT%"
set "PS_EXIT=%ERRORLEVEL%"
echo.
echo [DEBUG] PowerShell exit code: %PS_EXIT%

del "%PS1%" 2>nul
echo [DEBUG] Temp PS1 cleaned up
echo.
echo [DEBUG] Script finished
pause
