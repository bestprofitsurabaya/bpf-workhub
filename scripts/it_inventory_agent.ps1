<#
.SYNOPSIS
  Agen WMI Inventaris IT — kirim data hardware PC Windows ke BPF WorkHub.

.DESCRIPTION
  Dijalankan DI PC yang diinventaris (manual oleh IT, lewat GPO/Intune, atau
  dipasang terkontrol oleh scripts/deploy_it_agent.ps1). Script ini hanya
  membaca metadata perangkat lewat WMI/CIM dan mengirimnya ke server.

  Mode pakai:
    -Run (default)  : sekali jalan, parameter diberikan langsung (uji/manual)
    -Install        : pasang ke C:\ProgramData\BPFWorkHub, tulis config,
                      daftarkan Scheduled Task harian (SYSTEM), lalu jalankan
    -FromConfig     : dipakai Scheduled Task — baca config, lapor, cek update

  Sifatnya ADITIF dan TIDAK menyebar sendiri:
    - tidak memindai jaringan, tidak membuka port, tidak menulis ke PC lain;
    - tidak membaca berkas pengguna; hanya metadata perangkat;
    - hasil di server berupa *kandidat* + baris registry cakupan agen;
    - aset TIDAK pernah dibuat otomatis.

.PARAMETER ApiUrl
  Basis URL aplikasi, mis. https://nasbpfsby.duckdns.org:5000

.PARAMETER Token
  Token agen = nilai `IT_DISCOVERY_TOKEN` di `.env` aplikasi.

.PARAMETER Branch
  Kode cabang pemilik PC (SBY, JKT, BDG, ...).

.PARAMETER Install
  Pasang permanen + Scheduled Task harian 12:05 (butuh Administrator).

.PARAMETER FromConfig
  Baca konfigurasi dari $InstallDir\agent-config.json (dipakai task).

.PARAMETER InstallDir
  Lokasi pemasangan, default C:\ProgramData\BPFWorkHub.

.PARAMETER TokenFile
  Baca token dari berkas (dipakai deployer agar token tidak tampil di
  command line). Baris baru/spasi dipangkas.

.PARAMETER DeleteTokenFile
  Hapus berkas token setelah config tersimpan (khusus berkas sementara
  milik deployer).

.PARAMETER InstallMethod
  Label asal pemasangan yang dicatat di registry cakupan
  (mis. winrm-push, gpo, manual).

.PARAMETER SkipUpdate
  Jangan cek/perbarui agen dari server pada eksekusi ini.

.EXAMPLE
  # uji tanpa mengirim
  powershell -ExecutionPolicy Bypass -File .\it_inventory_agent.ps1 `
      -ApiUrl https://nasbpfsby.duckdns.org:5000 -Token "xxxx" -Branch SBY -DryRun

.EXAMPLE
  # pasang permanen di PC ini (Administrator)
  powershell -ExecutionPolicy Bypass -File .\it_inventory_agent.ps1 `
      -ApiUrl https://nasbpfsby.duckdns.org:5000 -Token "xxxx" -Branch SBY -Install

.NOTES
  Penanda paket (dipakai self-update): BPF-WORKHUB-IT-ASSET-AGENT
  Versi harus sama dengan AGENT_VERSION di modules/routes_it_assets.py.
#>
# BPF-WORKHUB-IT-ASSET-AGENT
[CmdletBinding()]
param(
    [string] $ApiUrl = '',
    [string] $Token = '',
    [string] $Branch = 'SBY',
    [string] $LocationRoom = '',
    [string] $AssignedTo = '',
    [switch] $Install,
    [switch] $FromConfig,
    [string] $InstallDir = 'C:\ProgramData\BPFWorkHub',
    [string] $TokenFile = '',
    [switch] $DeleteTokenFile,
    [string] $InstallMethod = '',
    [switch] $SkipUpdate,
    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'
$AgentVersion = '1.1.0'
$TaskName = 'BPFWorkHub-ITAssetAgent'
$ConfigFile = Join-Path $InstallDir 'agent-config.json'
$InstalledScript = Join-Path $InstallDir 'it_inventory_agent.ps1'
$ScriptPath = if ($PSCommandPath) { $PSCommandPath } else { $MyInvocation.MyCommand.Path }

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    Write-Warning "TLS 1.2 tidak dapat diaktifkan: $_"
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-AgentConfig {
    if (-not (Test-Path $ConfigFile)) {
        throw "Config agen tidak ditemukan: $ConfigFile (jalankan -Install lebih dulu)."
    }
    return (Get-Content -Raw -Path $ConfigFile | ConvertFrom-Json)
}

function Save-AgentConfig {
    param([hashtable] $Values)
    $json = [ordered]@{
        api_url       = $Values.ApiUrl
        token         = $Values.Token
        branch        = $Values.Branch
        location_room = $Values.LocationRoom
        assigned_to   = $Values.AssignedTo
        installed_at  = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        installed_by  = "$env:USERDOMAIN\$env:USERNAME"
        agent_version = $AgentVersion
    } | ConvertTo-Json -Depth 4
    Set-Content -Path $ConfigFile -Value $json -Encoding UTF8
    # Token tersimpan lokal: batasi ke SYSTEM + Administrators saja.
    try {
        & icacls $ConfigFile /inheritance:r /grant:r 'SYSTEM:(F)' 'Administrators:(F)' | Out-Null
    } catch {
        Write-Warning "Gagal membatasi ACL config: $_"
    }
}

function Register-AgentTask {
    $arg = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$InstalledScript`" -FromConfig"
    try {
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
        $trigger = New-ScheduledTaskTrigger -Daily -At '12:05'
        $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' `
            -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings -Force | Out-Null
        Write-Host "[it-agent] Scheduled task '$TaskName' terdaftar (harian 12:05, SYSTEM)."
    } catch {
        Write-Warning "Register-ScheduledTask gagal ($_), mencoba schtasks."
        $tr = "powershell.exe $arg"
        & schtasks /Create /SC DAILY /ST 12:05 /TN $TaskName /TR $tr /RU SYSTEM /RL HIGHEST /F | Out-Null
    }
}

function Update-AgentIfNeeded {
    param([string] $BaseUrl, [string] $TokenValue)
    try {
        $headers = @{ 'X-IT-TOKEN' = $TokenValue }
        $info = Invoke-RestMethod -Method Get -Headers $headers -TimeoutSec 20 `
            -Uri ($BaseUrl.TrimEnd('/') + '/api/it/agents/version')
        $remote = "$($info.version)"
        if (-not $remote) { return }
        $needUpdate = $false
        try {
            $needUpdate = ([version]$remote -gt [version]$AgentVersion)
        } catch {
            $needUpdate = ($remote -ne $AgentVersion)
        }
        if (-not $needUpdate) { return }
        Write-Host "[it-agent] versi server $remote > lokal $AgentVersion — memperbarui."
        $tmp = Join-Path $InstallDir 'it_inventory_agent.new.ps1'
        Invoke-WebRequest -Method Get -Headers $headers -TimeoutSec 30 `
            -Uri ($BaseUrl.TrimEnd('/') + '/api/it/agents/package') -OutFile $tmp
        $body = Get-Content -Raw -Path $tmp
        if ($body -notmatch 'BPF-WORKHUB-IT-ASSET-AGENT') {
            Remove-Item $tmp -Force -ErrorAction SilentlyContinue
            Write-Warning 'Paket update tidak valid (penanda tidak ditemukan) — dibatalkan.'
            return
        }
        Move-Item -Path $tmp -Destination $InstalledScript -Force
        Write-Host "[it-agent] agen diperbarui ke $remote (berlaku pada eksekusi berikutnya)."
    } catch {
        Write-Warning "Cek update dilewati: $_"
    }
}

function Send-Json {
    param([string] $Uri, [hashtable] $Headers, [object] $Payload)
    $body = [System.Text.Encoding]::UTF8.GetBytes(($Payload | ConvertTo-Json -Depth 8 -Compress))
    return Invoke-RestMethod -Method Post -Uri $Uri -Headers $Headers `
        -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 60
}

# ------------------------------------------------------------------ mode install
if ($Install) {
    if (-not (Test-IsAdmin)) {
        throw 'Mode -Install butuh PowerShell sebagai Administrator.'
    }
    if (-not $ApiUrl) {
        throw 'Mode -Install butuh -ApiUrl.'
    }
    if (-not $Token -and $TokenFile) {
        if (-not (Test-Path -LiteralPath $TokenFile)) {
            throw "Berkas token tidak ditemukan: $TokenFile"
        }
        $Token = (Get-Content -Raw -LiteralPath $TokenFile).Trim()
    }
    if (-not $Token) {
        throw 'Mode -Install butuh -Token atau -TokenFile.'
    }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    if ($ScriptPath -and ($ScriptPath -ne $InstalledScript)) {
        Copy-Item -Path $ScriptPath -Destination $InstalledScript -Force
    }
    Save-AgentConfig @{
        ApiUrl = $ApiUrl.TrimEnd('/'); Token = $Token; Branch = $Branch
        LocationRoom = $LocationRoom; AssignedTo = $AssignedTo
    }
    Register-AgentTask
    if ($DeleteTokenFile -and $TokenFile) {
        Remove-Item -LiteralPath $TokenFile -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[it-agent] terpasang di $InstallDir (versi $AgentVersion)."
    if (-not $DryRun) {
        $ApiUrl = $ApiUrl.TrimEnd('/')
    }
}

# --------------------------------------------------------------- mode config
if ($FromConfig) {
    $cfg = Get-AgentConfig
    $ApiUrl = "$($cfg.api_url)".TrimEnd('/')
    $Token = "$($cfg.token)"
    $Branch = "$($cfg.branch)"
    $LocationRoom = "$($cfg.location_room)"
    $AssignedTo = "$($cfg.assigned_to)"
    if (-not $SkipUpdate) {
        Update-AgentIfNeeded -BaseUrl $ApiUrl -TokenValue $Token
    }
}

if (-not $FromConfig -and -not $Install) {
    if (-not $ApiUrl -or -not $Token) {
        throw 'Butuh -ApiUrl dan -Token (atau jalankan dengan -FromConfig / -Install).'
    }
}

if ($Token -match '^(CHANGE_ME|)$') {
    throw 'Token belum diisi. Salin nilai IT_DISCOVERY_TOKEN dari .env aplikasi.'
}

# ------------------------------------------------------------------ inventaris
$cs = Get-CimInstance -ClassName Win32_ComputerSystem
$os = Get-CimInstance -ClassName Win32_OperatingSystem
$cpu = Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1
$bios = Get-CimInstance -ClassName Win32_BIOS
$board = Get-CimInstance -ClassName Win32_BaseBoard
$disks = Get-CimInstance -ClassName Win32_DiskDrive |
    Where-Object { $_.MediaType -notlike '*Removable*' }

$ramGb = [math]::Round(($cs.TotalPhysicalMemory / 1GB), 1)
$diskList = @()
foreach ($d in $disks) {
    $diskList += [ordered]@{
        model   = "$($d.Model)".Trim()
        size_gb = if ($d.Size) { [math]::Round($d.Size / 1GB, 1) } else { 0 }
        serial  = "$($d.SerialNumber)".Trim()
    }
}

$ipAddresses = @()
$macAddress = ''
try {
    $net = Get-CimInstance -ClassName Win32_NetworkAdapterConfiguration |
        Where-Object { $_.IPEnabled -eq $true }
    foreach ($n in $net) {
        foreach ($ip in @($n.IPAddress)) {
            if ($ip -match '^\d+\.\d+\.\d+\.\d+$') { $ipAddresses += $ip }
        }
        if (-not $macAddress -and $n.MACAddress) { $macAddress = $n.MACAddress }
    }
} catch {
    Write-Warning "Gagal membaca adaptor jaringan: $_"
}
$primaryIp = $ipAddresses | Where-Object { $_ -notmatch '^169\.254\.' } |
    Select-Object -First 1

$specs = [ordered]@{
    cpu           = "$($cpu.Name)".Trim()
    cpu_cores     = $cpu.NumberOfCores
    cpu_threads   = $cpu.NumberOfLogicalProcessors
    ram_gb        = $ramGb
    disks         = $diskList
    motherboard   = "$($board.Manufacturer) $($board.Product)".Trim()
    bios_version  = "$($bios.SMBIOSBIOSVersion)".Trim()
    os_arch       = $os.OSArchitecture
    logged_user   = "$($cs.UserName)".Trim()
    domain        = "$($cs.Domain)".Trim()
    model         = "$($cs.Model)".Trim()
    serial_number = "$($bios.SerialNumber)".Trim()
    collected_at  = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
}

$serial = "$($bios.SerialNumber)".Trim()
if ([string]::IsNullOrWhiteSpace($serial) -or $serial -match '^(To Be Filled|Default|0+)$') {
    $serial = "$($cs.Name)".Trim()
}

$osName = "$($os.Caption) $($os.Version)".Trim()
$device = [ordered]@{
    ip            = $primaryIp
    mac           = $macAddress.ToUpper()
    hostname      = $env:COMPUTERNAME
    vendor        = "$($cs.Manufacturer)".Trim()
    ports         = @()   # agen WMI tidak memindai port
    ad_os         = $osName
    specs         = $specs
    source        = 'wmi'
    model         = "$($cs.Model)".Trim()
    serial        = $serial
    location_room = $LocationRoom
    assigned_to   = $AssignedTo
}

$payload = [ordered]@{
    branch_code = $Branch
    method      = 'wmi'
    subnets     = @()
    devices     = @($device)
}

Write-Host "[it-agent] $($env:COMPUTERNAME) → $Branch / $primaryIp (serial: $serial, versi $AgentVersion)"

if ($DryRun) {
    $payload | ConvertTo-Json -Depth 8
    return
}

$headers = @{ 'X-IT-TOKEN' = $Token }
$base = $ApiUrl.TrimEnd('/')
$discoveryOk = $false
$discoveryMsg = ''
try {
    $resp = Send-Json -Uri "$base/api/it/discovery/agent" -Headers $headers -Payload $payload
    $discoveryOk = $true
    Write-Host "[it-agent] kandidat OK: run_id=$($resp.run_id) found=$($resp.found) new=$($resp.new)"
} catch {
    $discoveryMsg = "$_"
    Write-Warning "[it-agent] gagal kirim kandidat: $discoveryMsg"
}

# Registry cakupan: satu baris per PC. Status 'installed' hanya bila data
# perangkat berhasil terkirim — kalau gagal, tandai agar terlihat di dashboard.
$report = [ordered]@{
    branch_code    = $Branch
    hostname       = $env:COMPUTERNAME
    ip             = $primaryIp
    mac            = $macAddress.ToUpper()
    os_name        = $osName
    agent_version  = $AgentVersion
    install_method = if ($InstallMethod) { $InstallMethod } `
        elseif ($FromConfig) { 'wmi-task' } else { 'wmi-manual' }
    status         = if ($discoveryOk) { 'installed' } else { 'failed' }
    message        = if ($discoveryOk) { "serial=$serial" } else { $discoveryMsg }
}
try {
    $r2 = Send-Json -Uri "$base/api/it/agents/report" -Headers $headers -Payload $report
    Write-Host "[it-agent] registry OK: updated=$($r2.updated)"
} catch {
    Write-Warning "[it-agent] gagal lapor registry: $_"
}

if (-not $discoveryOk) { exit 1 }
exit 0
