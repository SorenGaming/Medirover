param([string]$BackupFolder = (Join-Path $PSScriptRoot 'Backups'))

$ErrorActionPreference = 'Stop'
$inputStream = [Console]::OpenStandardInput()
$headerBytes = [System.Collections.Generic.List[byte]]::new()
for ($i = 0; $i -lt 100; $i++) {
    $byte = $inputStream.ReadByte()
    if ($byte -lt 0 -or $byte -eq 10) { break }
    $headerBytes.Add([byte]$byte)
}

$header = [Text.Encoding]::ASCII.GetString($headerBytes.ToArray())
if ($byte -ne 10 -or $header -cnotmatch '^([0-9a-f]{64}) ([1-9][0-9]{0,17})$') {
    throw 'Backuphovedet skal indeholde SHA-256 og antal byte.'
}
$expectedHash = $Matches[1]
$expectedSize = [long]$Matches[2]

$folder = [IO.Directory]::CreateDirectory($BackupFolder)
$timestamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$name = "medirover_demo-$timestamp.dump"
$destination = Join-Path $folder.FullName $name
$partial = Join-Path $folder.FullName ("{0}.partial" -f [Guid]::NewGuid())

try {
    $file = [IO.File]::Open($partial, [IO.FileMode]::CreateNew)
    try {
        $inputStream.CopyTo($file)
    } finally {
        $file.Dispose()
    }

    $reader = [IO.File]::OpenRead($partial)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        if ($reader.Length -ne $expectedSize) { throw 'Backupfilen har forkert størrelse.' }
        $actualHash = [BitConverter]::ToString($sha256.ComputeHash($reader)).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha256.Dispose()
        $reader.Dispose()
    }
    if ($actualHash -cne $expectedHash) { throw 'Backupfilens SHA-256 afviger.' }
    [IO.File]::Move($partial, $destination)
    Write-Output "MEDIROVER_BACKUP_OK $actualHash $name"
} finally {
    if ([IO.File]::Exists($partial)) { [IO.File]::Delete($partial) }
}
