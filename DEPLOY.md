# Deploy Guide

Three options for putting `api_server.py` on the internet so your phone (or any device) can use the Kroger features without your PC running.

| Option | Cost | Effort | Cold start | Best for |
|---|---|---|---|---|
| **Cloudflare Tunnel** | $0 | 5 min | None | "I'm fine leaving my PC on" |
| **Render free tier** | $0 | 15 min | ~30s | "I want 24/7 but can wait" |
| **Railway hobby** | $5/mo | 15 min | None | "I want it instant" |

After any of these, **these steps are required regardless**:

1. Add the new public URL as a Kroger OAuth redirect URI:
   `https://<your-deployed-url>/api/kroger/callback`
   → done at [developer.kroger.com](https://developer.kroger.com) → your app → Web Redirect URI
2. Set env vars on the host:
   - `KROGER_REDIRECT_URI=https://<your-deployed-url>/api/kroger/callback`
   - `ALLOWED_ORIGIN=https://<your-deployed-url>` (CORS allowlist — without it,
     browsers block cross-origin API calls to the deployed server)
3. Prefer opening the app at `https://<your-deployed-url>/` directly (the server
   serves it with the access token injected). If you instead load the app from
   somewhere else, tell it where the API is:
   - Open browser console (F12)
   - Run: `localStorage.setItem('mp2_api_base', 'https://your-deployed-url')`
   - And set the token: `localStorage.setItem('mp2_api_token', '<contents of .api_token on the server>')`
   - Hard refresh

Note: state-changing endpoints (pantry, publish, cart) now require the
`X-MP-Token` header. The token lives in `.api_token` next to the server and is
injected automatically into pages the server itself serves.

---

## Option A: Cloudflare Tunnel

You keep `start.bat` running on your PC. Cloudflare gives you a public HTTPS URL that tunnels to `localhost:8099`.

```bash
# 1. Install cloudflared (one time)
#    Windows: download from https://github.com/cloudflare/cloudflared/releases
#    or: winget install --id Cloudflare.cloudflared

# 2. Authenticate (one time, opens browser)
cloudflared tunnel login

# 3. Create the tunnel
cloudflared tunnel create meal-planner

# 4. Route a hostname (replace with your Cloudflare-managed domain)
cloudflared tunnel route dns meal-planner meal.example.com

# 5. Run the tunnel — keep this open alongside start.bat
cloudflared tunnel --url http://localhost:8099 run meal-planner
```

Or the simplest "quick tunnel" without DNS setup (URL changes every restart):
```bash
cloudflared tunnel --url http://localhost:8099
```
It'll print a `https://random-words-here.trycloudflare.com` URL — use that as your API base.

**Pros:** Zero cloud config, your PC handles all compute.
**Cons:** PC has to be on for the tunnel + `start.bat` to work.

---

## Option B: Render free tier

```
1. Push this repo to GitHub (already done if you're using the auto-publish action)
2. Go to render.com → New → Web Service → connect your GitHub repo
3. Settings:
   - Runtime: Python 3
   - Build command: pip install -r requirements.txt
   - Start command: python api_server.py --port $PORT
   - Auto-deploy: yes (on push to main)
4. Environment variables:
   - KROGER_CLIENT_ID  =  (your client id)
   - KROGER_CLIENT_SECRET  =  (your client secret)
   - DEFAULT_ZIP  =  45202  (or whatever)
5. Click Deploy. URL will be https://<your-app>.onrender.com
```

**Pros:** $0/month, runs 24/7, auto-deploys on git push.
**Cons:** Spins down after 15 min idle → first request takes ~30 seconds.
**Caveat:** Free tier has ephemeral disk, so `.kroger_user_token.json`, `pantry.json`, and `match_overrides.json` reset on each redeploy. Kroger refresh tokens last 6 months so re-login isn't frequent, but pantry/match-learning data is lost. Upgrade to a paid plan ($7/mo) for persistent disk.

---

## Option C: Railway

Similar to Render but no spin-down on the $5/mo Hobby plan.

```
1. railway.com → new project → deploy from GitHub repo
2. Add same env vars as above
3. Generate a public domain → use that as your API base
```

---

## After deploying

- The local `start.bat` keeps working — `API_BASE` falls back to `localhost:8099` if you haven't set the override.
- To switch back to local: in browser console, `localStorage.removeItem('mp2_api_base')` then refresh.
- The frontend logs `[API] Using base: ...` on every load so you can verify which URL it's hitting.

## Persistent token note

If you go with Render free tier, the `.kroger_*.json` files reset on each deploy. Workarounds:

- Use a paid tier with disk
- Add a small persistent KV store (Upstash Redis free tier) and rewrite the token helpers to read/write there
- Just live with re-login after each code change (tokens last ~6 months on no-deploy days)

For most personal use, the free tier with occasional re-logins is fine.
