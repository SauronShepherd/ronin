ARG PYTHON_IMAGE=python:3.11-alpine3.24@sha256:09d17d5e4c16d0a7a1eea690bcb7c6ab8616b211f8421e429e97c1bef5bd0ed2

FROM ${PYTHON_IMAGE} AS wheel
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY python ./python
COPY web ./web
COPY agent-skills ./agent-skills
RUN python -m pip wheel --no-deps --wheel-dir /wheels .

FROM docker:29.9.2-cli-alpine3.24@sha256:5e6baf67325a79f64ed3bed6863954d5e05d0f3d4e57cbdb14809346814bbfdb AS docker-cli

FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="Ronin"
LABEL org.opencontainers.image.description="Ronin v0.1 local control plane, worker, and execution image"
LABEL org.opencontainers.image.source="https://github.com/SauronShepherd/ronin"
LABEL org.opencontainers.image.licenses="Apache-2.0"

COPY docker/apk-runtime.lock /tmp/apk-runtime.lock
RUN set -eux; \
    sed -i 's/\r$//' /tmp/apk-runtime.lock; \
    apk add --no-cache $(cat /tmp/apk-runtime.lock); \
    rm /tmp/apk-runtime.lock; \
    groupadd --gid 65532 ronin; \
    adduser -D -h /home/ronin -u 65532 -G ronin -s /sbin/nologin ronin; \
    install -d -o 65532 -g 65532 /var/lib/ronin /workspace; \
    install -d /usr/local/lib/ronin

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=wheel /wheels /tmp/wheels
COPY docker/pip-bootstrap.lock /tmp/pip-bootstrap.lock
COPY docker/requirements-runtime.lock /tmp/requirements-runtime.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/pip-bootstrap.lock \
    && python -m pip install --no-cache-dir --no-deps /tmp/wheels/*.whl \
    && python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements-runtime.lock \
    && python -m pip uninstall --yes pip setuptools wheel jaraco.context \
    && rm -rf /tmp/wheels /tmp/pip-bootstrap.lock /tmp/requirements-runtime.lock

COPY docker/container-entrypoint.sh /usr/local/bin/ronin-container-entrypoint
COPY docker/healthcheck.py /usr/local/lib/ronin/healthcheck.py
COPY web /usr/local/lib/ronin/web
RUN sed -i 's/\r$//' /usr/local/bin/ronin-container-entrypoint \
    && chmod 0755 /usr/local/bin/ronin-container-entrypoint

ENV HOME=/home/ronin \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspace
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/ronin-container-entrypoint"]
CMD ["ronin", "serve"]
