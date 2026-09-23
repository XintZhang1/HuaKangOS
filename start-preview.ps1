param(
    [int]$Port = 8000,
    [string]$DataDirectory = '',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot 'scripts\preview_launcher.ps1')
$explicitPort = $PSBoundParameters.ContainsKey('Port')
$repositoryId = Get-PreviewRepositoryId $PSScriptRoot
if ($Port -lt 1024 -or $Port -gt 65535) { throw '端口必须在 1024 至 65535 之间。' }
if (-not $env:LOCALAPPDATA) { throw '未找到本机应用数据目录，无法建立独立预览。' }
if (-not $DataDirectory) { $DataDirectory = Join-Path $env:LOCALAPPDATA ('huakangos\preview-' + $repositoryId) }
$previewRoot = [IO.Path]::GetFullPath($DataDirectory).TrimEnd('\')
$allowedRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'huakangos')).TrimEnd('\') + '\'
if (-not $previewRoot.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase) -or $previewRoot.StartsWith($PSScriptRoot.TrimEnd('\')+'\', [StringComparison]::OrdinalIgnoreCase)) {
    throw '预览数据必须位于 LOCALAPPDATA\huakangos 的独立子目录，且不能放在源码目录内。'
}
$mutexSuffix = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($previewRoot.ToLowerInvariant())).Replace('/','_').Replace('+','-')
$previewMutex = New-Object Threading.Mutex($false, ('Local\huakangos-preview-' + $mutexSuffix))
$ownedMutex = $false
function Read-PreviewHealth([int]$AtPort = $Port) {
    try { return Invoke-RestMethod -Uri "http://127.0.0.1:$AtPort/api/local-preview/status" -TimeoutSec 2 -Proxy $null }
    catch { return $null }
}
function Safe-JsonWrite($Path, $Object) {
    $temporary = $Path + '.next'
    [IO.File]::WriteAllText($temporary, ($Object | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}
try {
    $ownedMutex = $previewMutex.WaitOne(0)
    if (-not $ownedMutex) { throw '另一个预览启动器正在运行，请稍后重试。' }
    New-Item -ItemType Directory -Path $previewRoot -Force | Out-Null
    # Restrict the runtime directory to this Windows user and SYSTEM. No secrets in logs.
    $windowsSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $previewRoot /inheritance:r /grant:r ('*'+$windowsSid+':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '无法限制预览目录访问权限，已停止启动。' }
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $setupLog = Join-Path $previewRoot 'setup.log'
    if (-not (Test-Path -LiteralPath $python)) {
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if (-not $launcher) { $launcher = Get-Command python -ErrorAction SilentlyContinue }
        if (-not $launcher) { throw '请安装 Python 3.11–3.13，再运行 start-preview.cmd。' }
        & $launcher.Source -m venv (Join-Path $PSScriptRoot '.venv') *> $setupLog
        if ($LASTEXITCODE -ne 0) { throw "Python 环境创建未完成，请重试。日志：$setupLog" }
    }
    Ensure-PreviewDependencies $python $PSScriptRoot $setupLog
    $identityText = & $python -m app.preview_runtime identity
    if ($LASTEXITCODE -ne 0) { throw '无法读取本版本的源码标识，已停止启动。' }
    $identity = $identityText | ConvertFrom-Json
    if ($identity.repository_id -ne $repositoryId) { throw '源码目录标识不一致，已停止启动。' }
    $manifestPath = Join-Path $previewRoot 'preview.json'
    $processPath = Join-Path $previewRoot 'process.json'
    $stdoutPath = Join-Path $previewRoot 'server.out.log'
    $stderrPath = Join-Path $previewRoot 'server.err.log'
    $manifest = if (Test-Path -LiteralPath $manifestPath) { Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json } else { $null }
    if ((Get-PreviewProperty $manifest 'repository_id') -and $manifest.repository_id -ne $identity.repository_id) {
        throw '此预览数据目录属于另一份源码，请使用它原来的启动器或新的独立目录。'
    }
    $health = $null
    if (Test-Path -LiteralPath $processPath) {
        $previous = Get-Content -LiteralPath $processPath -Raw | ConvertFrom-Json
        $health = Read-PreviewHealth ([int]$previous.port)
        if ($health) {
            Assert-PreviewIdentity $health $manifest $identity
            if ($explicitPort -and $Port -ne [int]$previous.port) {
                throw "此目录已在端口 $($previous.port) 运行；请使用该端口，或不指定端口重新启动。"
            }
            $Port = [int]$previous.port
        } elseif (Test-PreviewPort ([int]$previous.port)) {
            throw "此目录原端口 $($previous.port) 正在被占用且服务未能通过检查，请核查原进程；未启动第二个服务。"
        }
    }
    if (-not $health -and $manifest) {
        $possible = Read-PreviewHealth $Port
        if ($possible -and (Get-PreviewProperty $possible 'instance_id') -eq $manifest.instance_id) {
            Assert-PreviewIdentity $possible $manifest $identity
            $health = $possible
        }
    }
    if ($health) {
        $previewPid = [int]$health.pid
        Write-Host "已打开原有本机预览（进程 $previewPid）。"
    } else {
        $Port = Select-PreviewPort $Port $explicitPort
        $prepareOut = Join-Path $previewRoot 'prepare.json'
        $prepare = Start-Process -FilePath $python -ArgumentList @('-m','app.local_preview','prepare','--root',('"'+$previewRoot+'"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput $prepareOut -RedirectStandardError $setupLog
        if ($prepare.ExitCode -ne 0) {
            $recoveryCommand = '.\start-preview.ps1 -DataDirectory (Join-Path $env:LOCALAPPDATA (''huakangos\preview-retry-'' + [guid]::NewGuid().ToString(''N'')))'
            throw "预览数据库准备未完成或实例标记无法验证，原目录已保留；请核查日志：$setupLog。需要重新尝试首次设置时，请在此源码目录打开 PowerShell 并使用新目录：$recoveryCommand"
        }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        $server = Start-Process -FilePath $python -ArgumentList @('-m','app.local_preview','serve','--root',('"'+$previewRoot+'"'),'--port',"$Port",'--expected-repository-id',$identity.repository_id,'--expected-source-fingerprint',$identity.source_fingerprint) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        $previewPid = $server.Id
        # Keep the actual chosen port discoverable if this launcher is interrupted.
        Safe-JsonWrite $processPath @{pid=$previewPid;port=$Port;instance_id=$manifest.instance_id;repository=$identity.repository;repository_id=$identity.repository_id;source_fingerprint=$identity.source_fingerprint;state='starting'}
        $deadline = [DateTime]::UtcNow.AddSeconds(60)
        do {
            Start-Sleep -Milliseconds 500
            $health = Read-PreviewHealth
            if ($health -and $health.instance_id -eq $manifest.instance_id) {
                Assert-PreviewIdentity $health $manifest $identity
                $servingProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($health.pid)"
                # Windows venv's python.exe is a redirector with a child interpreter.
                if ($health.pid -eq $server.Id -or ($servingProcess -and $servingProcess.ParentProcessId -eq $server.Id)) {
                    $previewPid = [int]$health.pid
                    break
                }
            }
            $server.Refresh()
            if ($server.HasExited) { throw "预览进程未能启动，请核查日志：$stderrPath" }
        } while ([DateTime]::UtcNow -lt $deadline)
        if (-not $health -or $health.instance_id -ne $manifest.instance_id -or $health.pid -ne $previewPid) { throw "预览未能通过启动检查，请核查日志：$stderrPath" }
        Write-Host "本机预览已启动（进程 $previewPid）。"
    }
    Safe-JsonWrite $processPath @{pid=$previewPid;port=$Port;instance_id=$manifest.instance_id;repository=$identity.repository;repository_id=$identity.repository_id;source_fingerprint=$health.source_fingerprint;state='running'}
    $url = "http://127.0.0.1:$Port/"
    if ($health.bootstrap_required) {
        $bytes = New-Object byte[] 32
        $random = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $random.GetBytes($bytes) } finally { $random.Dispose() }
        $token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $hash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($token)))).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
        Safe-JsonWrite (Join-Path $previewRoot 'bootstrap.json') @{instance_id=$manifest.instance_id;token_hash=$hash;expires_at=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()+900}
        $url += '#preview-setup=' + $token
        Write-Host '首次使用：请在打开的页面自行设置管理员密码。设置链接 15 分钟有效。'
    }
    if (-not $NoBrowser) { Start-Process $url | Out-Null }
    # Deliberately print only the ordinary URL, never the fragment or token.
    Write-Host "本机预览：http://127.0.0.1:$Port/"
    Write-Host "资料和日志：$previewRoot"
    Write-Host '再次运行 start-preview.cmd 即可重新打开，已有账号和资料会保留。'
} catch {
    Write-Error $_.Exception.Message
    exit 1
} finally {
    if ($ownedMutex) { $previewMutex.ReleaseMutex() }
    $previewMutex.Dispose()
}
