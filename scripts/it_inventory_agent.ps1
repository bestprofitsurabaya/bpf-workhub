<#
.SYNOPSIS
  Agen WMI Inventaris IT — kirim data hardware PC Windows ke BPF WorkHub.

.DESCRIPTION
  Dijalankan DI PC yang akan diinventaris (oleh IT, manual atau lewat
  Task Scheduler / GPO logon script). Membaca WMI (CIM) lokal, lalu POST ke
  `/api/it/discovery/agent` dengan header `X-IT-TOKEN`.

  Hasilnya masuk sebagai *kandidat* di tab "Jaringan" — IT tetap memutuskan
  "Jadikan Aset" atau "Abaikan". Agen ini TIDAK membuat aset otomatis dan
  TIDAK membaca berkas pengguna; hanya metadata perangkat.

.PARAMETER ApiUrl
  Basis URL aplikasi, mis. https://nasbpfsby.duckdns.org  (atau
  http://192.168.2.31:5001 bila dijalankan dari dalam LAN).

.PARAMETER Token
  Token agen = nilai `IT_DISCOVERY_TOKEN` di `.env` aplikasi.

.PARAMETER Branch
  Kode cabang pemilik PC (SBY, JKT, BDG, ...).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\it_inventory_agent.ps1 `
      -ApiUrl https://nasbpfsby.duckdns.org -Token "xxxx" -Branch SBY

.NOTES
  Jadwal disarankan: Task Scheduler harian 12:00 (SYSTEM/akun IT), atau
  sekali saat penyerahan perangkat baru.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $ApiUrl,
    [Parameter(Mandatory = $true)] [string] $Token,
    [string] $Branch = 'SBY',
    [string] $LocationRoom = '',
    [string] $AssignedTo = '',
    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'

function Get-FirstValue($value) {
    if ($null -eq $value) { return '' }
    if ($value -is [array]) { return ($value | Select-Object -First 1) }
    return $value
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
        model  = "$($d.Model)".Trim()
        size_gb = if ($d.Size) { [math]::Round($d.Size / 1GB, 1) } else { 0 }
        serial = "$($d.SerialNumber)".Trim()
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
    cpu          = "$($cpu.Name)".Trim()
    cpu_cores    = $cpu.NumberOfCores
    cpu_threads  = $cpu.NumberOfLogicalProcessors
    ram_gb       = $ramGb
    disks        = $diskList
    motherboard  = "$($board.Manufacturer) $($board.Product)".Trim()
    bios_version = "$($bios.SMBIOSBIOSVersion)".Trim()
    os_arch      = $os.OSArchitecture
    logged_user  = "$($cs.UserName)".Trim()
    domain       = "$($cs.Domain)".Trim()
    model        = "$($cs.Model)".Trim()
    serial_number = "$($bios.SerialNumber)".Trim()
    collected_at = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
}

$serial = "$($bios.SerialNumber)".Trim()
if ([string]::IsNullOrWhiteSpace($serial) -or $serial -match '^(To Be Filled|Default|0+)$') {
    $serial = "$($cs.Name)".Trim()
}

$device = [ordered]@{
    ip        = $primaryIp
    mac       = $macAddress.ToUpper()
    hostname  = $env:COMPUTERNAME
    vendor    = "$($cs.Manufacturer)".Trim()
    ports     = @()   # agen WMI tidak memindai port
    ad_os     = "$($os.Caption) $($os.Version)".Trim()
    specs     = $specs
    source    = 'wmi'
    model     = "$($cs.Model)".Trim()
    serial    = $serial
    location_room = $LocationRoom
    assigned_to   = $AssignedTo
}

$payload = [ordered]@{
    branch_code = $Branch
    method      = 'wmi'
    subnets     = @()
    devices     = @($device)
}

$json = $payload | ConvertTo-Json -Depth 8 -Compress
Write-Host "[it-agent] $($env:COMPUTERNAME) → $Branch / $primaryIp (serial: $serial)"

if ($DryRun) {
    $payload | ConvertTo-Json -Depth 8
    return
}

if ($Token -match '^(CHANGE_ME|)$') {
    throw 'Token belum diisi. Salin nilai IT_DISCOVERY_TOKEN dari .env aplikasi.'
}

try {
    $resp = Invoke-RestMethod -Method Post -Uri ($ApiUrl.TrimEnd('/') + '/api/it/discovery/agent') `
        -Headers @{ 'X-IT-TOKEN' = $Token } `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($json)) `
        -TimeoutSec 60
    Write-Host "[it-agent] OK: run_id=$($resp.run_id) found=$($resp.found) new=$($resp.new)"
    exit 0
}
catch {
    Write-Error "[it-agent] gagal kirim: $_"
    exit 1
}
