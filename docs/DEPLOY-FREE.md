# Putting WhyChain on a link, for free

Checked against each provider's own documentation on 26 Sep 2026. Free tiers
change; re-check the one you pick on the day you set it up.

## What the app needs, and why that rules most "free" hosts out

The engine is Python with DuckDB, scipy and statsmodels, reading a warehouse of
about 765 MB. A diagnosis holds roughly 0.7 to 1.2 GB of memory. So:

| Option | Verdict | Why |
|---|---|---|
| **Vercel, Netlify** | Not possible | Serverless functions with a bundle limit far below a 765 MB warehouse, and no long-running process |
| **Cloudflare Workers or Pages** | Not possible for the engine | No native DuckDB or scipy, and memory far below 1 GB. Fine for static files, which is not where the work is |
| **Render, free plan** | Not enough | 512 MB and a tenth of a CPU; spins down after 15 minutes idle |
| **Hugging Face Spaces** | No longer free for this | Docker Spaces now need a paid plan to create; only static Spaces are free |
| **Cloudflare quick tunnel from your laptop** | **Free, no account, works today** | Your laptop runs the app; Cloudflare gives it a public link |
| **Google Cloud Run** | **Free within its monthly allowance** | Runs the Docker image, 2 workers on 2 CPUs and 4 GB; needs a card on file |

## Option A, for demo day: your laptop plus a Cloudflare quick tunnel

A public `https://<random-words>.trycloudflare.com` link to the app running on
your laptop. No Cloudflare account, no domain, free. The link changes each time
you start it and only works while the laptop is on and online. Cloudflare says
quick tunnels are for testing, with no uptime guarantee and a cap of 200
concurrent requests, which is plenty for a jury.

1. Install the connector (once):
   ```bash
   brew install cloudflared
   ```
2. Start WhyChain as usual, in one Terminal window:
   ```bash
   ./run.sh
   ```
3. In a second window, open the tunnel:
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```
4. Copy the `https://….trycloudflare.com` address it prints. That is the link.
5. Before sharing it: `make warm-ai`, then **Reset demo** in the seat menu (or
   `make demo-reset`), then open `/uat` on the link and check it is all pass.

**Know this before you share it.** The link opens the demo seat picker, so anyone
who has it can sign and decide as any seat. Share it with the jury only, and
reset afterwards. If the model key is set, their clicks use your model quota.

## Option B, an always-available link: Google Cloud Run

A fixed `https://whychain-….run.app` link that works when your laptop is off.
The free allowance (Google's figures, request-based billing, in `us-central1`) is
2 million requests, 180,000 vCPU-seconds and 360,000 GiB-seconds a month: about
25 hours of busy time at 2 CPUs and 4 GB, billed only while requests are being
served, which a demo and a jury's week of clicking will not approach. Instances
are capped at 3, so a burst of traffic cannot become a bill. A billing account
with a card is required even to stay inside it. Other regions have their own
tiers; check before choosing Mumbai.

1. Install the Google Cloud CLI, sign in, and create a project with billing on:
   ```bash
   brew install --cask google-cloud-sdk
   ```
   ```bash
   gcloud init
   ```
2. From the project folder, build and deploy. The image generates the warehouse
   and runs the benchmark while it builds, so the first build takes several
   minutes:
   ```bash
   gcloud run deploy whychain --source . --region us-central1 --memory 4Gi --cpu 2 --max-instances 3 --set-env-vars WHYCHAIN_WORKERS=2 --port 8000 --allow-unauthenticated
   ```
3. The model key is never in the image (`.dockerignore` excludes `.env`, and a
   test holds that; see BUGS.md B-072). To turn the model on, store the key in
   Secret Manager and attach it:
   ```bash
   gcloud run services update whychain --region us-central1 --set-secrets WHYCHAIN_LLM_API_KEY=whychain-llm-key:latest
   ```
   The key alone is not enough: set the same non-secret settings your `.env`
   has (`WHYCHAIN_LLM_BACKEND`, `WHYCHAIN_LLM_BASE_URL`, `WHYCHAIN_LLM_MODEL`,
   `WHYCHAIN_LLM_FREE_ONLY`) with `--set-env-vars`, copying the values from `.env`.
   Without them the app runs the deterministic path and says so on the receipt.
4. The first visit after a quiet spell starts a container, which is slow; open
   the link a few minutes before you present. Sign-offs made on it vanish when
   the container restarts, which for a demo is a reset for free.

## Deploying on every push (CD)

`.github/workflows/deploy.yml` builds the image on Google's Cloud Build, deploys
it to Cloud Run, then runs the demo smoke test against the new link. It runs on
every push to `main`, and on any branch from the Actions tab (Deploy > Run
workflow). Until it is connected it skips with a notice, so nothing goes red.

To connect it, once:

1. In the Google Cloud console (IAM > Service accounts), create a service account
   `whychain-deploy` with the roles **Cloud Run Admin**, **Cloud Build Editor**,
   **Artifact Registry Writer**, **Service Account User** and **Storage Admin**.
   Create a JSON key for it and download it.
2. In GitHub, the repository's Settings > Secrets and variables > Actions:
   - secret `GCP_SA_KEY`: paste the whole JSON key file;
   - variable `GCP_PROJECT`: the project id;
   - variable `GCP_REGION` (optional): `us-central1` by default, for the free tier.
3. Run it once from the Actions tab on `feat/ui-redesign` to check, then leave it
   to follow `main`. The job summary prints the live link.

The key file is a credential: paste it into GitHub's secret store and delete the
downloaded copy. The model key goes on the service as in Option B step 3, once;
deploys keep it.

## Recommendation

Present from the laptop, with the offline package as the fallback if the venue
network fails. Share a quick-tunnel link with the jury if they want to click
through, and set up Cloud Run only if you want a link that outlives the day.

## Sources

- Cloudflare quick tunnels: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/
- Render free plan: https://render.com/docs/free
- Hugging Face Spaces hardware and plans: https://huggingface.co/docs/hub/spaces-overview
- Cloud Run free tier: https://cloud.google.com/run/pricing
