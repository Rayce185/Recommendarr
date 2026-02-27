# Recommendarr

**AI-powered personal media recommendation engine for Plex, Jellyfin, and Emby.**

Recommendarr learns from your actual viewing behavior — completion rates, rewatch patterns, time-of-day habits — to generate explainable, actionable recommendations. Unlike Trakt or Plex Discover, it's fully self-hosted, privacy-first, and library-aware.

## Features

- **Behavior-based profiling** — completion rate > ratings. Abandoned at 20 min = strong signal.
- **17 recommendation modes** — Watch Tonight, Worth Grabbing, Mood Match, Auto-Grab, Group Night, and more
- **Library-aware** — knows what's on your server AND what Radarr/Sonarr can grab
- **Explainable** — every recommendation includes "because you..." reasoning
- **Multi-user** — per-user taste profiles respecting library sharing permissions
- **Plex Connect** — play recommendations on any device from the web UI
- **World Cinema Map** — explore what's trending in 50+ countries
- **Cultural Pulse** — real-world events surface thematically relevant content
- **Plugin system** — extensible architecture for community contributions

## Quick Start

```bash
git clone https://github.com/Rayce185/Recommendarr.git
cd Recommendarr
cp .env.example .env
# Edit .env with your Plex token and TMDB API key
docker compose up -d
```

Open `http://localhost:30800` and log in with your Plex account.

## Requirements

- **Required:** Plex/Jellyfin/Emby server, TMDB API key (free)
- **Recommended:** Tautulli (for detailed watch history)
- **Optional:** Radarr/Sonarr (grab features), Seerr (request proxy), Ollama (local LLM)

## Stack

| Component | Tech |
|-----------|------|
| Backend | Python 3.12, FastAPI |
| Database | PostgreSQL 16 |
| Vectors | ChromaDB + nomic-embed-text |
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Deployment | Docker Compose |

## Architecture

Recommendarr uses a three-tier explanation engine:

- **Tier 1 (default):** Template engine — zero dependencies, works everywhere
- **Tier 2:** Local LLM via Ollama — auto-discovers models, pick from dropdown
- **Tier 3:** Remote LLM API — OpenRouter, Groq, Gemini (free tiers available)

## Documentation

- [Project Specification](docs/RECOMMENDARR-PROJECT.md)
- [API Reference](docs/API.md) *(coming soon)*
- [Plugin Development](docs/PLUGINS.md) *(coming soon)*

## License

[MIT](LICENSE)

## Contributing

Contributions welcome! See the [plugin interfaces](backend/app/clients/base.py) for extension points.
