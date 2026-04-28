# Scene Studio

Character-consistent scene generation and video production, end-to-end, in your browser.

Give it a creative brief and a reference image, paste a script, and Scene Studio will generate on-model scene images (Gemini 2.5 Flash Image) and turn the approved ones into short videos via your choice of **Kling Direct, Google Veo, Wan 2.1, Seedance, or Kling on Replicate**.

## Features

- **4-step guided workflow** — creative brief → script → images → videos
- **Character consistency** via Gemini multi-turn image generation anchored to a reference image + extracted style prefix
- **Script parsing** — handles `SCENE X:`, `INT./EXT.`, numbered, markdown `#`, and bracket-notation scripts
- **Auto-generated prompts** — image and video prompts derived from your scene descriptions
- **Per-scene review** — approve / reject / regenerate images and videos one at a time
- **Bulk ZIP export** of approved images and videos
- **Local project storage** — resume work anytime; compact per-project folders with image/video sidecars
- **Bring Your Own Keys** — first-time visitors paste their own API keys; nothing is stored server-side

## Quick start (local)

```bash
git clone <your-fork-url> scene-studio
cd scene-studio

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and paste in your API keys

streamlit run app.py
```

The app will open at http://localhost:8501.

## Deploy publicly — Bring Your Own Keys (BYOK)

The app is designed so you can host a public demo **without leaking your API keys or paying for strangers' usage**. First-time visitors see a welcome screen that asks them to paste their own Gemini and fal.ai keys. Those keys live in the visitor's browser session only — never stored server-side, never logged.

1. Push this repo to GitHub (private is fine; public also works since there are no secrets in it).
2. Go to https://share.streamlit.io → **New app**.
3. Point it at your repo, branch `main`, main file `app.py`.
4. **Leave the Secrets section empty.** Visitors will provide their own keys.
5. Deploy. First boot takes ~2 minutes while dependencies install.
6. Share the `.streamlit.app` URL with anyone.

When you want to use it yourself without pasting every time, add a `.streamlit/secrets.toml` locally or set `GEMINI_API_KEY` / `KLING_ACCESS_KEY` in your shell — the welcome screen auto-skips if a Gemini key is already set.

> **Note on persistence:** Streamlit Community Cloud has ephemeral disk. Saved projects live for the lifetime of the container. For durable storage, run locally or host on a platform with a persistent volume.

### If you'd rather host with your own keys (not recommended for public URL)

Under **Advanced → Secrets**, paste:
```toml
GEMINI_API_KEY = "..."
KLING_ACCESS_KEY = "..."
```
Every visitor will then use **your** API quota. Only do this for personal or team deployments behind authentication.

## Getting the API keys

| Service | Where to get it | Models it unlocks |
|---|---|---|
| **Gemini** (required) | https://aistudio.google.com/apikey | All image generation + Veo videos |
| **Kling Open Platform** (optional) | https://app.klingai.com/global → API | Kling 2.6 Pro / 2 Master / 1.6 Pro |
| **Replicate** (optional) | https://replicate.com/account/api-tokens | Wan 2.1 I2V, Seedance 1 Pro, Kling 2.1 Master |

> Tip: Veo runs entirely on the Gemini key. The simplest path for a free demo is Gemini-only and select Veo as the video backend.

## Admin keys (free trial mode)

If you set `ADMIN_*` keys in Streamlit Cloud Secrets, the welcome screen shows a one-click **"Use admin keys"** button. Anyone who clicks it uses your quota — useful for sharing a friction-free demo, dangerous if a malicious visitor finds the link.

```toml
ADMIN_GEMINI_API_KEY     = "AIza..."
ADMIN_KLING_ACCESS_KEY   = "..."   # optional
ADMIN_KLING_SECRET_KEY   = "..."   # optional
ADMIN_REPLICATE_API_TOKEN = "r8_..."  # optional
```

**Kill switch**: delete `ADMIN_GEMINI_API_KEY` from Streamlit Cloud Secrets. The button disappears on the next page load — no redeploy needed.

## Project structure

```
scene_studio/
├── app.py                 # Streamlit entry point, sidebar + step routing
├── config.py              # API key / data dir resolution (st.secrets → env → .env)
├── core/
│   ├── models.py          # Pydantic models for ProjectState, Scene, etc.
│   └── constants.py       # Model names, retry limits, style presets
├── services/
│   ├── gemini_client.py   # Vision + multi-turn image generation
│   ├── kling_client.py    # fal.ai video submission + polling
│   ├── style_analyzer.py  # Creative brief → CharacterProfile
│   └── script_parser.py   # Script → scenes + auto prompts
├── engine/
│   ├── image_pipeline.py  # Sequential image generation w/ history
│   └── video_pipeline.py  # Parallel video submission + polling
├── ui/
│   ├── pages/             # One file per step
│   └── components/        # Reusable scene cards, progress, download
└── utils/
    ├── project_store.py   # JSON-on-disk persistence
    ├── image_utils.py     # Resize / MIME detection
    ├── retry.py           # Tenacity decorators
    └── file_utils.py      # Zip builder
```

## Roadmap

- [ ] Per-scene style overrides (flashback in sepia without rewriting the whole profile)
- [ ] Undo history for regenerated images
- [ ] Full-project export ZIP (images + videos + script + profile)
- [ ] Stronger character consistency — pass the reference image on every call, not just the first

## License

MIT — see [LICENSE](LICENSE).
