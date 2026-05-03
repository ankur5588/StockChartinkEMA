# ChartinkTrade — VPS Deployment (one command)

This folder is the **production deployment helper** for the ChartinkTrade app.
The script provisions a fresh Ubuntu 22.04 VPS into a fully configured
SEBI-compliant algo-trading server in ~5 minutes.

## Before you run it

1. **Rent a VPS with a RESERVED STATIC IP**
   - Recommended: [DigitalOcean Bangalore (BLR1)](https://www.digitalocean.com/products/droplets) — ~₹400/mo droplet + ₹0 Reserved IP
   - Minimum spec: **Ubuntu 22.04**, 1 vCPU, 2 GB RAM, 25 GB SSD
   - In the Networking tab, create a **Reserved IP** and assign it to your droplet

2. **Point your domain's DNS `A` record at the Reserved IP**
   - e.g. `chartinktrade.com  A  203.0.113.45`
   - Wait ~5 min for propagation (check with `dig chartinktrade.com`)

3. **SSH in as root** and clone this repo:
   ```bash
   ssh root@203.0.113.45
   apt update && apt install -y git
   git clone https://github.com/YOUR_USER/chartink-trade.git /opt/chartink-trade
   ```

## Run the deploy script

```bash
cd /opt/chartink-trade
chmod +x deploy.sh
sudo ./deploy.sh chartinktrade.com admin@chartinktrade.com
```

That's it. In ~5 minutes you'll have:

- ✅ Python 3.11 + FastAPI backend running under systemd on port 8001
- ✅ React frontend built and served by Nginx
- ✅ HTTPS enabled with a Let's Encrypt certificate (auto-renews)
- ✅ MongoDB 7 with authentication enabled (passwords stored in `/root/.chartink_mongo_*_pwd`)
- ✅ Encrypted broker credential vault (Fernet key in `/root/.chartink_fernet_key`)
- ✅ UFW firewall locked to 22 / 80 / 443
- ✅ Compliance card will show **STATIC IP — green** after first login

## After the script finishes

The script prints:
- Your outbound static IP (same as the Reserved IP)
- Paths to all generated secrets — **back these up off-server**
- Exact URLs to check health

**Critical next step**: whitelist the static IP with your brokers:

| Broker | Where |
|---|---|
| Dhan | web.dhan.co → My Profile → Access DhanHQ APIs → Whitelisted IPs |
| Kotak Neo | Neo app → Profile → Trade API → API Dashboard → edit app → IP whitelist |
| Alice Blue | ant.aliceblueonline.com → Apps → edit app → IP whitelist |

## Re-running the script

Fully idempotent — re-run it any time to:
- Pull latest code (`git pull` inside)
- Rebuild the frontend
- Restart the backend service
- Renew config

Secrets (Fernet key, Mongo passwords) are generated once and reused, so
re-runs never invalidate existing saved broker credentials.

## Common operations

```bash
# Restart backend after code changes
git -C /opt/chartink-trade pull
sudo systemctl restart chartink-backend

# Tail backend logs
journalctl -u chartink-backend -f
tail -f /var/log/chartink-backend.err.log

# Rebuild frontend only
sudo -u chartink bash -c 'cd /opt/chartink-trade/frontend && yarn build'

# Check outbound IP matches Reserved IP
curl -s https://yourdomain.com/api/deployment/info | jq

# Force SSL cert renewal (usually auto-handled)
sudo certbot renew --force-renewal
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Backend won't start | `journalctl -u chartink-backend -n 100` — most common is MongoDB not ready; `systemctl status mongod` |
| HTTPS cert fails | Ensure DNS A record points to the Reserved IP before running the script; re-run `sudo certbot --nginx -d yourdomain.com` |
| Dhan returns DH-905 | Reserved IP still not whitelisted on web.dhan.co — also check there's no stale old IP blocking |
| FERNET_KEY lost | Stored in `/root/.chartink_fernet_key`. If wiped, saved broker creds in Mongo become unrecoverable — users must re-save them from the dashboard |
| Want to start over cleanly | `rm /root/.chartink_*` + drop the Mongo DB + re-run script (WARNING: all users lose their saved broker creds) |

## What the script does NOT do

- Automated Dhan token refresh (their tokens expire every 24h unless you register as a partner — manual refresh from dashboard takes 30 sec)
- Daily cron for EMA10 stoploss run (can be added as a systemd timer; ping the author to set up)
- Multi-worker Uvicorn (kept at `--workers 1` because broker sessions are in-memory; moving to Redis-backed sessions is P1 backlog)
- Off-site backups of MongoDB (set up a daily `mongodump` + S3 sync yourself — highly recommended before going live)
