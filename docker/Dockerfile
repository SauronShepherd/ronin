ARG PYTHON_IMAGE=python:3.11.16-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84

FROM ${PYTHON_IMAGE} AS wheel
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY python ./python
RUN python -m pip wheel --no-deps --wheel-dir /wheels .

FROM docker:27.3.1-cli-alpine3.20@sha256:328eb399a065780c2cebe9224de003aa14084cf69efae882ac27430f921819b7 AS docker-cli

FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="Ronin"
LABEL org.opencontainers.image.description="Ronin v0.1 local control plane, worker, and execution image"
LABEL org.opencontainers.image.source="https://github.com/SauronShepherd/ronin"
LABEL org.opencontainers.image.licenses="Apache-2.0"

RUN set -eux; \
    apt-get update; \
    apt-get install --no-install-recommends -y ca-certificates git gosu; \
    rm -rf /var/lib/apt/lists/*; \
    useradd --create-home --uid 65532 --shell /usr/sbin/nologin ronin; \
    install -d -o 65532 -g 65532 /var/lib/ronin /workspace; \
    install -d /usr/local/lib/ronin

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=wheel /wheels /tmp/wheels
RUN python -m pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels

COPY docker/container-entrypoint.sh /usr/local/bin/ronin-container-entrypoint
COPY docker/healthcheck.py /usr/local/lib/ronin/healthcheck.py
RUN chmod 0755 /usr/local/bin/ronin-container-entrypoint

ENV HOME=/home/ronin \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspace
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/ronin-container-entrypoint"]
CMD ["ronin", "--help"]
