<#
.SYNOPSIS
    构建可脱离环境的 Windows 便携版（PyInstaller onedir + 内置 Chromium）。

.DESCRIPTION
    1. 把本机已安装的 Playwright 浏览器复制进 playwright 包目录下的
       .local-browsers（即 PLAYWRIGHT_BROWSERS_PATH=0 的效果），
       PyInstaller 会随 collect_all('playwright') 一并打包；
    2. 调用 packaging/AutoLogin.spec 生成 dist/AutoLogin/；
    3. 压缩为 release/AutoLogin-<version>-win64.zip。

    目标机器无需安装 Python，也无需另装浏览器。

.EXAMPLE
    pwsh scripts/build_release.ps1
    pwsh scripts/build_release.ps1 -SkipBrowser -Suffix -slim   # 不内置浏览器，体积更小
#>
[CmdletBinding()]
param(
    [switch]$SkipBrowser,
    [string]$Suffix = ""
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $version = (& python -c "import sys; sys.path.insert(0, 'src'); import autologin; print(autologin.__version__)").Trim()
    Write-Host "==> AutoLogin $version" -ForegroundColor Cyan

    if (-not $SkipBrowser) {
        $driver = (& python -c "import playwright, os; print(os.path.dirname(playwright.__file__))").Trim()
        $target = Join-Path $driver 'driver\package\.local-browsers'
        $source = Join-Path $env:LOCALAPPDATA 'ms-playwright'
        if (-not (Test-Path $source)) {
            throw "未找到 $source，请先执行 python -m playwright install chromium"
        }
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        foreach ($item in Get-ChildItem $source -Directory | Where-Object { $_.Name -like 'chromium*' }) {
            $dest = Join-Path $target $item.Name
            if (-not (Test-Path $dest)) {
                Write-Host "==> 内置浏览器 $($item.Name)" -ForegroundColor Cyan
                Copy-Item $item.FullName $dest -Recurse -Force
            }
        }
        # 让 playwright 在运行时优先使用随包分发的内核
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
    Write-Host "    校验: & '$exe' --version"
}
finally {
    Remove-Item Env:PLAYWRIGHT_BROWSERS_PATH -ErrorAction SilentlyContinue
    Pop-Location
}
