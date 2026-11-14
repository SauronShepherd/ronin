# Manual validation, commits and uploads

Ronin no utiliza GitHub Actions. No hay validación, publicación ni despliegue
automático asociado a un `push`; todas las decisiones de ejecución y subida son
manuales y explícitas.

## 1. Preparar el candidato

Desde un clon limpio y en el commit candidato:

```powershell
git status --short
git rev-parse HEAD
python -m pip install --require-hashes -r requirements-test.lock
python -m pip install --no-deps -e .
```

No se deben incluir artefactos locales no rastreados en el commit. Revisar el
diff y los hashes antes de continuar.

## 2. Ejecutar los gates localmente

El gate principal es local y debe conservar sus salidas:

```powershell
python -m pytest --ignore=tests/perf -q
python -m ruff check .
python -m ruff format --check .
```

Para el navegador, cuando estén instaladas las dependencias bloqueadas:

```powershell
npm --prefix web-tests ci
npm --prefix web-tests exec playwright install chromium
npm --prefix web-tests test -- --workers=1
```

Los gates que requieren Docker, PostgreSQL, Terraform, Floci, proveedores o
clusters se ejecutan manualmente con sus scripts existentes y sólo se declaran
PASS si el servicio está disponible y la salida queda archivada junto al SHA.

## 3. Commit y subida del código

Después de una fase satisfactoria:

```powershell
git diff --check
git status --short
git add <archivos-revisados>
git commit -m "<cambio de la fase>"
git push origin main
git rev-parse HEAD
```

El `push` es una subida manual de Git, no dispara automatizaciones. Verificar
el SHA remoto con `git ls-remote origin refs/heads/main`.

## 4. Publicación manual de imágenes

Sólo con aprobación explícita del responsable de release, identidad de versión
decidida y credenciales cargadas fuera del repositorio:

```powershell
docker build --pull=false -t <registry>/<image>:<version> .
docker image inspect <registry>/<image>:<version> --format '{{.Id}}'
docker push <registry>/<image>:<version>
```

Registrar el digest devuelto por el registry y compararlo con el manifiesto del
candidato. Nunca usar alias mutables como evidencia de una release.

## 5. Evidencia y progreso

Cada fase cerrada debe tener un receipt con SHA, comandos, resultados y límites
de alcance. La matriz `docs/product/PUBLIC_V1_CAPABILITY_MATRIX.md` y
`docs/product/public-v1-status.json` se sincronizan sólo con evidencia local o
de servicios ejecutados manualmente. La ausencia de automatización no convierte
una fase en cualificada: Public v1 permanece `0/13`, `0%`, `NO-GO` hasta que
cada familia y sus gates aprobados tengan evidencia independiente.
