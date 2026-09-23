# Pure decisions and bounded probes; dot-sourcing does not launch or modify anything.
function Get-PreviewRepositoryId([string]$Repository) {
    $canonical = [IO.Path]::GetFullPath($Repository).TrimEnd('\').ToLowerInvariant()
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($canonical)))).Replace('-','').ToLowerInvariant().Substring(0,20) }
    finally { $sha.Dispose() }
}
function Get-PreviewProperty($Object, [string]$Name) {
    if ($null -ne $Object -and $null -ne $Object.PSObject.Properties[$Name]) { return $Object.$Name }
    return $null
}
function Assert-PreviewIdentity($Health, $Manifest, $Identity) {
    if (-not (Get-PreviewProperty $Health 'local_preview') -or
        -not (Get-PreviewProperty $Manifest 'instance_id') -or
        (Get-PreviewProperty $Health 'instance_id') -ne (Get-PreviewProperty $Manifest 'instance_id') -or
        (Get-PreviewProperty $Health 'repository_id') -ne $Identity.repository_id -or
        (Get-PreviewProperty $Health 'source_fingerprint') -ne $Identity.source_fingerprint) {
        throw '此预览目录正在运行其他来源或旧版本代码，不能复用。请关闭原预览后重试，或指定新的独立预览目录；未停止或重写原进程。'
    }
}
function Test-PreviewPort([int]$AtPort) {
    $listener = [Net.Sockets.TcpClient]::new()
    try { $listener.Connect('127.0.0.1', $AtPort); return $true }
    catch { return $false }
    finally { $listener.Dispose() }
}
function Select-PreviewPort([int]$RequestedPort, [bool]$ExplicitPort) {
    if ($RequestedPort -lt 1024 -or $RequestedPort -gt 65535) { throw '端口必须在 1024 至 65535 之间。' }
    for ($candidate = $RequestedPort; $candidate -le 65535; $candidate++) {
        if (-not (Test-PreviewPort $candidate)) { return $candidate }
        if ($ExplicitPort) { throw "指定端口 $RequestedPort 已被占用，请换一个端口；未停止任何进程。" }
    }
    throw '没有找到可用的本机端口，请关闭不需要的预览后重试。'
}
function Invoke-PreviewPython([string]$Python, [string[]]$Arguments, [string]$Log) {
    $priorPreference = $ErrorActionPreference
    try {
        # Native stderr is captured as log data, including harmless pip notices.
        $ErrorActionPreference = 'Continue'
        & $Python @Arguments *> $Log
        return $LASTEXITCODE
    } finally { $ErrorActionPreference = $priorPreference }
}
function Ensure-PreviewDependencies([string]$Python, [string]$Repository, [string]$Log) {
    $helper = Join-Path $Repository 'app\preview_runtime.py'
    if ((Invoke-PreviewPython $Python @($helper, 'python-version') $Log) -ne 0) {
        throw "预览环境需要 Python 3.11–3.13，请重新配置受支持的 Python 环境。日志：$Log"
    }
    if ((Invoke-PreviewPython $Python @($helper, 'dependencies') $Log) -eq 0) { return }
    if ((Invoke-PreviewPython $Python @('-m','pip','install','-r',(Join-Path $Repository 'requirements.txt')) $Log) -ne 0) {
        throw "依赖安装未完成。请检查网络后重新运行 start-preview.cmd，启动器会继续检查并重试。日志：$Log"
    }
    if ((Invoke-PreviewPython $Python @($helper, 'dependencies') $Log) -ne 0) {
        throw "依赖尚未就绪，请查看日志后重新运行启动器。日志：$Log"
    }
}
