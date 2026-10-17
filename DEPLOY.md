# Deploying TRACEBACK for free (Render + FalkorDB Cloud)

One Render web service runs the API **and** serves the web console. The graph lives in a free FalkorDB Cloud database.

> Free-tier limits change. Check the Render and FalkorDB Cloud pricing pages before relying on any number here.

## 1. Create the database (FalkorDB Cloud, free)
1. Sign up at <https://app.falkordb.cloud> and create a **Free** instance (no credit card).
2. Copy the connection details: **host**, **port** and **password**.

Things to know about the free tier: 100 MB of memory, no persistence or backups, no TLS, and an instance that is idle for a day is stopped. The API re-seeds the demo companies whenever it starts, so the console still works after a restart. Analysed repositories are temporary.

## 2. Deploy the app (Render)
1. Push this repository to GitHub.
2. In Render: **New → Blueprint**, pick the repository. Render reads `render.yaml`.
3. Fill in the three values it asks for: `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_PASSWORD`.
4. Click **Apply**. The first build takes several minutes (it builds the web console and installs the API).
5. Open the `https://<name>.onrender.com` URL. The first visit after a quiet period shows a loading screen while the free service wakes up.

If you prefer clicking through manually: **New → Web Service → Docker**, same repo, plan **Free**, health check path `/api/health`, then add the environment variables listed below.

## Environment variables
| Variable | Purpose |
|---|---|
| `FALKORDB_HOST` / `FALKORDB_PORT` / `FALKORDB_PASSWORD` | Your FalkorDB Cloud instance |
| `FALKORDB_SSL` | `0` for the free tier (no TLS); `1` if your database uses TLS |
| `TBK_ADMIN_TOKEN` | Secret for `POST /api/admin/reseed` (send it as the `X-Admin-Token` header). Without it the endpoint is disabled on public hosts |
| `TBK_MAX_WORKSPACES`, `TBK_INGESTS_PER_HOUR`, `TBK_MAX_FILES` | Abuse limits for analysed repositories |
| `ANTHROPIC_API_KEY` (optional) | Server-side default LLM key. Leave it unset and visitors use the offline planner or their own key; if you set it, visitors spend your credits |

## Check it works
Open `https://<name>.onrender.com/api/health`. You should see `"ok": true` and the tenants `helix` and `orbit`. Then open the site, run the crew on the built-in company and analyse a public GitHub repository.

## Troubleshooting
- **Health check fails / site never loads:** the database values are wrong or the instance was stopped. Open FalkorDB Cloud, start it, then redeploy.
- **Graph features say the database is unreachable:** check `FALKORDB_SSL` matches your instance.
- **First load is slow:** the free web service sleeps when idle and takes a while to wake.
- **Analysed repos disappeared:** expected on the free tier after a restart.

## Other hosts
The same `Dockerfile` runs anywhere that runs containers (Koyeb, Cloud Run, a VPS with `docker compose`). Set the same environment variables; the app listens on `$PORT`.
