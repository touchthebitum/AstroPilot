param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
foreach ($entry in @(@{Name='valid';HostName='api.open-meteo.com'}, @{Name='wrong';HostName='wrong.invalid'})) {
    $csp = [System.Security.Cryptography.CspParameters]::new(24)
    $csp.Flags = [System.Security.Cryptography.CspProviderFlags]::CreateEphemeralKey
    $rsa = [System.Security.Cryptography.RSACryptoServiceProvider]::new(2048,$csp)
    $rsa.PersistKeyInCsp = $false
    $request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
        ('CN=' + $entry.HostName), $rsa, [System.Security.Cryptography.HashAlgorithmName]::SHA256,
        [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
    $san = [System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
    $san.AddDnsName($entry.HostName)
    $request.CertificateExtensions.Add($san.Build())
    $request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($true,$false,0,$true))
    $usage = [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -bor [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment -bor [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyCertSign
    $request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new($usage,$true))
    $oids = [System.Security.Cryptography.OidCollection]::new()
    [void]$oids.Add([System.Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.1'))
    $request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($oids,$false))
    $certificate = $request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddMinutes(-5),[DateTimeOffset]::UtcNow.AddDays(2))
    $parameters = $rsa.ExportParameters($true)
    $document = @{certificate=[Convert]::ToBase64String($certificate.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))}
    foreach ($name in @('Modulus','Exponent','D','P','Q','DP','DQ','InverseQ')) {
        $document[$name] = [Convert]::ToBase64String($parameters.$name)
    }
    $path = Join-Path $OutputDirectory ($entry.Name + '.json')
    [IO.File]::WriteAllText($path,($document | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    $certificate.Dispose()
    $rsa.Dispose()
}
# Certificate material is generated in this new test directory only; no certificate store is used.
