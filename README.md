# OpenClaw NAS Custom Image

This repository publishes a custom OpenClaw image for NAS use.

It keeps the current NAS customizations:

- QQ reply model-name prefix patch
- GitHub CLI support (`gh`)
- password-based SSH automation support (`sshpass`)
- video download dependency (`yt-dlp`)
- printer bootstrap entrypoint
- Chinese locale and required print/document packages

Removed from this custom image:

- Gemini CLI integration and OAuth sync helpers
- Weixin-specific runtime expectations
- obsolete control-ui delivery model patch
- one-time QQ legacy session reconciliation script

The image is published to:

- `ghcr.io/7461151/openclaw-nas-custom:latest`

## How It Works

- `Dockerfile` builds on top of `ghcr.io/openclaw/openclaw:latest`
- GitHub Actions checks the upstream image every hour and rebuilds only when the upstream base image changes (push and manual runs still build immediately)
- NAS only needs to pull the published image and redeploy

## Files

- `Dockerfile`: image build definition
- `docker-compose.yaml`: NAS deployment file using the published GHCR image
- `compose.build.local.yaml`: original local-build compose file for debugging
- `print-entrypoint.sh`: printer setup and model-label patch bootstrap
- `patch-qqbot-model-label.py`: runtime QQ model-label patch

## NAS Update Flow

After this repository is set up, NAS updates are:

```bash
cd /volume2/docker/openclaw
docker compose pull
docker compose up -d
```

If your NAS container manager supports "redeploy + pull latest image", that is enough after switching to this `docker-compose.yaml`.

The image includes `gh`, so the built-in GitHub skill can use GitHub CLI after authentication is configured.

The image also includes `sshpass`, so tasks inside the container can automate password-based SSH when a key is not available.

The image now also includes `yt-dlp`, so a workspace skill/script can handle YouTube and other media downloads without relying on `web_fetch`.

## First-Time NAS Switch

Replace the current compose file on NAS with the `docker-compose.yaml` from this repository, then redeploy once.

## Manual Publish

You can also manually trigger the `Publish Image` workflow from GitHub Actions.
