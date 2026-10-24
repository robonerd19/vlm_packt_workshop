#!/usr/bin/env bash
# Installs Docker Engine + Compose v2 and the NVIDIA Container Toolkit on Ubuntu 24.04;
# `cpu` skips the toolkit for machines without an NVIDIA GPU. Safe to re-run: anything already working is skipped.
# Follows https://docs.docker.com/engine/install/ubuntu/ and
# https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
set -euo pipefail
usage() { echo 'Usage: bash scripts/install_prereqs.sh [gpu|cpu]   (default gpu; cpu skips NVIDIA Container Toolkit)'; }
mode="${1:-gpu}"
case "$mode" in
  cpu|gpu) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

as_root() { if ((EUID)); then sudo "$@"; else "$@"; fi; }
# Plain docker once the user is in the docker group, sudo before that.
dk() { if docker info >/dev/null 2>&1; then docker "$@"; else as_root docker "$@"; fi; }
user="${SUDO_USER:-$USER}"

. /etc/os-release
[[ "$ID" == ubuntu ]] || { echo "Ubuntu is required (found $ID)." >&2; exit 1; }
[[ "$VERSION_ID" == 24.04 ]] || echo "Warning: tested on Ubuntu 24.04, found $VERSION_ID." >&2

# --- Docker Engine + Compose v2 ---
if docker compose version >/dev/null 2>&1; then
  echo "Docker and Compose v2 already installed: $(docker compose version)"
else
  echo 'Installing Docker Engine and Compose v2...'
  # Ubuntu's own docker packages conflict with Docker's; images in /var/lib/docker are kept.
  for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
    if dpkg -s "$pkg" >/dev/null 2>&1; then as_root apt-get remove -y "$pkg"; fi
  done
  as_root apt-get update
  as_root apt-get install -y ca-certificates curl
  as_root install -m 0755 -d /etc/apt/keyrings
  as_root curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  as_root chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
    | as_root tee /etc/apt/sources.list.d/docker.list >/dev/null
  as_root apt-get update
  as_root apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  as_root systemctl enable --now docker
fi

# Lets the workshop scripts run `docker` without sudo (needs a new login to apply).
relogin=false
if [[ "$user" != root ]] && ! id -nG "$user" | grep -qw docker; then
  as_root usermod -aG docker "$user"
  relogin=true
fi

# --- NVIDIA Container Toolkit ---
if [[ "$mode" == gpu ]]; then
  if ! command -v nvidia-smi >/dev/null || ! nvidia-smi >/dev/null 2>&1; then
    echo 'No working NVIDIA driver (nvidia-smi failed). Install one, reboot, and re-run:' >&2
    echo '  sudo ubuntu-drivers install && sudo reboot' >&2
    echo 'No NVIDIA GPU? Run: bash scripts/install_prereqs.sh cpu' >&2
    exit 1
  fi
  if command -v nvidia-ctk >/dev/null; then
    echo "NVIDIA Container Toolkit already installed: $(nvidia-ctk --version | head -1)"
  else
    echo 'Installing NVIDIA Container Toolkit...'
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
      | as_root gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
      | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
      | as_root tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
    as_root apt-get update
    as_root apt-get install -y nvidia-container-toolkit
  fi
  if grep -qs '"nvidia"' /etc/docker/daemon.json; then
    echo 'Docker already has the nvidia runtime.'
  else
    # Restarting Docker stops running containers, so only do it when the runtime is missing.
    as_root nvidia-ctk runtime configure --runtime=docker
    as_root systemctl restart docker
  fi
fi

# --- Verify ---
echo 'Checking Docker...'
dk run --rm hello-world >/dev/null
echo 'Docker OK.'
if [[ "$mode" == gpu ]]; then
  echo 'Checking GPU access from a container...'
  dk run --rm --gpus all ubuntu:24.04 nvidia-smi -L
  echo 'GPU OK.'
fi
if $relogin; then
  echo "Added $user to the docker group. Log out and back in (or run 'newgrp docker') before using the workshop scripts."
fi
echo 'Prerequisites ready.'
