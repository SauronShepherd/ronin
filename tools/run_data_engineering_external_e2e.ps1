param(
  [string]$SparkHome = $env:SPARK_HOME,
  [string]$SparkEndpoint = "sc://127.0.0.1:15002",
  [string]$SdpProjectId = $env:SDP_PROJECT_ID,
  [string]$SdpDataRoot = $env:SDPSTUDIO_DATA_ROOT
)

$ErrorActionPreference = "Stop"
if (-not $SparkHome) { throw "SPARK_HOME or -SparkHome is required" }
if (-not $SdpProjectId) { throw "SDP_PROJECT_ID or -SdpProjectId is required" }
if (-not $SdpDataRoot) { throw "SDPSTUDIO_DATA_ROOT or -SdpDataRoot is required" }

$jar = Join-Path $SparkHome "jars\spark-connect_2.13-4.2.0.jar"
$submit = Join-Path $SparkHome "..\..\..\Scripts\spark-submit.cmd"
if (-not (Test-Path $jar)) { throw "Spark Connect jar not found: $jar" }
if (-not (Test-Path $submit)) { throw "spark-submit.cmd not found: $submit" }

$env:PYSPARK_PYTHON = (Get-Command python).Source
$env:PYSPARK_DRIVER_PYTHON = $env:PYSPARK_PYTHON
$env:SPARK_HOME = $SparkHome
$env:SPARK_CONNECT_ENDPOINT = $SparkEndpoint
$env:SDPSTUDIO_DATA_ROOT = $SdpDataRoot
$server = Start-Process -FilePath $submit -ArgumentList @(
  "--class", "org.apache.spark.sql.connect.service.SparkConnectServer", $jar
) -PassThru -WindowStyle Hidden
try {
  $ready = $false
  for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
      $connection = [System.Net.Sockets.TcpClient]::new("127.0.0.1", 15002)
      $connection.Dispose()
      $ready = $true
      break
    } catch { Start-Sleep -Seconds 1 }
  }
  if (-not $ready) { throw "Spark Connect did not become ready" }
  pytest -q tests/e2e/test_data_engineering_external.py -k "spark or real_cli"
  sdpstudio validate $SdpProjectId
  if ($LASTEXITCODE -ne 0) { throw "SDP Studio validation failed" }
} finally {
  if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force }
}
