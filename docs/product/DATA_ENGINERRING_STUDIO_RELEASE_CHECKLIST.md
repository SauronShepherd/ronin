# Data Enginerring Studio — release checklist

## Local quality gate

Desde `repo-analysis`:

```powershell
$files = Get-ChildItem tests -Filter 'test_data_engineering_*.py' |
  ForEach-Object { $_.FullName }
pytest -q @files
ruff check python/studio_data_engineering tools/data_engineering_qualification.py
python -m compileall -q python/studio_data_engineering
```

Pass: todos los tests en verde, Ruff limpio y bytecode compilable.

## HTTP/UI gate

```powershell
pytest -q tests/test_studio_static.py tests/test_data_engineering_ui.py
```

Pass: los tres assets se sirven bajo `/studio/` y la UI puede validar,
previsualizar y enviar un run.

## Spark Connect gate

Configurar:

```powershell
$env:SPARK_CONNECT_ENDPOINT = 'sc://spark-connect:15002'
```

Ejecutar:

```powershell
pytest -q tests/e2e/test_data_engineering_external.py -k spark
```

Pass: `select 1` devuelve una fila y el resultado conserva endpoint y métrica.

### Qualification realizada en Windows

Con Spark 4.2.0 instalado, el servidor oficial se levantó con:

```powershell
$env:PYSPARK_PYTHON = 'C:\Python313\python.exe'
$env:PYSPARK_DRIVER_PYTHON = $env:PYSPARK_PYTHON
$env:SPARK_HOME = '...\site-packages\pyspark'
spark-submit.cmd --class org.apache.spark.sql.connect.service.SparkConnectServer `
  "$env:SPARK_HOME\jars\spark-connect_2.13-4.2.0.jar"
```

El adapter de Ronin ejecutó `select 1 as value` contra
`sc://127.0.0.1:15002` y devolvió `row_count=1`. El worker produjo estado
`succeeded` y evidence `data-engineering.spark-connect`.

Para repetir la qualification completa (Spark smoke + SDP validation):

```powershell
$env:SDP_PROJECT_ID = '<project-id-importado-en-sdpstudio>'
$env:SDPSTUDIO_DATA_ROOT = '<ruta-de-datos-sdpstudio>'
pwsh tools/run_data_engineering_external_e2e.ps1 `
  -SparkHome '<ruta-a-site-packages\\pyspark>'
```

## SDP Studio gate

El gate operativo obligatorio usa el CLI oficial instalado de SDP Studio y el
proyecto importado en `SDP_PROJECT_ID`:

```powershell
$env:SDP_PROJECT_ID = '<project-id-importado-en-sdpstudio>'
$env:SDPSTUDIO_DATA_ROOT = '<ruta-de-datos-sdpstudio>'
pytest -q tests/e2e/test_data_engineering_external.py -k 'spark or real_cli'
```

Pass: Spark Connect devuelve una fila, la evidencia queda persistida y
`sdpstudio validate` termina con `Pipeline model is valid.`. Este es el gate
que ejecuta `tools/run_data_engineering_external_e2e.ps1`.

La siguiente variante valida además el contrato opcional JSON-stdio del
adaptador, pero no sustituye al CLI oficial:

Configurar el comando que acepte el contrato JSON por stdin/stdout:

```powershell
$env:SDP_STUDIO_COMMAND = 'sdp-studio compile --json-stdio'
```

Ejecutar:

```powershell
pytest -q tests/e2e/test_data_engineering_external.py -k sdp
```

Pass: importación lossless, validación y compilación devuelven JSON válido.

## Durable execution gate

Verificar en el entorno Ronin:

1. `GET /v1/data-engineering/health` devuelve `status=ready`.
2. Preview local produce artifact y `StoredEvidenceRef`.
3. El outbox publica y marca `published_at` sólo después de éxito.
4. La pérdida de lease no permite escribir evidence con token antiguo.
5. El lineage observado conserva `execution_ref` y exporta OpenLineage.

## Release decision

El módulo puede declararse **100%** sólo cuando todos los bloques anteriores
estén ejecutados y el gate operativo `spark or real_cli` no aparezca como
`skipped`. El gate JSON-stdio es opcional. Si Docker, Spark Connect o SDP
Studio no están disponibles, el estado correcto es
`implementation-ready / external-validation-pending`, nunca `100% operativo`.
