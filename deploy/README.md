# KYRO — AWS Deployment Runbook

Single-EC2, Docker Compose production deployment. No Terraform/CDK — the
steps below **are** the infrastructure definition. Follow them once per
environment; re-running the GitHub Actions workflow after that handles
every subsequent deploy.

## 1. One-time AWS setup

### EC2 instance
- Ubuntu 22.04 LTS, `t3.medium` or larger (Postgres + Redis + API + 2 Celery
  processes + ML libs need at least 2 vCPU / 4GB RAM).
- gp3 root volume, ≥50GB.
- Allocate and associate an **Elastic IP** so the address survives restarts.
- Security group: inbound `22/tcp` (SSH — restrict to a known IP if
  possible), `80/tcp` and `443/tcp` (`0.0.0.0/0`). Nothing else public.

### IAM instance profile (attach to the EC2 instance)
- Policy: `AmazonEC2ContainerRegistryReadOnly` (lets the box `docker pull`
  from ECR via its role — no static AWS keys on the instance).

### Bootstrap the instance (SSH in once)
```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git

# Docker Engine + Compose plugin from Docker's official repo
# (Ubuntu's own repo ships an older Compose without `!reset` support,
# which docker-compose.prod.yml relies on — need Compose v2.24+)
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# AWS CLI v2 (for `aws ecr get-login-password`)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && sudo ./aws/install

sudo usermod -aG docker $USER   # log out/in for this to take effect
```

### ECR repositories
```bash
aws ecr create-repository --repository-name kyro-api --image-scanning-configuration scanOnPush=true
aws ecr create-repository --repository-name kyro-frontend --image-scanning-configuration scanOnPush=true
aws ecr create-repository --repository-name kyro-pipeline --image-scanning-configuration scanOnPush=true
```

### GitHub OIDC → IAM role (build-and-push job only)
1. IAM → Identity providers → add `token.actions.githubusercontent.com`
   (audience `sts.amazonaws.com`) if not already present in the account.
2. Create an IAM role trusted for this repo only, e.g. trust policy
   condition: `token.actions.githubusercontent.com:sub` =
   `repo:<org>/<repo>:ref:refs/heads/main`.
3. Attach an inline policy granting `ecr:GetAuthorizationToken`,
   `ecr:BatchCheckLayerAvailability`, `ecr:PutImage`,
   `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`,
   `ecr:CompleteLayerUpload`, `ecr:BatchGetImage` on the three repos above.
4. Note the role ARN — it becomes the `AWS_ROLE_ARN` GitHub secret.

### Deploy SSH key
```bash
ssh-keygen -t ed25519 -f kyro_deploy_key -N ""
# append kyro_deploy_key.pub to ~/.ssh/authorized_keys on the EC2 instance
# the private half (kyro_deploy_key) becomes the EC2_SSH_KEY GitHub secret
```

### Clone the app + create production secrets on the instance
```bash
sudo mkdir -p /opt/kyro && sudo chown $USER /opt/kyro
git clone <this-repo-url> /opt/kyro
cd /opt/kyro
cp .env.example .env
# Edit .env with REAL production values:
#   SECRET_KEY   -> `openssl rand -hex 32`
#   DB_PASSWORD  -> a strong generated password (not the `kyro_pass` default)
#   DATABASE_URL -> update to match DB_USER/DB_PASSWORD/DB_NAME
#   ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID (if TTS is used)
chmod 600 .env
```
`.env` lives only on the instance, is gitignored, and `deploy.sh` never
touches it.

## 2. GitHub repository secrets

| Secret            | Value                                                   |
|--------------------|----------------------------------------------------------|
| `AWS_ROLE_ARN`     | IAM role ARN from the OIDC setup above                  |
| `AWS_REGION`       | e.g. `us-east-1`                                        |
| `ECR_REGISTRY`     | `<account-id>.dkr.ecr.<region>.amazonaws.com`           |
| `EC2_HOST`         | the instance's Elastic IP / public DNS                  |
| `EC2_SSH_USER`     | `ubuntu`                                                |
| `EC2_SSH_KEY`      | private half of the deploy keypair generated above      |

## 3. How a deploy works

Push to `main` (or run the workflow manually) triggers
`.github/workflows/deploy.yml`:
1. **test** — runs `pytest tests/api` against a throwaway Postgres service
   container.
2. **build-and-push** — builds `kyro-api`, `kyro-frontend`, `kyro-pipeline`
   images and pushes them to ECR tagged with the commit SHA and `latest`.
3. **deploy** — SSHes into the EC2 instance and runs `deploy/deploy.sh
   <sha>`, which: pulls the new images, runs `alembic upgrade head`,
   restarts the stack (`api`, `frontend`, `celery_worker`, `celery_beat`,
   `postgres`, `redis`), and fails the job if `/api/v1/health` doesn't come
   back healthy within ~30s.

The `pipeline` image is pulled but **not** auto-started on every deploy —
it's a one-off ETL job, already scheduled via `celery_beat` per the
existing compose setup. Run it manually when needed:
```bash
cd /opt/kyro
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm pipeline
```

## 4. Rollback

- **Preferred**: revert the bad commit on `main` and let the pipeline
  redeploy, or re-run the workflow via `workflow_dispatch` from a prior
  good commit.
- **Manual/fast**: SSH into the instance and pin a known-good tag directly:
  ```bash
  cd /opt/kyro
  IMAGE_TAG=<previous-good-sha> docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api frontend celery_worker celery_beat
  ```

## 5. Enable HTTPS

Let's Encrypt won't issue a certificate for a bare IP, so this needs a
hostname. If you don't own a domain, a free IP-based hostname works fine:
for Elastic IP `1.2.3.4`, `1-2-3-4.sslip.io` automatically resolves back to
`1.2.3.4` — no purchase, no DNS setup.

One-time bootstrap (run once, on the instance, from `/opt/kyro`):
```bash
chmod +x deploy/init-letsencrypt.sh
./deploy/init-letsencrypt.sh 1-2-3-4.sslip.io you@example.com
```
This creates a throwaway self-signed cert so nginx can start, requests the
real certificate from Let's Encrypt via the HTTP-01 webroot challenge, then
reloads nginx with it. The cert lives in `./certbot/conf` on the host
(gitignored, untouched by `deploy.sh`'s `git reset --hard`), so every
future CI deploy keeps serving HTTPS automatically — no changes to the
normal deploy flow needed.

**Renewal** (certs expire after 90 days) — add a daily cron job on the
instance:
```bash
crontab -e
# add this line:
0 3 * * * cd /opt/kyro && docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile certbot run --rm certbot renew --webroot -w /var/www/certbot && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec frontend nginx -s reload
```
`certbot renew` only actually renews within 30 days of expiry, so this is
a safe no-op most days.

Once HTTPS is live, remember to update the `EC2_HOST` GitHub secret's
usage in your head (SSH still uses the raw IP — that's unaffected) and
just bookmark `https://<your-hostname>` for the app itself.

## 6. Explicitly out of scope for now

- Managed RDS/ElastiCache — Postgres and Redis run as containers on the
  same instance.
- Terraform/CDK — these steps are the infra definition.
- Staging environment — production only.
