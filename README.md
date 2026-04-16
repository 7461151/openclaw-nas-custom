# OpenClaw NAS Custom Image

This repository publishes a custom OpenClaw image for NAS use.

It keeps the current NAS customizations:

- QQBot heartbeat patch
- QQ reply model-name prefix patch
- QQ private-chat delivery mirror session normalization
- QQ private-chat legacy `group:c2c` session reconciliation
- printer bootstrap entrypoint
- Chinese locale and required print/document packages

The image is published to:

- `ghcr.io/7461151/openclaw-nas-custom:latest`

## How It Works

- `Dockerfile` builds on top of `ghcr.io/openclaw/openclaw:latest`
- GitHub Actions rebuilds and pushes the image
- NAS only needs to pull the published image and redeploy

## Files

- `Dockerfile`: image build definition
- `docker-compose.yaml`: NAS deployment file using the published GHCR image
- `compose.build.local.yaml`: original local-build compose file for debugging
- `print-entrypoint.sh`: printer setup and runtime patch bootstrap
- `patch-qqbot-model-label.py`: runtime QQ model-label patch
- `patch-qqbot-delivery-mirror-session.py`: runtime QQ private-chat mirror session normalization
- `patch-qqbot-heartbeat.py`: heartbeat patch
- `reconcile-qqbot-c2c-legacy-sessions.py`: startup cleanup for stale QQ private-chat legacy session keys

## NAS Update Flow

After this repository is set up, NAS updates are:

```bash
cd /volume2/docker/openclaw
docker compose pull
docker compose up -d
```

If your NAS container manager supports "redeploy + pull latest image", that is enough after switching to this `docker-compose.yaml`.

## First-Time NAS Switch

Replace the current compose file on NAS with the `docker-compose.yaml` from this repository, then redeploy once.

## Manual Publish

You can also manually trigger the `Publish Image` workflow from GitHub Actions.
