# syntax=docker/dockerfile:1
# xteink server image: web UI build -> python wheel install -> slim runtime + pandoc.
# Multi-arch: works for linux/arm64 and linux/amd64 (all base images are multi-arch).

# --- Stage 1: web assets -------------------------------------------------------------
# Builds web/ (Vite, outDir ../xteink/server/_webassets) when web/package.json exists.
# Without web/, an empty _webassets dir is produced and the server serves a placeholder.
FROM node:22-bookworm-slim AS web
WORKDIR /src
COPY . /src
RUN mkdir -p /src/xteink/server/_webassets \
 && if [ -f web/package.json ]; then \
      cd web && npm ci && npm run build; \
    else \
      echo "web/package.json absent: skipping web build (placeholder UI)"; \
    fi

# --- Stage 2: install xteink[server] into an isolated prefix ---------------------------
FROM python:3.12-slim-bookworm AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY . /src
RUN pip install --prefix=/install ".[server]"
# Hatch skips VCS-ignored files (the _webassets build output), so place the web stage's
# output into the installed package explicitly.
COPY --from=web /src/xteink/server/_webassets /tmp/_webassets
RUN SP="$(find /install -type d -name site-packages | head -1)" \
 && rm -rf "$SP/xteink/server/_webassets" \
 && cp -r /tmp/_webassets "$SP/xteink/server/_webassets"

# --- Stage 3: pinned upstream pandoc ----------------------------------------------------
# Debian's pandoc package keeps data files outside the binary, so `pandoc --sandbox`
# (which xteink uses) cannot find them ("Could not find data file data/epub.css").
# The upstream static release embeds them. Checksums verified per architecture.
FROM debian:bookworm-slim AS pandoc
ARG TARGETARCH
ARG PANDOC_VERSION=3.12
ARG PANDOC_SHA256_AMD64=67d7d011fed8c8543306022b985b9b2499ab9b74818df91d8727c7e9ebc5ba06
ARG PANDOC_SHA256_ARM64=6cefcf7100e23a99447c26f89d1ff5b253f3407fcef99a9e27ae06f3ed16cb82
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && case "$TARGETARCH" in \
      amd64) SHA="$PANDOC_SHA256_AMD64" ;; \
      arm64) SHA="$PANDOC_SHA256_ARM64" ;; \
      *) echo "unsupported arch: $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl -fsSL -o /tmp/pandoc.tgz \
      "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-linux-${TARGETARCH}.tar.gz" \
 && echo "${SHA}  /tmp/pandoc.tgz" | sha256sum -c - \
 && tar -xzf /tmp/pandoc.tgz -C /tmp \
 && install -m 0755 "/tmp/pandoc-${PANDOC_VERSION}/bin/pandoc" /usr/local/bin/pandoc

# --- Stage 4: runtime ------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime
RUN useradd --system --uid 10001 --create-home --home-dir /home/xteink xteink \
 && mkdir -p /data && chown xteink:xteink /data
COPY --from=pandoc /usr/local/bin/pandoc /usr/local/bin/pandoc
COPY --from=build /install /usr/local
ENV PYTHONUNBUFFERED=1 \
    XTEINK_DATA_DIR=/data \
    XTEINK_BIND=0.0.0.0 \
    XTEINK_PORT=8780 \
    XTEINK_DEVICE_PORT=8781
USER xteink
VOLUME ["/data"]
EXPOSE 8780 8781 8782
CMD ["python", "-m", "xteink.server", "serve"]
