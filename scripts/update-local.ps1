# 本地更新：只写指定训练目录。先下载检查，再备份，最后替换程序。
param(
    [string]$TrainPath = 'C:\Users\29356\Desktop\行测obsidian\行测\训练',
    [string]$Revision = 'main'
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if ($Revision -notmatch '^(main|[a-f0-9]{40})$') { throw '版本必须是 main 或完整提交编号。' }
if (-not (Test-Path -LiteralPath $TrainPath -PathType Container)) { throw "训练目录不存在：$TrainPath" }
$TrainPath = (Resolve-Path -LiteralPath $TrainPath).Path
$program = Join-Path $TrainPath '程序'
$running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'python3.exe'" -ErrorAction Stop |
    Where-Object { $_.CommandLine -and ($_.CommandLine.Replace('/', '\').Contains($program)) }
if ($running) { throw '请先关闭训练程序的终端窗口，再运行更新。' }
$stage = Join-Path $TrainPath ('.更新临时-' + [Guid]::NewGuid().ToString('N'))
$backupRoot = Join-Path $TrainPath '更新备份'
$backup = Join-Path $backupRoot ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,6))
$oldProgram = Join-Path $stage '旧程序'
$swapped = $false
$utf8 = New-Object System.Text.UTF8Encoding($false)
try {
    New-Item -ItemType Directory -Path $stage | Out-Null
    $zip = Join-Path $stage 'source.zip'
    Invoke-WebRequest -Uri "https://github.com/dingzhen164-coder/xingce-rpg/archive/$Revision.zip" -OutFile $zip -UseBasicParsing
    $unpack = Join-Path $stage '解压'
    Expand-Archive -LiteralPath $zip -DestinationPath $unpack
    $source = Get-ChildItem -LiteralPath $unpack -Directory | Select-Object -First 1
    if (-not $source) { throw '下载内容无效。' }
    foreach ($required in @('server.py','rpg\question_bank.py','web\app.js','defaults\题库')) {
        if (-not (Test-Path -LiteralPath (Join-Path $source.FullName $required))) { throw "下载内容缺少 $required，尚未修改本地程序。" }
    }
    $newProgram = Join-Path $stage '新程序'
    New-Item -ItemType Directory -Path $newProgram | Out-Null
    Get-ChildItem -LiteralPath $source.FullName -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $newProgram -Recurse -Force
    }
    # 备份代码、配置、骨架、题库和存档；不把历史备份套进新备份。
    New-Item -ItemType Directory -Path $backup | Out-Null
    Get-ChildItem -LiteralPath $TrainPath -Force | Where-Object {
        $_.Name -ne '更新备份' -and $_.Name -notlike '.更新临时-*'
    } | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $backup -Recurse -Force }
    if (Test-Path -LiteralPath $program) { Move-Item -LiteralPath $program -Destination $oldProgram }
    try {
        Move-Item -LiteralPath $newProgram -Destination $program
        $swapped = $true
        $bankFolder = Join-Path $TrainPath '题库'
        New-Item -ItemType Directory -Path $bankFolder -Force | Out-Null
        Get-ChildItem -LiteralPath (Join-Path $program 'defaults\题库') -Filter '*.md' | ForEach-Object {
            $target = Join-Path $bankFolder $_.Name
            if (-not (Test-Path -LiteralPath $target)) { Copy-Item -LiteralPath $_.FullName -Destination $target }
        }
        $rulesPath = Join-Path $TrainPath '规则.md'
        if (-not (Test-Path -LiteralPath $rulesPath)) {
            Copy-Item -LiteralPath (Join-Path $program 'defaults\规则.md') -Destination $rulesPath
        } else {
            $rules = [IO.File]::ReadAllText($rulesPath, $utf8)
            $extra = @()
            foreach ($pair in @(@('实战每组题数','10'), @('分钟.实战每题','2'), @('经验.实战答对','5'), @('经验.实战答错','1'), @('经验.实战通关','30'), @('试炼上品正确率','0.9'), @('试炼中品正确率','0.7'), @('试炼塔层数','100'), @('试炼塔总题数','5000'))) {
                $pattern = '(?m)^\s*[-*]\s+' + [regex]::Escape($pair[0]) + '\s*[:：]'
                if ($rules -notmatch $pattern) { $extra += ('- ' + $pair[0] + ': ' + $pair[1]) }
            }
            if ($extra.Count -gt 0) {
                $rules = $rules.TrimEnd() + "`n`n## 真题实战`n`n" + ($extra -join "`n") + "`n"
                [IO.File]::WriteAllText($rulesPath, $rules.Replace("`r`n", "`n"), $utf8)
            }
        }
        [IO.File]::WriteAllText((Join-Path $program '更新版本.txt'), $Revision + "`n", $utf8)
    } catch {
        # 配置修改失败也恢复更新前的程序和规则；存档始终未改写。
        if ($swapped -and (Test-Path -LiteralPath $program)) { Remove-Item -LiteralPath $program -Recurse -Force }
        if (Test-Path -LiteralPath $oldProgram) { Move-Item -LiteralPath $oldProgram -Destination $program }
        $oldRules = Join-Path $backup '规则.md'
        if (Test-Path -LiteralPath $oldRules) { Copy-Item -LiteralPath $oldRules -Destination (Join-Path $TrainPath '规则.md') -Force }
        throw
    }
    Write-Host '更新成功。重新启动训练程序，在“试炼塔”中查看各板块。' -ForegroundColor Green
    Write-Host "题库位置：$(Join-Path $TrainPath '题库')"
    Write-Host "备份位置：$backup"
    Write-Host '存档、骨架和已有题库未覆盖；规则只补充缺失的实战参数。'
} finally {
    # 如果回滚失败，保留原程序，不能在清理时删除最后一份可恢复代码。
    if ((Test-Path -LiteralPath $oldProgram) -and -not (Test-Path -LiteralPath $program)) {
        Write-Warning "原程序保留在 $oldProgram，请从备份恢复。"
    } elseif (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
