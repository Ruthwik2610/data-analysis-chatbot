# Deploy

Production VPS for this project:

- **SSH alias:** `datachat-vps` (defined in `~/.ssh/config` → `root@66.116.235.156`)
- **Remote repo path:** `/opt/datachat/`
- **Backend service:** `datachat-backend.service` (systemd)
- **Frontend service:** `datachat-frontend.service` (systemd)
- **Nginx vhost:** `/etc/nginx/sites-available/datachat`
- **Rsync excludes file:** `/tmp/datachat-rsync-excludes` — excludes `.git`, `.venv`, `.cache`, `cache`, `logs`, `node_modules`, `.next`, `__pycache__`, `*.pyc`, `.env`, `.env.local`, `.env.production`, `mcp.json`, `.DS_Store`, `.streamlit/`, `app.py`

Standard deploy after editing files locally:

```bash
rsync -az --stats --exclude-from=/tmp/datachat-rsync-excludes \
  -e "ssh -F /Users/rajasekharbandreddy/.ssh/config" \
  ./ datachat-vps:/opt/datachat/
ssh datachat-vps systemctl restart datachat-backend.service
ssh datachat-vps systemctl status datachat-backend.service --no-pager
```

For frontend (Next.js) changes also restart `datachat-frontend.service`. `mcp.json` is excluded from rsync so the server's connected MCP bridges (BigQuery, etc.) survive deploys.
