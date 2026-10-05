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
# A cache key for the Frappe build: upgrade.sh sets it to the newest v16 release (e.g. v16.36.0)
# only when that is newer than the Frappe already built, so this slow step (10 minutes or more)
# runs again only for a new Frappe release. The same value keeps the cached layer.
ARG FRAPPE_COMMIT=
USER frappe

# 1. Frappe framework with its Python and Node packages, in a stage of its own. (Keep this line
#    exactly as it is: any change to it rebuilds Frappe for everyone once.)
RUN echo "Frappe ${FRAPPE_BRANCH} ${FRAPPE_COMMIT}" && bench init \
      --frappe-branch=${FRAPPE_BRANCH} \
      --frappe-path=${FRAPPE_PATH} \
      --no-procfile --no-backups --skip-redis-config-generation \
      /home/frappe/frappe-bench

FROM ${FRAPPE_IMAGE_PREFIX}/base:${FRAPPE_BRANCH} AS backend
USER frappe
# the whole Frappe bench (about 1 GB): the same layer as last time unless Frappe changed, so an
# upgrade of Research Desk alone neither rebuilds nor copies it
COPY --from=builder --chown=frappe /home/frappe/frappe-bench /home/frappe/frappe-bench
WORKDIR /home/frappe/frappe-bench
RUN echo "{}" > sites/common_site_config.json && find apps -mindepth 1 -path "*/.git" | xargs rm -fr

USER root
# OCR for re-reading pages (reocr.py): Tesseract with every language model it has ("all", Debian's
# tesseract-ocr-all), so any book's language can be read. Its own layer, cached across upgrades.
# A smaller image: OCR_LANGS="kan hin eng" (codes of tesseract-ocr-<code>) in .env, then upgrade
ARG OCR_LANGS="all"
# the list the image was built with, for Server → Requirements
ENV RESDESK_OCR_LANGS="${OCR_LANGS}"
RUN apt-get update -q \
 && apt-get install -y -q --no-install-recommends tesseract-ocr poppler-utils \
      $(if [ "${OCR_LANGS}" = all ]; then echo tesseract-ocr-all; else for l in ${OCR_LANGS}; do echo tesseract-ocr-$l; done; fi) \
 && rm -rf /var/lib/apt/lists/*
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker/start.sh /usr/local/bin/start.sh
COPY docker/create-site.sh /usr/local/bin/create-site.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh /usr/local/bin/start.sh /usr/local/bin/create-site.sh \
    && mkdir -p /preservation && chown frappe /preservation   # a new volume there starts writable
USER frappe

# 2. This app: a few MB, the only part rebuilt when Research Desk changes (under a minute)
COPY --chown=frappe . apps/sok_resdesk
RUN rm -rf apps/sok_resdesk/.git \
 && uv pip install --python env/bin/python -e apps/sok_resdesk \
 && sed -i -e '$a\' sites/apps.txt && echo "sok_resdesk" >> sites/apps.txt \
 && bench build --app sok_resdesk \
 && cp -r sites/assets assets && rm -rf sites/assets

# (built assets stay in the image, in assets/; the entrypoint links them into the sites volume)
# declared last: changes made inside a volume after it is declared would be lost
VOLUME ["/home/frappe/frappe-bench/sites", "/home/frappe/frappe-bench/logs"]

LABEL org.opencontainers.image.title="SOK Research Desk" \
      org.opencontainers.image.description="Research portal and digital library on Frappe" \
      org.opencontainers.image.licenses="MIT"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["start.sh"]
