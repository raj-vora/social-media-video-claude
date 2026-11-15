# Exports each chart .pptx to an .mp4 through PowerPoint's own video export (no
# screen recording), then grabs the final frame as the freeze-frame still the
# CapCut drafts hold on once the animation ends.
#
#   pptx/<name>.pptx -> ppt_videos/<name>.mp4 (1080x1920, 30fps)
#                    -> ppt_videos/stills/<NN>_<chart>_last_frame.png
#
# Usage (from the repo root):
#   powershell -File invit-analysis-2026/assets/charts/generator/export_chart_videos.ps1 [-Only 02_] [-Seconds 10] [-Force] [-Wide]
#
# -Wide exports the 16:9 <name>_wide.pptx charts (generate_charts.ps1 -Wide) at 1920x1080
# instead, with stills named <NN>_<chart>_wide_last_frame.png. In the long form a chart
# sits under VO that is already giving its numbers, so wide exports play at
# -WideSpeed (1.8x), minus PowerPoint's black lead-in (-WideTrim, seconds after the
# speed-up): the title is up at once and the bars within about a second.
#
# Existing videos are skipped unless -Force. 01_* were screen-recorded by hand
# (608x1080) and are referenced by the hand-finished Indus EN draft; re-exporting
# them changes their resolution and length, so leave them unless you mean to.
param(
  [string]$Only = '',
  [int]$Seconds = 10,
  [switch]$Force,
  [switch]$Wide,
  [double]$WideSpeed = 1.8,
  [double]$WideTrim = 1.1
)
$ErrorActionPreference = 'Stop'

$charts = Split-Path $PSScriptRoot -Parent
$pptxDir = Join-Path $charts 'pptx'
$videoDir = Join-Path $charts 'ppt_videos'
$stillDir = Join-Path $videoDir 'stills'
New-Item -ItemType Directory -Force $stillDir | Out-Null

$files = Get-ChildItem $pptxDir -Filter '*.pptx' | Where-Object { $_.Name -like "*$Only*" -and ($_.BaseName -like '*_wide') -eq [bool]$Wide }
$vertRes = if ($Wide) { 1080 } else { 1920 }
$app = New-Object -ComObject PowerPoint.Application
try {
  foreach ($f in $files) {
    $out = Join-Path $videoDir ($f.BaseName + '.mp4')
    if ((Test-Path $out) -and -not $Force) { Write-Host "SKIP $($f.BaseName) (exists; -Force to redo)"; continue }

    $raw = Join-Path $env:TEMP ($f.BaseName + '_raw.mp4')
    $pres = $app.Presentations.Open($f.FullName, $true, $false, $false)  # read-only, no window
    try {
      # CreateVideo(file, useTimings, slideSeconds, vertRes, fps, quality). On-click
      # effects fire on their own in the export, so the whole sequence plays.
      $pres.CreateVideo($raw, $false, $Seconds, $vertRes, 30, 100)
      $waited = 0
      while ($pres.CreateVideoStatus -in 1, 2) {  # queued / in progress
        Start-Sleep -Seconds 1
        if (++$waited -gt 600) { throw "export of $($f.Name) timed out" }
      }
      if ($pres.CreateVideoStatus -ne 3) { throw "export of $($f.Name) failed (status $($pres.CreateVideoStatus))" }
    } finally { $pres.Close() }

    # PowerPoint leaves the colour metadata as "reserved", which ffmpeg refuses to
    # scale; tag it bt709 without re-encoding.
    ffmpeg -v error -y -i $raw -c copy -bsf:v 'h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1' $out
    if ($LASTEXITCODE) { throw "ffmpeg remux of $($f.Name) failed" }
    Remove-Item $raw
    if ($Wide -and $WideSpeed -ne 1) {
      $fast = Join-Path $env:TEMP ($f.BaseName + '_fast.mp4')
      ffmpeg -v error -y -i $out -vf "setpts=PTS/$WideSpeed" -ss $WideTrim -an -c:v libx264 -crf 16 -preset medium $fast
      if ($LASTEXITCODE) { throw "speed-up of $($f.Name) failed" }
      Move-Item -Force $fast $out
    }

    # 02_powergrid_invit_return_breakdown -> 02_return_breakdown_last_frame.png
    $kind = if ($f.BaseName -like '*return_breakdown*') { 'return_breakdown' } else { 'yearly_track_record' }
    if ($Wide) { $kind += '_wide' }
    $still = Join-Path $stillDir ('{0}_{1}_last_frame.png' -f $f.BaseName.Substring(0, 2), $kind)
    ffmpeg -v error -y -sseof -0.5 -i $out -update 1 -frames:v 1 $still
    if ($LASTEXITCODE) { throw "still extraction for $($f.Name) failed" }
    Write-Host "OK   $($f.BaseName).mp4 + $(Split-Path $still -Leaf)"
  }
} finally { $app.Quit() }
