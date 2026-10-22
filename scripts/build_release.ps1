<#
.SYNOPSIS
    构建可脱离环境的 Windows 便携版（PyInstaller onedir + 可选内置 Chromium）。

.DESCRIPTION
    完整版：把 Playwright 的 Chromium 放进 playwright 包目录下的 .local-browsers，
            PyInstaller 通过 collect_all('playwright') 一并打包，目标机无需浏览器。
    精简版：构建期间把 .local-browsers 临时移开，产物依赖目标机的 Edge / Chrome。

    浏览器来源优先级：
      1. 包目录下已存在的 .local-browsers（CI 里 PLAYWRIGHT_BROWSERS_PATH=0 安装的结果）；
      2. 本机 %LOCALAPPDATA%\ms-playwright（复制过来）；
      3. 都没有则执行 playwright install chromium 下载。

.EXAMPLE
    pwsh scripts/build_release.ps1
    pwsh scripts/build_release.ps1 -SkipBrowser -Suffix -slim
#>
[CmdletBinding()]
param(
    [switch]$SkipBrowser,
    [string]$Suffix = ""
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

$stash = $null
try {
    $version = (& python -c "import sys; sys.path.insert(0, 'src'); import autologin; print(autologin.__version__)").Trim()
    Write-Host "==> AutoLogin $version (Suffix='$Suffix', SkipBrowser=$SkipBrowser)" -ForegroundColor Cyan

    $driver = (& python -c "import playwright, os; print(os.path.dirname(playwright.__file__))").Trim()
    $browsers = Join-Path $driver 'driver\package\.local-browsers'

    if ($SkipBrowser) {
        # 必须移到包目录之外：留在 playwright 包内的话，collect_all('playwright')
        # 仍会把它收进产物（只是换个名字），"瘦身版"会依旧 300+ MB。
        if (Test-Path $browsers) {
            $stash = Join-Path ([System.IO.Path]::GetTempPath()) ("autologin-browsers-" + [guid]::NewGuid().ToString('N'))
            Write-Host "==> 临时移出浏览器缓存以构建精简版 -> $stash" -ForegroundColor Cyan
            Move-Item $browsers $stash -Force
        }
    }
    else {
        $hasChromium = (Test-Path $browsers) -and (Get-ChildItem $browsers -Directory -Filter 'chromium*' -ErrorAction SilentlyContinue)
        if (-not $hasChromium) {
            $source = Join-Path $env:LOCALAPPDATA 'ms-playwright'
            if ((Test-Path $source) -and (Get-ChildItem $source -Directory -Filter 'chromium*' -ErrorAction SilentlyContinue)) {
                New-Item -ItemType Directory -Force -Path $browsers | Out-Null
                foreach ($item in Get-ChildItem $source -Directory -Filter 'chromium*') {
                    $dest = Join-Path $browsers $item.Name
                    if (-not (Test-Path $dest)) {
                        Write-Host "==> 复制浏览器 $($item.Name)" -ForegroundColor Cyan
                        Copy-Item $item.FullName $dest -Recurse -Force
                    }
                }
            }
            else {
                Write-Host "==> 本机无浏览器缓存，执行 playwright install" -ForegroundColor Cyan
                $env:PLAYWRIGHT_BROWSERS_PATH = '0'
                python -m playwright install chromium
                if ($LASTEXITCODE -ne 0) { throw "playwright install 失败（退出码 $LASTEXITCODE）" }
            }
        }
        # 让 playwright 在构建期与运行期都优先使用随包分发的内核
        $env:PLAYWRIGHT_BROWSERS_PATH = '0'
    }

    Write-Host "==> PyInstaller 打包" -ForegroundColor Cyan
    python -m PyInstaller --clean --noconfirm packaging/AutoLogin.spec | Select-Object -Last 5
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败（退出码 $LASTEXITCODE）" }

    $exe = Join-Path $root 'dist\AutoLogin\AutoLogin.exe'
    if (-not (Test-Path $exe)) { throw "未生成 $exe" }

    $release = Join-Path $root 'release'
    New-Item -ItemType Directory -Force -Path $release | Out-Null
    $zip = Join-Path $release "AutoLogin-$version-win64$Suffix.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }

    Write-Host "==> 压缩产物" -ForegroundColor Cyan
    Compress-Archive -Path (Join-Path $root 'dist\AutoLogin\*') -DestinationPath $zip -CompressionLevel Optimal

    $size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
    Write-Host "==> 完成: $zip ($size MB)" -ForegroundColor Green
}
finally {
    if ($stash -and (Test-Path $stash)) {
        Move-Item $stash $browsers -Force
        Write-Host "==> 浏览器缓存已还原" -ForegroundColor DarkGray
    }
    Remove-Item Env:PLAYWRIGHT_BROWSERS_PATH -ErrorAction SilentlyContinue
    Pop-Location
}
