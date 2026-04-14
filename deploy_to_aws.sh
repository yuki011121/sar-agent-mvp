#!/usr/bin/env bash
set -euo pipefail

# Required environment variables:
#   EC2_INSTANCE_IP
#   EC2_KEY_PAIR_LOCATION

# Check EC2_INSTANCE_IP
if [ -z "${EC2_INSTANCE_IP:-}" ]; then
  echo "Error: EC2_INSTANCE_IP is not set."
  echo "If you haven't already, deploy your AWS CDK configuration to your account."
  echo "Please export EC2_INSTANCE_IP=<your-instance-ip>"
  exit 1
fi

# Check EC2_KEY_PAIR_LOCATION
if [ -z "${EC2_KEY_PAIR_LOCATION:-}" ]; then
  echo "Error: EC2_KEY_PAIR_LOCATION is not set."
  echo "Create an EC2 Key Pair in us-west-2 under the name sar-agents"
  echo "Please export EC2_KEY_PAIR_LOCATION=<path-to-key-pair.pem>"
  exit 1
fi

echo "Using EC2 instance: $EC2_INSTANCE_IP"
echo "Using key pair: $EC2_KEY_PAIR_LOCATION"

REMOTE_USER="ec2-user"
SSH_TARGET="$REMOTE_USER@$EC2_INSTANCE_IP"

echo "Attempting to connect to $SSH_TARGET using key $EC2_KEY_PAIR_LOCATION"


DOCKER_SETUP_SCRIPT='
echo "✅ SSH connection successful to $(hostname)"
set -e
if command -v docker >/dev/null 2>&1; then
  echo "Docker already installed:"
  sudo usermod -aG docker ec2-user
  docker --version
else
  echo "Installing Docker..."
  sudo dnf update -y
  sudo dnf install -y docker
  sudo systemctl enable docker
  sudo systemctl start docker
  sudo usermod -aG docker ec2-user
fi

if docker compose version >/dev/null 2>&1; then
  echo "Docker Compose already installed:"
  docker compose version
else
  echo "Installing Docker Compose v2..."
  sudo mkdir -p /usr/local/lib/docker/cli-plugins
  sudo curl -SL \
    https://github.com/docker/compose/releases/download/v2.29.2/docker-compose-$(uname -s | tr "[:upper:]" "[:lower:]")-$(uname -m) \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
  sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

  echo "Verifying Docker Compose..."
  docker compose version || { echo "Docker Compose install failed"; exit 1; }
fi
'

ssh -i "$EC2_KEY_PAIR_LOCATION" \
    -o StrictHostKeyChecking=no \
    "$SSH_TARGET" \
    "$DOCKER_SETUP_SCRIPT"

# Now that docker is setup, we need to copy all the relevant files to the ec2 instance
# copy everything from the directory except for aws and datasets to save time

rsync -avz \
  -e "ssh -i $EC2_KEY_PAIR_LOCATION" \
  --exclude "datasets/" \
  --exclude "venv/" \
  --exclude ".*/" \
  ./ \
  ec2-user@$EC2_INSTANCE_IP:~/app/