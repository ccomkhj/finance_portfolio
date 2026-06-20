# Self-host the dashboard on Oracle Cloud (Always Free)

Host the **full, editable** dashboard against your **real, private** data on a
free Oracle Cloud VM that you control. Your holdings never leave your own
server. Access is gated by the app password and served over HTTPS.

This guide targets **Oracle Linux** with a **domain name** (HTTPS via Caddy +
Let's Encrypt). Files referenced live in `deploy/`.

> Reminder: review [DISCLAIMER.md](../DISCLAIMER.md). A password + HTTPS is a
> reasonable personal access gate, not bank-grade security. Use a long, unique
> password and keep the server patched.

## 1. Create the VM

1. In the Oracle Cloud console: **Compute → Instances → Create instance**.
2. Image: **Oracle Linux** (8 or 9). Shape: an **Always Free** eligible shape
   — `VM.Standard.A1.Flex` (Ampere ARM, e.g. 1 OCPU / 6 GB is plenty) or
   `VM.Standard.E2.1.Micro`.
3. Add your SSH public key. Create.
4. Note the **public IP**. Default login user on Oracle Linux is `opc`.

## 2. Open the ports

Two layers must allow 80 and 443:

**VCN security list (cloud firewall):** Networking → VCN → your subnet →
default security list → add **ingress** rules: source `0.0.0.0/0`, TCP,
destination ports **80** and **443**.

**Host firewall (on the VM):**

```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

> Do **not** open 8501 — Streamlit binds to localhost only; Caddy is the only
> thing exposed.

## 3. Point your domain at the VM

Create a DNS **A record** for e.g. `dashboard.example.com` → the VM's public IP.
(AAAA too if you enabled IPv6.) Wait for it to resolve before step 6.

## 4. Install dependencies and the app

```bash
sudo dnf install -y git
# uv (installs to ~/.local/bin)
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/ccomkhj/finance_portfolio.git
cd finance_portfolio
~/.local/bin/uv sync
```

Put your real data in `data/private/` (gitignored). Either `scp` your existing
`config.yaml` + `accounts/*.json` there, or initialise fresh:

```bash
PORTFOLIO_DATA_DIR=data/private ~/.local/bin/uv run portfolio init --force
```

## 5. Run it as a service

```bash
# Secrets / data dir (gitignored)
cp deploy/portfolio.env.example deploy/portfolio.env
# edit deploy/portfolio.env: set a strong PORTFOLIO_PASSWORD

sudo cp deploy/portfolio-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now portfolio-dashboard
systemctl status portfolio-dashboard      # should be active (running)
```

If SELinux is enforcing and the service can't start, check
`sudo ausearch -m avc -ts recent`; the simplest fix for a personal box is to run
the app from the user's home (as above) which avoids most policy issues.

## 6. HTTPS with Caddy

Install Caddy on Oracle Linux:

```bash
sudo dnf install -y 'dnf-command(copr)'
sudo dnf copr enable -y @caddy/caddy
sudo dnf install -y caddy
```

Configure the reverse proxy:

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo sed -i 's/dashboard.example.com/YOUR.DOMAIN.HERE/' /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
```

Caddy fetches a Let's Encrypt certificate automatically. Visit
`https://your.domain` — you'll get the password prompt, then the full
dashboard.

## 7. Updating

```bash
cd ~/finance_portfolio
git pull
~/.local/bin/uv sync
sudo systemctl restart portfolio-dashboard
```

## Notes

- **Back up `data/private/`** — it only exists on this VM. `scp` it down
  periodically or push it to a *private* git remote.
- Always-Free Ampere VMs can rarely be reclaimed if idle; keep a backup.
- To rotate the password: edit `deploy/portfolio.env`, then
  `sudo systemctl restart portfolio-dashboard`.
