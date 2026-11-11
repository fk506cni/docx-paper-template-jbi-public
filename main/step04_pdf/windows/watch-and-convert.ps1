<#
.SYNOPSIS
    Watches the script's folder for new .docx files and auto-converts them to PDF using Microsoft Word.

.DESCRIPTION
    This script runs as a persistent watcher. When a new .docx file appears in the
    same folder as this script, it waits for the file to become accessible (handling
    Google Drive sync locks), converts it to PDF via Word COM automation, and moves
    the original .docx into a "processed" subfolder.

    Designed for use with Google Drive sync folders where .docx files are delivered
    automatically and need to be converted to PDF without manual intervention.

    Each conversion runs in a separate PowerShell process working on a copy of the
    .docx in %TEMP%. The watcher waits for it with a time limit; if the limit is
    exceeded (Word hung on a dialog, etc.), it stops that process and the Word it
    started, moves the .docx to "error", and goes on with the next file.

.PARAMETER ConvertTimeoutSec
    Per-file conversion time limit in seconds (default: 120). Covers starting Word,
    opening the document and exporting the PDF.

.PARAMETER SimulateHang
    TEST ONLY. The converter sleeps after opening the document, so every conversion
    runs into the time limit. Used to check that the watcher stops only the Word it
    started. Never pass this from the .bat launcher.

.NOTES
    Requires: Microsoft Word installed on the machine.

    === How to Run ===

    Method 1: Right-click and "Run with PowerShell"
      - Right-click this file in Explorer -> "Run with PowerShell"
      - Note: The window may close on errors. Method 2 is recommended.

    Method 2: From a PowerShell terminal (RECOMMENDED)
      1. Open PowerShell (or Windows Terminal)
      2. Navigate to the folder containing this script:
             cd "C:\path\to\your\folder"
      3. If you've never run PowerShell scripts before, allow execution:
             Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
      4. Run the script:
             .\watch-and-convert.ps1
      5. The script will now watch for .docx files. Press Ctrl+C to stop.

    Method 3: Create a shortcut for one-click launch
      1. Right-click on the Desktop -> New -> Shortcut
      2. Enter as location:
             powershell -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\watch-and-convert.ps1"
      3. Name it "DOCX to PDF Watcher" and click Finish
      4. Double-click the shortcut to start watching.

    Test runs (non-default settings; close the window and use the .bat to go back):
        powershell -NoProfile -ExecutionPolicy Bypass -File .\watch-and-convert.ps1 -ConvertTimeoutSec 30 -SimulateHang

    === Folder Structure ===

    Place this script in the Google Drive sync folder:

        YourFolder/
        ├── watch-and-convert.ps1    <- this script
        ├── some-document.docx       <- new files appear here
        ├── some-document.pdf        <- PDF output stays here
        ├── .watcher-alive           <- liveness timestamp + settings, refreshed every 60s
        ├── watch-and-convert.log    <- log
        ├── processed/               <- converted .docx moved here (auto-created)
        └── error/                   <- failed .docx moved here (created only on failure)

    Work files live in %TEMP%\docx2pdf_<random>\ and are removed after each file.

    === Configuration ===

    Edit the variables in the "Configuration" region below to adjust:
      - $PollIntervalSec    : How often to check for new files (default: 5 seconds)
    The per-file time limit is the -ConvertTimeoutSec parameter (default: 120 seconds).
#>

#Requires -Version 5.1

param(
    [ValidateRange(1, 86400)]
    [int]$ConvertTimeoutSec = 120,

    [switch]$SimulateHang
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ============================================================================
#region Configuration
# ============================================================================

$PollIntervalSec = 5     # Polling interval in seconds

# Log file inside the watch folder. The real path is assigned in Main once
# $WatchDir is known. Declared here because Write-Log runs before that and
# Set-StrictMode makes an undefined variable a hard error.
$LogFile = $null

# Settings given on the command line that differ from a plain .bat launch.
# Shown in the banner and written to .watcher-alive, so that a test run left
# running is visible from the Linux side (scripts/check-pdf-path.sh).
$NonDefaultSettings = @()
if ($PSBoundParameters.ContainsKey('ConvertTimeoutSec')) {
    $NonDefaultSettings += "ConvertTimeoutSec=$ConvertTimeoutSec"
}
if ($SimulateHang) {
    $NonDefaultSettings += 'SimulateHang'
}

#endregion

# ============================================================================
#region Converter (runs in a child process, one per file)
# ============================================================================
#
# Why a child process: a COM call into a hung Word never returns, and nothing
# inside the same PowerShell process can interrupt it. Running the conversion
# in its own powershell.exe lets the watcher wait with a time limit and stop it.
#
# Why embedded here and written out per conversion (instead of a separate .ps1
# next to this one): the child always matches the running watcher, even if the
# .ps1 files in the synced folder are replaced while the watcher runs, and the
# set of files to deploy stays the same.
#
# Contract with the watcher. Everything lives in the child's own folder
# (%TEMP%\docx2pdf_<random>\), so the only argument is this script's path:
#   input      : the only *.docx in the folder
#   output     : <same name>.pdf in the folder
#   word.pid   : "<pid> <start time, UTC ticks>" of the WINWORD it started
#   convert.log: "HH:mm:ss<TAB>LEVEL<TAB>message" lines, UTF-8 (written line by
#                line, so the watcher can show how far a killed run got)
#   exit code  : 0 ok / 3 ok after repair / 20 cannot open / 21 export failed /
#                22 setup error / 23 Word automation failed (e.g. Word did not
#                start). Anything else is unexpected (e.g. 1 = crash).
#
# Keep this block ASCII only.

$ConverterScript = @'
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# Progress records would reach the redirected stderr as CLIXML noise.
$ProgressPreference = 'SilentlyContinue'

$here    = $PSScriptRoot
$logPath = Join-Path $here 'convert.log'
$pidPath = Join-Path $here 'word.pid'
$utf8    = New-Object System.Text.UTF8Encoding($false)

function Out-Log([string]$Level, [string]$Message) {
    $line = (Get-Date -Format 'HH:mm:ss') + "`t" + $Level + "`t" + ($Message -replace '[\r\n]+', ' ') + "`r`n"
    try { [System.IO.File]::AppendAllText($logPath, $line, $utf8) } catch { }
}

function Get-WordIds {
    @(Get-Process -Name 'WINWORD' -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
}

$docxFiles = @(Get-ChildItem -LiteralPath $here -Filter '*.docx' -File)
if ($docxFiles.Count -ne 1) {
    Out-Log 'ERROR' "Expected exactly one .docx in the work folder, found $($docxFiles.Count)"
    exit 22
}
$DocxPath = $docxFiles[0].FullName
$pdfPath  = [System.IO.Path]::ChangeExtension($DocxPath, '.pdf')
$leaf     = Split-Path $DocxPath -Leaf
$simulateHang = Test-Path -LiteralPath (Join-Path $here 'simulate-hang.flag')

$word = $null
$doc  = $null
$ownWord = $false
$code = 0

try {
    Out-Log 'INFO' 'Starting Word COM...'

    # Identify the WINWORD this script starts: COM launches it through the
    # DCOM service, so it is not a child of this process. Compare the WINWORD
    # list just before and just after the launch; only an unambiguous single
    # new process is recorded. Without a record the watcher will not
    # force-stop any Word for this file.
    $before = @(Get-WordIds)
    $word = New-Object -ComObject Word.Application
    $new = @(Get-Process -Name 'WINWORD' -ErrorAction SilentlyContinue |
             Where-Object { $before -notcontains $_.Id })
    if ($new.Count -eq 0) {
        # Connected to a Word that was already running (it may hold documents the
        # user is working on). Stop here without touching it: do not hide its
        # window, change its alert setting, open a document in it, or Quit it.
        # The watcher leaves the .docx in place and retries on a later cycle.
        Out-Log 'ERROR' 'No new WINWORD appeared (attached to a Word that was already running?). Stopping without touching it.'
        $code = 24
    } else {
        $ownWord = $true   # the COM reference is ours
        # Record the PID only when it is unambiguous: exactly one new WINWORD,
        # and it has no window (Word started for automation is windowless; a
        # Word the user starts at the same moment would have one). Without a
        # record the watcher will not force-stop any Word for this file.
        $windowless = @($new | Where-Object { $_.MainWindowHandle -eq [IntPtr]::Zero })
        if ($new.Count -eq 1 -and $windowless.Count -eq 1) {
            try {
                $ticks = $new[0].StartTime.ToUniversalTime().Ticks
                [System.IO.File]::WriteAllText($pidPath, "$($new[0].Id) $ticks", $utf8)
                Out-Log 'INFO' "Word process: PID $($new[0].Id)"
            } catch {
                Out-Log 'WARN' "Could not record the Word process: $($_.Exception.Message)"
            }
        } else {
            Out-Log 'WARN' "$($new.Count) new WINWORD processes appeared ($($windowless.Count) without a window); cannot tell which is ours. None will be force-stopped."
        }
    }

  if ($code -eq 0) {
    $word.Visible = $false
    $word.DisplayAlerts = 0  # wdAlertsNone

    # Documents.Open parameters:
    #   FileName, ConfirmConversions, ReadOnly, AddToRecentFiles,
    #   PasswordDocument, PasswordTemplate, Revert,
    #   WritePasswordDocument, WritePasswordTemplate, Format,
    #   Encoding, Visible, OpenAndRepair
    #
    # Two-stage open: plain first, OpenAndRepair only when that fails.
    # Repairing unconditionally would hide whether the generated docx opens in
    # Word without repair, which is worth knowing (hand-built OOXML: text boxes,
    # embedded SVG, diff highlighting). Exit code 3 reports that repair was needed.
    $repaired = $false
    Out-Log 'INFO' "Opening: $leaf"
    try {
        $doc = $word.Documents.Open(
            $DocxPath, $false, $false, $false, '', '', $false, '', '', 0,
            [Type]::Missing, $false,
            $false              # OpenAndRepair
        )
    } catch {
        Out-Log 'WARN' "Plain open failed: $($_.Exception.Message)"
        $doc = $null
    }
    if (-not $doc) {
        Out-Log 'WARN' "Retrying with OpenAndRepair: $leaf"
        try {
            $doc = $word.Documents.Open(
                $DocxPath, $false, $false, $false, '', '', $false, '', '', 0,
                [Type]::Missing, $false,
                $true           # OpenAndRepair
            )
            $repaired = $true
        } catch {
            Out-Log 'ERROR' "Cannot open even with OpenAndRepair: $($_.Exception.Message)"
            $code = 20
        }
    }

    if ($code -eq 0) {
        if ($simulateHang) {
            Out-Log 'WARN' 'SimulateHang: sleeping with the document open until the watcher times out'
            Start-Sleep -Seconds 86400
        }

        # --- Diagnostics: what can influence raster image resolution ----------
        # A raster figure can land in the PDF at a lower resolution than the PNG
        # embedded in the docx (observed: 200 ppi from a 600 dpi PNG). Setting
        # <w:doNotAutoCompressPictures/> in the document did NOT stop it.
        # This block only READS. It writes nothing to the registry or to Word's
        # settings; it exists so the Linux side can see what levers are available.
        try {
            Out-Log 'INFO' "Word version: $($word.Version) / Build: $($word.Build)"
            $optNames = @($word.Options | Get-Member -MemberType Property |
                          Where-Object { $_.Name -match 'Compress|Dpi|Image|Picture|Graphic' } |
                          ForEach-Object { $_.Name })
            if ($optNames.Count -gt 0) {
                foreach ($n in $optNames) {
                    $v = '(unreadable)'
                    try { $v = $word.Options.$n } catch { }
                    Out-Log 'INFO' "  Options.$n = $v"
                }
            } else {
                Out-Log 'INFO' '  Options exposes no image/compression property'
            }
        } catch {
            Out-Log 'WARN' "Diagnostics failed: $($_.Exception.Message)"
        }

        Out-Log 'INFO' 'Exporting as PDF...'
        # ExportAsFixedFormat rather than SaveAs2($pdfPath, 17):
        #   SaveAs2 cannot state the export quality; it leaves it to Word's default.
        #   ExportAsFixedFormat lets OptimizeFor be given explicitly:
        #     wdExportOptimizeForPrint (0)    = "Standard (publishing online and printing)"
        #     wdExportOptimizeForOnScreen (1) = "Minimum size"
        # Argument order: OutputFileName, ExportFormat, OpenAfterExport, OptimizeFor,
        #   Range, From, To, Item, IncludeDocProps, KeepIRM, CreateBookmarks,
        #   DocStructureTags, BitmapMissingFonts, UseISO19005_1
        # Keep BitmapMissingFonts = $true (the default). Setting it $false can let a
        # typeface be substituted, which changes the typeset result.
        $exported = $false
        try {
            $doc.ExportAsFixedFormat(
                $pdfPath,   # OutputFileName
                17,         # ExportFormat = wdExportFormatPDF
                $false,     # OpenAfterExport
                0,          # OptimizeFor = wdExportOptimizeForPrint
                0,          # Range = wdExportAllDocument
                1,          # From
                1,          # To
                0,          # Item = wdExportDocumentContent
                $true,      # IncludeDocProps
                $true,      # KeepIRM
                0,          # CreateBookmarks = wdExportCreateNoBookmarks
                $true,      # DocStructureTags
                $true,      # BitmapMissingFonts
                $false      # UseISO19005_1
            )
            $exported = $true
            Out-Log 'OK' 'Exported with ExportAsFixedFormat (OptimizeFor=Print)'
        } catch {
            # Falling back is deliberate: no PDF at all is worse than a default one.
            Out-Log 'WARN' "ExportAsFixedFormat failed: $($_.Exception.Message)"
        }
        if (-not $exported) {
            Out-Log 'WARN' 'Falling back to SaveAs2'
            try {
                $doc.SaveAs2($pdfPath, 17)
            } catch {
                Out-Log 'ERROR' "SaveAs2 failed: $($_.Exception.Message)"
                $code = 21
            }
        }
        try { $doc.Close($false) } catch { }

        if ($code -eq 0 -and $repaired) { $code = 3 }
    }
  }

} catch {
    Out-Log 'ERROR' "Word conversion failed: $($_.Exception.Message)"
    if ($code -eq 0) { $code = 23 }

} finally {
    # Thorough COM cleanup to prevent orphan WINWORD.exe processes
    if ($doc) {
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null } catch { }
    }
    if ($word) {
        if ($ownWord) {
            try { $word.Quit() } catch { }
        }
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null } catch { }
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

exit $code
'@

#endregion

# ============================================================================
#region Helper Functions
# ============================================================================

function Write-Log {
    param(
        [string]$Message,
        [ValidateSet('INFO','WARN','ERROR','OK')]
        [string]$Level = 'INFO'
    )
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $color = switch ($Level) {
        'INFO'  { 'Cyan' }
        'WARN'  { 'Yellow' }
        'ERROR' { 'Red' }
        'OK'    { 'Green' }
    }
    Write-Host "[$timestamp] " -NoNewline -ForegroundColor DarkGray
    Write-Host "[$Level] " -NoNewline -ForegroundColor $color
    Write-Host $Message

    # Also append to a log file in the watch folder.
    # Diagnostics shown only in this console window cannot be read from the
    # Linux side. The watch folder is synced by Google Drive, so a log written
    # here comes back with the PDF.
    # Lines are emitted at startup and per conversion only -- never per poll
    # (same consideration as .watcher-alive: do not make the sync client churn).
    # A failure to log must never break a conversion.
    if ($script:LogFile) {
        try {
            Add-Content -Path $script:LogFile -Encoding UTF8 -ErrorAction Stop `
                -Value "[$timestamp] [$Level] $Message"
        } catch { }
    }
}

function Write-AliveMarker {
    <#
    .SYNOPSIS
        Stamps .watcher-alive (throttled to once per $AliveIntervalSec).
        Line 1 is the timestamp; the following key=value lines tell the Linux
        side which script and which settings this watcher runs with.
    #>
    param([switch]$Force)
    if (-not $Force -and ((Get-Date) - $script:LastAliveWrite).TotalSeconds -lt $script:AliveIntervalSec) {
        return
    }
    try {
        $lines = @(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz') + $script:AliveMeta
        Set-Content -Path $script:AliveFile -Encoding ASCII -ErrorAction Stop -Value $lines
        $script:LastAliveWrite = Get-Date
    } catch {
        # Never let the marker break conversion: a locked/synced file is not fatal.
    }
}

function Test-FileReady {
    <#
    .SYNOPSIS
        Tests whether a file can be opened exclusively (i.e., not locked by another process).
    #>
    param([string]$Path)
    try {
        $stream = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::None
        )
        $stream.Close()
        $stream.Dispose()
        return $true
    } catch {
        return $false
    }
}

function Get-WordIds {
    @(Get-Process -Name 'WINWORD' -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
}

function Find-OwnWord {
    <#
    .SYNOPSIS
        Returns the WINWORD process started by one conversion, or $null.
        Never guesses: when it cannot be told apart, nothing is returned, so a
        Word the user is working in is never stopped.
    .PARAMETER WordBefore
        WINWORD PIDs taken just before the converter was started. Used only as a
        fallback when the converter did not record its Word (it hung while Word
        was starting). Omit it to use the recorded PID only.
    #>
    param(
        [string]$PidFile,
        [int[]]$WordBefore
    )

    # 1. The PID recorded by the converter, if it still is that same process
    #    (same start time: a reused PID must not be stopped). Up to 1 second of
    #    difference is accepted: on some platforms the start time is derived
    #    afresh on every read and two processes can see slightly different
    #    values, while a PID being reused within a second is not a real case.
    if (Test-Path -LiteralPath $PidFile) {
        $parts = @(([System.IO.File]::ReadAllText($PidFile)).Trim() -split '\s+')
        if ($parts.Count -eq 2) {
            $p = Get-Process -Id ([int]$parts[0]) -ErrorAction SilentlyContinue
            if (-not $p) {
                if ($PSBoundParameters.ContainsKey('WordBefore')) {
                    Write-Log "Word (PID $($parts[0])) has already exited" 'INFO'
                }
                return $null
            }
            $ticks = $null
            try { $ticks = $p.StartTime.ToUniversalTime().Ticks } catch { }
            if ($p.ProcessName -eq 'WINWORD' -and $null -ne $ticks -and
                [Math]::Abs($ticks - [int64]$parts[1]) -le [TimeSpan]::TicksPerSecond) {
                return $p
            }
            Write-Log "PID $($parts[0]) is no longer the Word this conversion started (process $($p.ProcessName), start time differs); not stopping it" 'WARN'
            return $null
        }
    }
    if (-not $PSBoundParameters.ContainsKey('WordBefore')) {
        return $null
    }

    # 2. Fallback: exactly one WINWORD appeared since the converter started, and
    #    it has no window (a Word the user opens has one). Look twice: a Word
    #    whose launch was under way when the converter was stopped can appear
    #    a moment later and would otherwise be left running.
    for ($i = 0; $i -lt 2; $i++) {
        $new = @(Get-Process -Name 'WINWORD' -ErrorAction SilentlyContinue |
                 Where-Object { $WordBefore -notcontains $_.Id })
        if ($new.Count -gt 0) { break }
        Start-Sleep -Seconds 3
    }
    if ($new.Count -eq 0) {
        Write-Log 'No Word process was left by this conversion' 'INFO'
        return $null
    }
    $windowless = @($new | Where-Object { $_.MainWindowHandle -eq [IntPtr]::Zero })
    if ($new.Count -eq 1 -and $windowless.Count -eq 1) {
        Write-Log "Word process identified by elimination: PID $($windowless[0].Id)" 'INFO'
        return $windowless[0]
    }
    Write-Log "Cannot tell which WINWORD this conversion started ($($new.Count) new, $($windowless.Count) without a window); stopping none" 'WARN'
    Write-Log '  -> If a WINWORD.EXE without a window remains, end it in Task Manager' 'WARN'
    return $null
}

function Stop-OwnWord {
    param([System.Diagnostics.Process]$Process, [string]$Reason)
    try {
        if ($Process.HasExited) { return }
        $Process.Kill()
        $null = $Process.WaitForExit(15000)
        Write-Log "Stopped WINWORD PID $($Process.Id) ($Reason)" 'WARN'
    } catch {
        Write-Log "Could not stop WINWORD PID $($Process.Id): $($_.Exception.Message)" 'ERROR'
    }
}

function Stop-Converter {
    <#
    .SYNOPSIS
        Stops a converter that is still running, then the Word it started.
    #>
    param(
        [System.Diagnostics.Process]$Proc,
        [string]$PidFile,
        [int[]]$WordBefore
    )
    try {
        if (-not $Proc.HasExited) {
            $Proc.Kill()
            $null = $Proc.WaitForExit(10000)
        }
    } catch {
        Write-Log "Could not stop the converter process: $($_.Exception.Message)" 'ERROR'
    }
    $own = Find-OwnWord -PidFile $PidFile -WordBefore $WordBefore
    if ($own) {
        Stop-OwnWord -Process $own -Reason 'started by the stopped conversion'
    }
}

function Write-ConverterLog {
    <#
    .SYNOPSIS
        Copies the converter's log lines into this window and the log file.
    #>
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $lines = @()
    try { $lines = [System.IO.File]::ReadAllLines($Path, [System.Text.Encoding]::UTF8) } catch { return }
    foreach ($line in $lines) {
        if (-not $line) { continue }
        $f = $line -split "`t", 3
        if ($f.Count -eq 3 -and @('INFO','WARN','ERROR','OK') -contains $f[1]) {
            Write-Log "  ($($f[0])) $($f[2])" $f[1]
        } else {
            Write-Log "  $line" 'INFO'
        }
    }
}

function Remove-TempDir {
    param([string]$Path)
    for ($i = 1; $i -le 5; $i++) {
        if (-not (Test-Path -LiteralPath $Path)) { return }
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (Test-Path -LiteralPath $Path) {
        Write-Log "Could not remove the work folder (remove it later): $Path" 'WARN'
    }
}

function Clear-StaleTempDirs {
    <#
    .SYNOPSIS
        Removes work folders left behind when a watcher itself was killed.
        Only folders older than an hour are touched (far longer than any
        conversion), so another watcher's folder in use is never removed.
    #>
    $cutoff = (Get-Date).AddHours(-1)
    $stale = @(Get-ChildItem -LiteralPath $env:TEMP -Directory -Filter 'docx2pdf_*' -ErrorAction SilentlyContinue |
               Where-Object { $_.LastWriteTime -lt $cutoff })
    $removed = 0
    foreach ($d in $stale) {
        try {
            Remove-Item -LiteralPath $d.FullName -Recurse -Force -ErrorAction Stop
            $removed++
        } catch { }
    }
    if ($removed -gt 0) {
        Write-Log "Removed $removed stale work folder(s) from %TEMP%" 'INFO'
    }
    if ($removed -lt $stale.Count) {
        Write-Log "$($stale.Count - $removed) stale work folder(s) in %TEMP% could not be removed (docx2pdf_*)" 'WARN'
    }
}

function Convert-DocxToPdf {
    <#
    .SYNOPSIS
        Converts one .docx to PDF in a child process with a time limit.
        The .docx is copied to %TEMP% and converted there (away from Google
        Drive's sync locks); only the finished PDF is copied next to the .docx.
        Returns the PDF path, or $null on failure or timeout.
    #>
    param(
        [string]$DocxPath,
        [string]$OutputDir
    )

    $fileName = Split-Path $DocxPath -Leaf
    $pdfName  = [System.IO.Path]::ChangeExtension($fileName, '.pdf')
    $pdfPath  = Join-Path $OutputDir $pdfName

    $tempDir   = Join-Path $env:TEMP ('docx2pdf_' + [System.IO.Path]::GetRandomFileName().Replace('.', ''))
    $tempDocx  = Join-Path $tempDir $fileName
    $tempPdf   = Join-Path $tempDir $pdfName
    $childPs1  = Join-Path $tempDir 'convert.ps1'
    $childLog  = Join-Path $tempDir 'convert.log'
    $pidFile   = Join-Path $tempDir 'word.pid'
    $stderrTxt = Join-Path $tempDir 'stderr.txt'

    $proc = $null
    $wordBefore = @()
    $handled = $false   # set once the converter's end (or timeout) has been dealt with

    try {
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
        # Remember the source as it was when copied, to notice a replacement
        # (a newer push of the same name) that arrives while Word is converting.
        $srcBefore = Get-Item -LiteralPath $DocxPath
        Copy-Item -LiteralPath $DocxPath -Destination $tempDocx -Force
        try { Unblock-File -LiteralPath $tempDocx } catch { }
        [System.IO.File]::WriteAllText($childPs1, $script:ConverterScript, (New-Object System.Text.UTF8Encoding($true)))
        if ($script:SimulateHang) {
            Set-Content -LiteralPath (Join-Path $tempDir 'simulate-hang.flag') -Value 'test' -Encoding ASCII
        }
        Write-Log "Work folder: $tempDir" 'INFO'

        # Same PowerShell as this watcher (powershell.exe, or pwsh.exe if started from it).
        $hostExe = (Get-Process -Id $PID).Path
        $wordBefore = @(Get-WordIds)
        # Start-Process does not quote array elements, hence the explicit quotes.
        $proc = Start-Process -FilePath $hostExe `
            -ArgumentList @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', "`"$childPs1`"") `
            -NoNewWindow -PassThru `
            -RedirectStandardOutput (Join-Path $tempDir 'stdout.txt') `
            -RedirectStandardError $stderrTxt
        # Touch .Handle so that ExitCode is populated after WaitForExit
        # (PowerShell quirk with Start-Process -PassThru without -Wait).
        $null = $proc.Handle

        # Wait in short slices so that .watcher-alive keeps being refreshed
        # while Word works (the marker is throttled to once a minute inside).
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $limitMs = [int64]$script:ConvertTimeoutSec * 1000
        $timedOut = $false
        while ($true) {
            $remaining = $limitMs - $sw.ElapsedMilliseconds
            if ($remaining -le 0) { $timedOut = $true; break }
            if ($proc.WaitForExit([int][Math]::Min(5000, $remaining))) { break }
            Write-AliveMarker
        }
        $sw.Stop()

        if ($timedOut) {
            Write-Log "TIMEOUT: not finished within $($script:ConvertTimeoutSec)s: $fileName" 'ERROR'
            Write-ConverterLog -Path $childLog      # shows how far it got
            Stop-Converter -Proc $proc -PidFile $pidFile -WordBefore $wordBefore
            $handled = $true
            return $null
        }

        $exitCode = $proc.ExitCode
        Write-ConverterLog -Path $childLog
        if ((Test-Path -LiteralPath $stderrTxt) -and (Get-Item -LiteralPath $stderrTxt).Length -gt 0) {
            Write-Log "Converter stderr: $((Get-Content -LiteralPath $stderrTxt -Raw).Trim())" 'WARN'
        }
        Write-Log "Converter finished in $([Math]::Round($sw.Elapsed.TotalSeconds, 1))s (exit code $exitCode)" 'INFO'

        # Word normally exits right after the converter quits it. If it is still
        # there after a grace period, stop it -- only when it is provably ours.
        $left = Find-OwnWord -PidFile $pidFile
        if ($left -and -not $left.WaitForExit(15000)) {
            Stop-OwnWord -Process $left -Reason 'did not quit after the conversion'
        }
        $handled = $true

        switch ($exitCode) {
            0  { }
            3  {
                # The PDF exists, so carry on -- but this says the generated docx
                # has something Word had to repair, which is worth seeing.
                Write-Log "REPAIRED: plain open failed and OpenAndRepair was needed: $fileName" 'WARN'
                Write-Log '  -> The PDF was made, but the docx has a structural problem Word had to fix. Suspect hand-built OOXML (text boxes / embedded SVG / diff highlighting).' 'WARN'
            }
            20 { Write-Log "OPEN_ERROR: Word cannot open the docx even with OpenAndRepair: $fileName" 'ERROR'; return $null }
            21 { Write-Log "EXPORT_ERROR: Word could not write the PDF: $fileName" 'ERROR'; return $null }
            22 { Write-Log "SETUP_ERROR: the converter could not find its input: $fileName" 'ERROR'; return $null }
            23 { Write-Log "WORD_ERROR: Word automation failed (see the converter log above): $fileName" 'ERROR'; return $null }
            24 {
                Write-Log "ATTACHED: Word automation connected to a Word that was already running; stopped without touching it: $fileName" 'WARN'
                Write-Log '  -> The docx stays where it is and is retried on a later cycle (close the Word windows on this PC if it keeps happening).' 'WARN'
                $script:RetryLater = $true
                return $null
            }
            default { Write-Log "Converter ended unexpectedly (exit code $exitCode): $fileName" 'ERROR'; return $null }
        }

        if (-not (Test-Path -LiteralPath $tempPdf) -or (Get-Item -LiteralPath $tempPdf).Length -eq 0) {
            Write-Log "PDF was not created: $pdfName" 'ERROR'
            return $null
        }
        # The PDF belongs to the docx that was copied. If the source was replaced
        # meanwhile, returning this PDF would hand an older version back as the
        # new one; leave both the PDF and the docx alone and convert again later.
        $srcNow = Get-Item -LiteralPath $DocxPath -ErrorAction SilentlyContinue
        if (-not $srcNow -or $srcNow.Length -ne $srcBefore.Length -or
                $srcNow.LastWriteTimeUtc -ne $srcBefore.LastWriteTimeUtc) {
            Write-Log "CHANGED: $fileName was replaced while it was being converted; the PDF of the old one is discarded" 'WARN'
            $script:RetryLater = $true
            return $null
        }
        try {
            Copy-Item -LiteralPath $tempPdf -Destination $pdfPath -Force
        } catch {
            Write-Log "Could not write $pdfName to the watch folder (open in a PDF viewer?): $($_.Exception.Message)" 'ERROR'
            return $null
        }
        Write-Log "PDF created: $pdfName" 'OK'
        return $pdfPath

    } catch {
        Write-Log "Conversion failed: $($_.Exception.Message)" 'ERROR'
        return $null

    } finally {
        # Also reached on Ctrl+C or an unexpected error while the converter ran.
        # Ctrl+C reaches the converter too (same console), but not the Word it
        # started, so stop that Word here.
        if ($proc -and -not $handled) {
            Stop-Converter -Proc $proc -PidFile $pidFile -WordBefore $wordBefore
        }
        Remove-TempDir -Path $tempDir
    }
}

function Move-ToFolder {
    <#
    .SYNOPSIS
        Moves a file into a subfolder (created if needed; a timestamp is added
        on a name collision). Returns the new name, or $null when the source is
        already gone or the move fails -- never throws, so that one file cannot
        stop the watcher.
    #>
    param(
        [string]$FilePath,
        [string]$DestDir,
        [string]$Label
    )
    if (-not (Test-Path -LiteralPath $FilePath)) {
        Write-Log "Source already gone (moved or deleted by someone else?): $(Split-Path $FilePath -Leaf)" 'WARN'
        return $null
    }
    try {
        if (-not (Test-Path -LiteralPath $DestDir)) {
            New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
            Write-Log "Created folder: $Label/" 'INFO'
        }
        $fileName = Split-Path $FilePath -Leaf
        $destPath = Join-Path $DestDir $fileName
        if (Test-Path -LiteralPath $destPath) {
            $baseName  = [System.IO.Path]::GetFileNameWithoutExtension($fileName)
            $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
            $newName   = "${baseName}_${timestamp}.docx"
            $destPath  = Join-Path $DestDir $newName
        }
        Move-Item -LiteralPath $FilePath -Destination $destPath -Force
        return (Split-Path $destPath -Leaf)
    } catch {
        Write-Log "Could not move the docx to ${Label}/: $($_.Exception.Message)" 'WARN'
        return $null
    }
}

#endregion

# ============================================================================
#region Main
# ============================================================================

# Resolve the watch directory (= directory where this script lives)
$WatchDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProcessedDir = Join-Path $WatchDir 'processed'
$ErrorDir     = Join-Path $WatchDir 'error'

# --- Liveness marker ------------------------------------------------------
# The Linux side has no way to tell whether this window is still open, yet
# scripts/roundtrip.sh needs the watcher running. Stamp a timestamp into
# .watcher-alive so that scripts/check-pdf-path.sh and roundtrip.sh can report
# liveness without sending a docx.
# Written at most once per $AliveIntervalSec (NOT every poll) to keep the
# Google Drive client from syncing a tiny file every few seconds. Also written
# while a conversion runs, so a long conversion does not look like a dead watcher.
#
# Lines after the timestamp (key=value; readers of line 1 are unaffected):
#   script_md5          : MD5 of this .ps1 as read at startup. A running watcher
#                         keeps the script it started with, so this tells the
#                         Linux side whether a pushed update is actually running.
#   convert_timeout_sec : per-file time limit in effect
#   nondefault          : command-line settings a plain .bat launch would not have
$LogFile          = Join-Path $WatchDir 'watch-and-convert.log'
$AliveFile        = Join-Path $WatchDir '.watcher-alive'
$AliveIntervalSec = 60
$LastAliveWrite   = [DateTime]::MinValue

$ScriptMd5 = 'unknown'
try {
    $ScriptMd5 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm MD5).Hash.ToLowerInvariant()
} catch { }
$NonDefaultText = 'none'
if ($NonDefaultSettings.Count -gt 0) { $NonDefaultText = $NonDefaultSettings -join ',' }
$AliveMeta = @(
    "script_md5=$ScriptMd5",
    "convert_timeout_sec=$ConvertTimeoutSec",
    "nondefault=$NonDefaultText"
)

# Banner
Write-Host ''
Write-Host '========================================================' -ForegroundColor White
Write-Host '  DOCX -> PDF  Auto-Converter (Folder Watcher)' -ForegroundColor White
Write-Host '========================================================' -ForegroundColor White
Write-Host ''
Write-Log "Watch folder : $WatchDir" 'INFO'
Write-Log "Processed to : $ProcessedDir" 'INFO'
Write-Log "Error to     : $ErrorDir" 'INFO'
Write-Log "Poll interval: ${PollIntervalSec}s" 'INFO'
Write-Log "Timeout      : ${ConvertTimeoutSec}s per file" 'INFO'
Write-Log "Work folders : $env:TEMP\docx2pdf_*" 'INFO'
Write-Log "Alive marker : $AliveFile (every ${AliveIntervalSec}s)" 'INFO'
Write-Log "Log file     : $LogFile" 'INFO'
Write-Log "Script MD5   : $ScriptMd5" 'INFO'
if ($NonDefaultSettings.Count -gt 0) {
    Write-Log "NON-DEFAULT SETTINGS: $NonDefaultText" 'WARN'
    Write-Log '  -> For normal use, close this window and start watch-and-convert.bat' 'WARN'
}
Clear-StaleTempDirs
Write-Host ''
Write-Log "Watching for .docx files... Press Ctrl+C to stop." 'INFO'
Write-Host ''

# Stamp immediately so the Linux side sees liveness without waiting a full interval.
Write-AliveMarker -Force

# --- Stateless polling loop ---
# Every cycle, scan the watch folder for ALL .docx files.
#   - Locked files  -> skip (will be retried next cycle automatically)
#   - Convert OK    -> move to processed/
#   - Convert FAIL  -> move to error/
# Each file is handled inside its own try/catch, so an unexpected error on one
# file is logged and the loop goes on. The outer try/finally only reports
# "Watcher stopped." on Ctrl+C or when the watcher itself is terminated.
try {
    while ($true) {
        Write-AliveMarker    # throttled internally to $AliveIntervalSec

        $currentFiles = Get-ChildItem -Path $WatchDir -Filter '*.docx' -File -ErrorAction SilentlyContinue

        foreach ($file in $currentFiles) {
            # Skip temporary Word files (~$*.docx)
            if ($file.Name -like '~`$*') {
                continue
            }

            try {
                $filePath = $file.FullName

                # Check file lock (single attempt -- no blocking wait)
                if (-not (Test-FileReady -Path $filePath)) {
                    Write-Log "Locked (sync in progress?): $($file.Name) -- will retry next cycle" 'WARN'
                    continue
                }

                # File is ready -- process it
                Write-Host ''
                Write-Host '--------------------------------------------------------' -ForegroundColor DarkCyan
                Write-Log "Processing: $($file.Name)" 'INFO'

                $script:RetryLater = $false
                $pdfResult = Convert-DocxToPdf -DocxPath $filePath -OutputDir $WatchDir

                if (-not $pdfResult -and $script:RetryLater) {
                    Write-Log "Left in place for a later cycle: $($file.Name)" 'WARN'
                } elseif ($pdfResult) {
                    $movedName = Move-ToFolder -FilePath $filePath -DestDir $ProcessedDir -Label 'processed'
                    if ($movedName) {
                        Write-Log "Moved docx to: processed/$movedName" 'OK'
                    } else {
                        Write-Log 'PDF is done; the docx could not be moved (harmless, it may be converted again)' 'WARN'
                    }
                } else {
                    $movedName = Move-ToFolder -FilePath $filePath -DestDir $ErrorDir -Label 'error'
                    if ($movedName) {
                        Write-Log "Moved failed docx to: error/$movedName" 'ERROR'
                    } else {
                        Write-Log 'The failed docx could not be moved to error/ either' 'ERROR'
                    }
                }

                Write-Host '--------------------------------------------------------' -ForegroundColor DarkCyan
                Write-Host ''
            } catch {
                Write-Log "Unhandled error on $($file.Name): $($_.Exception.Message)" 'ERROR'
                Write-Log "  $($_.ScriptStackTrace)" 'ERROR'
                Write-Host '--------------------------------------------------------' -ForegroundColor DarkCyan
                Write-Host ''
            }
        }

        Start-Sleep -Seconds $PollIntervalSec
    }
} finally {
    Write-Log "Watcher stopped." 'WARN'
}

#endregion
