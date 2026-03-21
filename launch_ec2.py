#!/usr/bin/env python3
"""
Launch an EC2 t3.small instance with Docker + PostgreSQL for ApexBT.

Usage:
    cd /Users/yash/x/tweetbot
    source .venv/bin/activate
    python launch_ec2.py
"""

import boto3
import time
import sys

SESSION = boto3.Session()
EC2 = SESSION.client("ec2", region_name="us-east-1")

SG_ID = "sg-0f1e63cb2dad42b16"
KEY_NAME = "yash-ed25519"
AMI_ID = "ami-0e86e20dae9224db8"  # Ubuntu 24.04 LTS us-east-1
INSTANCE_TYPE = "t3.small"

USER_DATA = r"""#!/bin/bash
set -ex
exec > /var/log/user-data.log 2>&1

echo "=== Starting setup ==="

# Update system
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# Install Docker
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Enable Docker
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

# Create data directory for Postgres
mkdir -p /data/postgres

# Create docker-compose file
cat > /home/ubuntu/docker-compose.yml << 'COMPOSEEOF'
services:
  postgres:
    image: postgres:16
    container_name: apexbt-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: apexbt
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: apexbt_secure_2024
    ports:
      - "5432:5432"
    volumes:
      - /data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
COMPOSEEOF

chown ubuntu:ubuntu /home/ubuntu/docker-compose.yml

# Start PostgreSQL
cd /home/ubuntu
docker compose up -d

echo "=== SETUP COMPLETE ==="
"""


def main():
    print("Launching EC2 instance for ApexBT...")
    print(f"  Type:     {INSTANCE_TYPE}")
    print(f"  AMI:      {AMI_ID}")
    print(f"  Key:      {KEY_NAME}")
    print(f"  SG:       {SG_ID}")
    print()

    response = EC2.run_instances(
        ImageId=AMI_ID,
        InstanceType=INSTANCE_TYPE,
        KeyName=KEY_NAME,
        MinCount=1,
        MaxCount=1,
        SecurityGroupIds=[SG_ID],
        UserData=USER_DATA,
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": 20,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True,
                },
            }
        ],
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": "apexbt"},
                    {"Key": "Project", "Value": "apexbt"},
                ],
            }
        ],
    )

    instance_id = response["Instances"][0]["InstanceId"]
    print(f"Instance launched: {instance_id}")
    print("Waiting for running state...")

    waiter = EC2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])

    desc = EC2.describe_instances(InstanceIds=[instance_id])
    inst = desc["Reservations"][0]["Instances"][0]
    public_ip = inst.get("PublicIpAddress", "N/A")

    print()
    print("=" * 50)
    print(f"  Instance ID:  {instance_id}")
    print(f"  Public IP:    {public_ip}")
    print(f"  Private IP:   {inst.get('PrivateIpAddress', 'N/A')}")
    print("=" * 50)
    print()
    print("Docker + PostgreSQL are installing via user-data.")
    print("This takes about 2-3 minutes after the instance starts.")
    print()
    print("To check progress:")
    print(f"  ssh ubuntu@{public_ip} tail -f /var/log/user-data.log")
    print()
    print("To verify Postgres is running:")
    print(f"  ssh ubuntu@{public_ip} docker ps")
    print()
    print("Database connection details:")
    print(f"  Host:     {public_ip}")
    print(f"  Port:     5432")
    print(f"  DB:       apexbt")
    print(f"  User:     postgres")
    print(f"  Password: apexbt_secure_2024")
    print()

    # Wait for SSH to be ready
    print("Waiting for SSH to become available...", end="", flush=True)
    for i in range(30):
        time.sleep(5)
        print(".", end="", flush=True)
        try:
            import subprocess

            result = subprocess.run(
                [
                    "ssh",
                    "-o", "ConnectTimeout=3",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "BatchMode=yes",
                    f"ubuntu@{public_ip}",
                    "echo ok",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                print(" connected!")
                print()
                print("Waiting for Docker setup to finish (watching user-data log)...")
                print()
                subprocess.run(
                    [
                        "ssh",
                        "-o", "StrictHostKeyChecking=no",
                        f"ubuntu@{public_ip}",
                        "while [ ! -f /var/log/user-data.log ] || ! grep -q 'SETUP COMPLETE' /var/log/user-data.log 2>/dev/null; do sleep 5; echo '  still installing...'; done; echo; echo '=== Setup finished! ==='; echo; docker ps",
                    ],
                    timeout=300,
                )
                return
        except Exception:
            pass

    print()
    print(f"SSH not ready yet. Try manually: ssh ubuntu@{public_ip}")


if __name__ == "__main__":
    main()
