# Research Desk production image: Frappe v16 + sok_resdesk.
# Based on the layered build from https://github.com/frappe/frappe_docker (MIT).
#
#   docker build -f docker/Dockerfile -t sok-resdesk:local .
#
ARG FRAPPE_BRANCH=version-16
ARG FRAPPE_IMAGE_PREFIX=frappe

FROM ${FRAPPE_IMAGE_PREFIX}/build:${FRAPPE_BRANCH} AS builder
ARG FRAPPE_BRANCH=version-16
ARG FRAPPE_PATH=https://github.com/frappe/frappe
# set by upgrade.sh to the newest commit on FRAPPE_BRANCH: a new value rebuilds this layer and so
# brings in Frappe's patch releases; the same value keeps the cached layer (./upgrade.sh --no-frappe)
ARG FRAPPE_COMMIT=
USER frappe

# 1. Frappe framework (cached layer: rebuilt when FRAPPE_BRANCH or FRAPPE_COMMIT changes)
RUN echo "Frappe ${FRAPPE_BRANCH} ${FRAPPE_COMMIT}" && bench init \
      --frappe-branch=${FRAPPE_BRANCH} \
      --frappe-path=${FRAPPE_PATH} \
      --no-procfile --no-backups --skip-redis-config-generation \
      /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench

# 2. This app
COPY --chown=frappe:frappe . apps/sok_resdesk
RUN rm -rf apps/sok_resdesk/.git \
 && uv pip install --python env/bin/python -e apps/sok_resdesk \
 && sed -i -e '$a\' sites/apps.txt && echo "sok_resdesk" >> sites/apps.txt \
 && bench build --app sok_resdesk \
 && echo "{}" > sites/common_site_config.json \
 && find apps -mindepth 1 -path "*/.git" | xargs rm -fr

FROM ${FRAPPE_IMAGE_PREFIX}/base:${FRAPPE_BRANCH} AS backend
USER frappe
COPY --from=builder --chown=frappe:frappe /home/frappe/frappe-bench /home/frappe/frappe-bench
WORKDIR /home/frappe/frappe-bench

# Keep built assets in the image layer; entrypoint links them into the sites volume.
RUN cp -r sites/assets assets && rm -rf sites/assets

VOLUME ["/home/frappe/frappe-bench/sites", "/home/frappe/frappe-bench/logs"]

USER root
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker/start.sh /usr/local/bin/start.sh
COPY docker/create-site.sh /usr/local/bin/create-site.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh /usr/local/bin/start.sh /usr/local/bin/create-site.sh
USER frappe

LABEL org.opencontainers.image.title="SoK Research Desk" \
      org.opencontainers.image.description="Research portal and digital library on Frappe" \
      org.opencontainers.image.licenses="MIT"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["start.sh"]
