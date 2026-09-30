# The updater helper (./resdesk.sh updater on): Docker CLI + Compose, git, bash and Python,
# enough to run ./upgrade.sh and ./resdesk.sh for the Server page in the Desk.
FROM docker:28-cli
RUN apk add --no-cache bash git python3 curl coreutils findutils grep sed gawk tar gzip procps openssh-client rsync \
 && git config --system --add safe.directory '*'
ENV HOME=/tmp
CMD ["python3", "scripts/agent.py"]
