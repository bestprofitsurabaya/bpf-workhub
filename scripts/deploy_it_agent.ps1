<#
.SYNOPSIS
  Deploy TERKONTROL agen inventaris IT ke PC Windows — allowlist + WinRM.

.DESCRIPTION
  Satu-satunya jalur push agen. Prinsipnya: daftar target eksplisit, bukan
  propagasi. Skrip ini:

    * WAJIB memakai -Targets <csv> (allowlist). Tidak ada parameter
      subnet/CIDR/range dan tidak ada ekspansi otomatis; baris berisi
      CIDR, rentang IP, atau wildcard DITOLAK.
    * Membatasi jumlah host per eksekusi (-MaxHosts, default 25). Untuk
      melebihi, operator harus menambahkan -Force secara sadar.
    * Hanya memakai WinRM (5985/5986). Tidak memakai PsExec, tidak menulis
      ke share admin, tidak menyentuh host di luar daftar.
    * Mencatat hasil per host ke CSV lokal dan melaporkannya ke
      /api/it/agents/report agar dashboard cakupan akurat.
    * Menghapus token sementara di PC target setelah instalasi.

  PC yang tergabung domain sebaiknya memakai GPO/Intune (tanpa kredensial
  per-PC). Skrip ini untuk PC workgroup/standalone atau domain yang belum
  punya GPO — lihat docs/internal/IT_INVENTORY_RESEARCH.md.

.PARAMETER Targets
  Path CSV allowlist. Kolom wajib: host ATAU ip. Kolom opsional: mac,
  source, asset_tag, note. Format sama dengan unduhan
  GET /api/it/agents/targets.csv.

.PARAMETER ApiUrl
  Basis URL aplikasi, mis. https://nasbpfsby.duckdns.org:5000

.PARAMETER Token
  Token agen (IT_DISCOVERY_TOKEN). Bila kosong, skrip menanyakan secara
  tersembunyi (SecureString).

.PARAMETER TokenFile
  Alternatif -Token: baca token dari berkas lokal.

.PARAMETER Branch
  Kode cabang pemilik PC (SBY, JKT, BDG, ...).

.PARAMETER Credential
  Kredensial admin untuk WinRM. Untuk workgroup pakai .\Administrator.
  Bila kosong, skrip meminta Get-Credential.

.PARAMETER MaxHosts
  Batas host per eksekusi (default 25).

.PARAMETER Force
  Izinkan allowlist melebihi -MaxHosts. Tidak mengubah validasi per baris.

.PARAMETER DryRun
  Hanya menampilkan rencana (target tervalidasi + perintah yang akan
  dijalankan). Tidak membuka koneksi, tidak butuh token/kredensial.

.PARAMETER UseSSL
  Pakai WinRM HTTPS (5986).

.PARAMETER Port
  Port WinRM kustom (mengalahkan -UseSSL).

.PARAMETER SetupTrustedHosts
  Tambahkan host target ke WSMan:\localhost\Client\TrustedHosts di mesin
  ini (hanya untuk WinRM HTTP di workgroup). Diminta eksplisit karena
  menurunkan jaminan keamanan transport; HTTPS lebih disarankan.

.PARAMETER Yes
  Lewati konfirmasi interaktif sebelum deploy.

.PARAMETER LogDir
  Folder log CSV lokal (default .\logs).

.EXAMPLE
  # 1) unduh allowlist dari aplikasi (login IT), lalu uji rencana
  .\deploy_it_agent.ps1 -Targets .\target_agen_it_SBY.csv `
      -ApiUrl https://nasbpfsby.duckdns.org:5000 -Branch SBY -DryRun

.EXAMPLE
  # 2) deploy sungguhan ke maksimum 25 PC
  .\deploy_it_agent.ps1 -Targets .\target_agen_it_SBY.csv `
      -ApiUrl https://nasbpfsby.duckdns.org:5000 -Branch SBY `
      -Credential (Get-Credential)

.NOTES
  Penanda: BPF-WORKHUB-IT-AGENT-DEPLOYER
  Membutuhkan PowerShell 5.1+ di mesin operator (Windows).
#>
# BPF-WORKHUB-IT-AGENT-DEPLOYER
#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $Targets,
    [Parameter(Mandatory = $true)] [string] $ApiUrl,
    [string] $Token = '',
    [string] $TokenFile = '',
    [string] $Branch = 'SBY',
    [System.Management.Automation.PSCredential] $Credential,
    [int] $MaxHosts = 25,
    [switch] $Force,
    [switch] $DryRun,
    [switch] $UseSSL,
    [int] $Port = 0,
    [switch] $SetupTrustedHosts,
    [switch] $Yes,
    [string] $LogDir = '',
    [string] $LocationRoom = '',
    [string] $AssignedTo = '',
    [int] $TimeoutSec = 45
)

$ErrorActionPreference = 'Stop'
$AgentScriptName = 'it_inventory_agent.ps1'
$AgentSource = Join-Path $PSScriptRoot $AgentScriptName
$AgentMarker = 'BPF-WORKHUB-IT-ASSET-AGENT'
$RemoteDir = 'C:\Windows\Temp\bpf-it-agent'

function Say { param([string] $Text) Write-Host "[deploy] $Text" }
function SayWarn { param([string] $Text) Write-Warning "[deploy] $Text" }

# ------------------------------------------------------------- pra-syarat
if ($MaxHosts -lt 1) { throw '-MaxHosts minimal 1.' }
if ($ApiUrl -notmatch '^https?://[^/\s]+') {
    throw "-ApiUrl harus diawali http:// atau https:// (diberikan: $ApiUrl)."
}
if (-not (Test-Path -LiteralPath $AgentSource)) {
    throw "Skrip agen tidak ditemukan di samping deployer: $AgentSource"
}
if ((Get-Content -Raw -LiteralPath $AgentSource) -notmatch [regex]::Escape($AgentMarker)) {
    throw 'Skrip agen tidak punya penanda paket — unduh ulang dari aplikasi.'
}

$agentVersion = ''
$versionMatch = Select-String -LiteralPath $AgentSource -Pattern "AgentVersion\s*=\s*'([0-9][0-9.]*)'" |
    Select-Object -First 1
if ($versionMatch) { $agentVersion = $versionMatch.Matches[0].Groups[1].Value }

$winrmPort = if ($Port -gt 0) { $Port } elseif ($UseSSL) { 5986 } else { 5985 }

# --------------------------------------------------------------- allowlist
if (-not (Test-Path -LiteralPath $Targets)) {
    throw "Allowlist tidak ditemukan: $Targets"
}
$raw = @(Import-Csv -LiteralPath $Targets)
if ($raw.Count -eq 0) {
    throw 'Allowlist kosong — deployment dibatalkan.'
}
$columns = @($raw[0].PSObject.Properties.Name)
if (-not ($columns -contains 'host' -or $columns -contains 'ip')) {
    throw 'CSV allowlist harus punya kolom "host" atau "ip" (unduh dari /api/it/agents/targets.csv).'
}
if ($raw.Count -gt $MaxHosts -and -not $Force) {
    throw "Allowlist berisi $($raw.Count) host, melebihi -MaxHosts $MaxHosts. " +
          'Perkecil daftar (disarankan) atau tambahkan -Force bila sudah disetujui.'
}

$targetList = New-Object System.Collections.Generic.List[object]
$seen = @{}
foreach ($row in $raw) {
    $hostCell = "$($row.host)".Trim()
    $ipCell = "$($row.ip)".Trim()
    $entry = if ($hostCell) { $hostCell } else { $ipCell }
    if (-not $entry) {
        throw 'Ada baris tanpa host/ip — perbaiki CSV allowlist.'
    }
    if ($entry -match '[/?*]' -or $entry -match '\s') {
        throw "Target '$entry' bukan host tunggal. CIDR, wildcard, dan rentang ditolak."
    }
    if ($entry -match '^\d') {
        if ($entry -notmatch '^(\d{1,3}\.){3}\d{1,3}$') {
            throw "Target '$entry' bukan alamat IPv4 tunggal (rentang/CIDR ditolak)."
        }
    } elseif ($entry -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$') {
        throw "Target '$entry' bukan hostname valid."
    }
    $key = $entry.ToLowerInvariant()
    if ($seen.ContainsKey($key)) { continue }
    $seen[$key] = $true
    $targetList.Add([pscustomobject]@{
        host      = $entry
        ip        = $ipCell
        mac       = "$($row.mac)".Trim()
        asset_tag = "$($row.asset_tag)".Trim()
        source    = "$($row.source)".Trim()
        note      = "$($row.note)".Trim()
    })
}
if ($targetList.Count -eq 0) { throw 'Tidak ada target valid di allowlist.' }
if ($targetList.Count -gt $MaxHosts -and -not $Force) {
    throw "Setelah deduplikasi masih $($targetList.Count) host > -MaxHosts $MaxHosts."
}

Say "Allowlist: $($targetList.Count) host (cabang $Branch), agen v$agentVersion, WinRM port $winrmPort."
Say "Sumber: $Targets"

# ------------------------------------------------------------------ DryRun
if ($DryRun) {
    $targetList | Select-Object host, ip, mac, asset_tag, source |
        Format-Table -AutoSize | Out-String | Write-Host
    Say 'Rencana perintah per host (token tidak ditampilkan):'
    $planCommand = "powershell -File $AgentScriptName -Install -ApiUrl $($ApiUrl.TrimEnd('/')) " +
        "-TokenFile <token-sementara> -Branch $Branch -InstallMethod winrm-push"
    Say $planCommand
    Say 'DryRun selesai — tidak ada koneksi yang dibuka.'
    return
}

# --------------------------------------------------------------- kredensial
if (-not $Token -and $TokenFile) {
    if (-not (Test-Path -LiteralPath $TokenFile)) {
        throw "Berkas token tidak ditemukan: $TokenFile"
    }
    $Token = (Get-Content -Raw -LiteralPath $TokenFile).Trim()
}
if (-not $Token) {
    $secure = Read-Host -AsSecureString 'Token agen (IT_DISCOVERY_TOKEN)'
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $Token = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}
if (-not $Token) { throw 'Token agen wajib diisi.' }

if (-not $Credential) {
    $Credential = Get-Credential -Message 'Akun admin WinRM di PC target (workgroup: .\Administrator)'
}

if ($SetupTrustedHosts) {
    SayWarn 'Menambahkan target ke TrustedHosts (WinRM HTTP). Gunakan HTTPS bila memungkinkan.'
    $existing = @()
    try {
        $existing = @((Get-Item 'WSMan:\localhost\Client\TrustedHosts').Value -split ',' |
            ForEach-Object { $_.Trim() } | Where-Object { $_ })
    } catch { $existing = @() }
    foreach ($t in $targetList) {
        foreach ($name in @($t.host, $t.ip)) {
            if ($name -and ($existing -notcontains $name)) { $existing += $name }
        }
    }
    Set-Item 'WSMan:\localhost\Client\TrustedHosts' -Value ($existing -join ',') -Force
}

if (-not $Yes) {
    $answer = Read-Host "Deploy agen ke $($targetList.Count) PC cabang $Branch? Ketik 'ya' untuk lanjut"
    if ($answer -ne 'ya') { Say 'Dibatalkan oleh operator.'; return }
}

# ------------------------------------------------------------------ log CSV
if (-not $LogDir) { $LogDir = Join-Path (Get-Location) 'logs' }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logPath = Join-Path $LogDir "deploy_it_agent_${Branch}_$stamp.csv"
$logColumns = @('timestamp', 'branch', 'target', 'hostname', 'ip', 'mac', 'status',
                'message', 'asset_tag', 'duration_s', 'agent_version')

function Write-LogRow {
    param([hashtable] $Row)
    $obj = [pscustomobject]$Row
    $csvParams = @{ LiteralPath = $logPath; NoTypeInformation = $true; Encoding = 'UTF8' }
    if (Test-Path -LiteralPath $logPath) { $csvParams['Append'] = $true }
    $obj | Select-Object $logColumns | Export-Csv @csvParams
}

function Send-AgentReport {
    param([hashtable] $HostData)
    $payload = [ordered]@{ branch_code = $Branch; hosts = @($HostData) }
    $json = $payload | ConvertTo-Json -Depth 6 -Compress
    Invoke-RestMethod -Method Post -Uri ($ApiUrl.TrimEnd('/') + '/api/it/agents/report') `
        -Headers @{ 'X-IT-TOKEN' = $Token } -ContentType 'application/json; charset=utf-8' `
        -Body ([Text.Encoding]::UTF8.GetBytes($json)) -TimeoutSec 30 | Out-Null
}

function Test-TcpPort {
    param([string] $ComputerName, [int] $PortNumber, [int] $TimeoutMs = 3000)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($ComputerName, $PortNumber, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-RemoteFacts {
    param($Session)
    Invoke-Command -Session $Session -ScriptBlock {
        $facts = [ordered]@{
            hostname = $env:COMPUTERNAME
            domain   = ''
            os_name  = ''
            ip       = ''
            mac      = ''
        }
        try {
            $cs = Get-CimInstance -ClassName Win32_ComputerSystem
            $facts.domain = "$($cs.Domain)"
            $os = Get-CimInstance -ClassName Win32_OperatingSystem
            $facts.os_name = "$($os.Caption) $($os.Version)".Trim()
        } catch { }
        try {
            $cfg = Get-CimInstance -ClassName Win32_NetworkAdapterConfiguration |
                Where-Object { $_.IPEnabled -and $_.DefaultIPGateway } | Select-Object -First 1
            if (-not $cfg) {
                $cfg = Get-CimInstance -ClassName Win32_NetworkAdapterConfiguration |
                    Where-Object { $_.IPEnabled } | Select-Object -First 1
            }
            $ip = @($cfg.IPAddress | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } |
                Select-Object -First 1)
            if ($ip.Count) { $facts.ip = "$($ip[0])" }
            if ($cfg.MACAddress) { $facts.mac = "$($cfg.MACAddress)".ToUpper() }
        } catch { }
        [pscustomobject]$facts
    }
}

# --------------------------------------------------------- token sementara
$tokenTemp = Join-Path ([IO.Path]::GetTempPath()) ("bpf-it-token-" + [guid]::NewGuid().ToString('N') + '.txt')
Set-Content -LiteralPath $tokenTemp -Value $Token -Encoding ASCII -NoNewline
try {
    & icacls $tokenTemp /inheritance:r /grant:r "$env:USERNAME:(F)" 'SYSTEM:(F)' | Out-Null
} catch {
    SayWarn "Tidak bisa membatasi ACL berkas token sementara: $_"
}

$results = New-Object System.Collections.Generic.List[object]
$failures = 0

try {
    foreach ($target in $targetList) {
        $started = Get-Date
        $session = $null
        $status = 'failed'
        $message = ''
        $facts = [ordered]@{ hostname = ''; os_name = ''; ip = $target.ip; mac = $target.mac; domain = '' }
        $unreachable = $false
        Say "→ $($target.host)"

        try {
            if (-not (Test-TcpPort -ComputerName $target.host -PortNumber $winrmPort -TimeoutMs 3000)) {
                $unreachable = $true
                throw "WinRM ($winrmPort) tidak terbuka. Aktifkan dulu di PC target: Enable-PSRemoting -Force (atau lewat GPO)."
            }

            $sessionParams = @{ ComputerName = $target.host; ErrorAction = 'Stop' }
            if ($Credential) { $sessionParams.Credential = $Credential }
            if ($UseSSL) { $sessionParams.UseSSL = $true }
            if ($Port -gt 0) { $sessionParams.Port = $Port }
            $session = New-PSSession @sessionParams

            Say "  sesi WinRM terbuka; menyiapkan folder sementara (ACL SYSTEM+Administrators)"
            Invoke-Command -Session $session -ScriptBlock {
                param($Dir)
                New-Item -ItemType Directory -Force -Path $Dir | Out-Null
                & icacls $Dir /inheritance:r /grant:r 'SYSTEM:(OI)(CI)(F)' 'Administrators:(OI)(CI)(F)' | Out-Null
            } -ArgumentList $RemoteDir | Out-Null

            $remoteScript = Join-Path $RemoteDir $AgentScriptName
            $remoteToken = Join-Path $RemoteDir 'token.txt'
            Copy-Item -ToSession $session -Path $AgentSource -Destination $remoteScript -Force
            Copy-Item -ToSession $session -Path $tokenTemp -Destination $remoteToken -Force

            $run = Invoke-Command -Session $session -ScriptBlock {
                param($Script, $TokenPath, $Url, $BranchCode, $Room, $Assigned, $Method)
                $out = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Script `
                    -Install -ApiUrl $Url -TokenFile $TokenPath -DeleteTokenFile `
                    -Branch $BranchCode -LocationRoom $Room -AssignedTo $Assigned `
                    -InstallMethod $Method *>&1
                [pscustomobject]@{
                    exit_code = $LASTEXITCODE
                    output    = (($out | ForEach-Object { "$_" }) -join "`n")
                }
            } -ArgumentList $remoteScript, $remoteToken, $ApiUrl.TrimEnd('/'), $Branch,
                $LocationRoom, $AssignedTo, 'winrm-push'

            try { $facts = Get-RemoteFacts -Session $session } catch { }

            $exitCode = [int]$run.exit_code
            if ($exitCode -eq 0) {
                $status = 'installed'
                $message = "agen v$agentVersion terpasang; laporan awal terkirim"
            } else {
                $tail = ($run.output -split "`n" | Where-Object { $_.Trim() } |
                    Select-Object -Last 3) -join ' | '
                $message = "agen keluar dengan kode $exitCode. $tail"
            }
        } catch {
            $message = "$_"
            if ($unreachable) { $status = 'unreachable' }
            if ($message -match 'TrustedHosts|unencrypted|tidak dapat memproses') {
                $message += ' (workgroup: pakai -SetupTrustedHosts atau WinRM HTTPS)'
            }
        } finally {
            if ($session) {
                try {
                    Invoke-Command -Session $session -ScriptBlock {
                        param($Dir)
                        Remove-Item -LiteralPath $Dir -Recurse -Force -ErrorAction SilentlyContinue
                    } -ArgumentList $RemoteDir | Out-Null
                } catch { }
                try { Remove-PSSession -Session $session -ErrorAction SilentlyContinue } catch { }
            }
        }

        $duration = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
        if ($status -ne 'installed') { $failures++ }
        if ($message.Length -gt 300) { $message = $message.Substring(0, 300) }

        $reportHost = if ($facts.hostname) { "$($facts.hostname)" } else { $target.host }
        $reportIp = if ($facts.ip) { "$($facts.ip)" } else { $target.ip }
        $reportMac = if ($facts.mac) { "$($facts.mac)" } else { $target.mac }
        $report = @{
            branch_code    = $Branch
            hostname       = $reportHost
            ip             = $reportIp
            mac            = $reportMac
            os_name        = "$($facts.os_name)"
            agent_version  = $agentVersion
            install_method = 'winrm-push'
            status         = $status
            message        = $message
            asset_tag      = $target.asset_tag
        }
        try {
            Send-AgentReport -HostData $report
        } catch {
            SayWarn "  laporan server gagal (hasil tetap dicatat lokal): $_"
        }

        Write-LogRow -Row @{
            timestamp     = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            branch        = $Branch
            target        = $target.host
            hostname      = $report.hostname
            ip            = $report.ip
            mac           = $report.mac
            status        = $status
            message       = $message
            asset_tag     = $target.asset_tag
            duration_s    = $duration
            agent_version = $agentVersion
        }
        $results.Add([pscustomobject]@{ target = $target.host; status = $status;
            hostname = $report.hostname; message = $message })
        Say "  $status — $($report.hostname) ($duration s)"
    }
} finally {
    Remove-Item -LiteralPath $tokenTemp -Force -ErrorAction SilentlyContinue
}

Say "Selesai: $($results.Count - $failures) berhasil, $failures gagal/dilewati."
Say "Log lokal: $logPath"
Say 'Buka aplikasi → Inventaris IT → tab Jaringan → panel "Cakupan Agen" untuk melihat hasilnya.'
if ($failures -gt 0) { exit 1 }
exit 0
