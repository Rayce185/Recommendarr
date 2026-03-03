# Recommendarr

A self-hosted media recommendation engine for Plex. Learns from viewing behavior across all server users to generate personalized, explainable recommendations.

## Features

- **5 Recommendation Modes**: Watch Tonight, Worth Grabbing, Rediscover, Mood Match, Group Night
- **AI-Powered Explanations**: Optional LLM generates natural language "why we picked this" for each recommendation
- **Smart Mood Matching**: Natural language mood input ("just got dumped, distract me, no romcoms") parsed into genre/keyword weights — with LLM enhancement when configured
- **Multi-Source Trending**: Global TMDB, by country, by streaming provider, new releases, anime
- **Collection Tracking**: Detects partially watched franchises (John Wick, MCU, etc.) with completion progress and one-click requests for missing parts
- **Plex OAuth Authentication**: Secure login via Plex account with server access verification
- **Taste Profiles**: Auto-generated from watch history with manual genre/keyword tuning
- **Feedback Loop**: Thumbs up/down/dismiss — adjusts future recommendations
- **Plex Watchlist Integration**: Add/remove directly from recommendation cards
- **Seerr Request Integration**: Request media not yet in your library
- **Admin User Switcher**: Preview any user's recommendations
- **Editable Settings**: Runtime configuration via UI — no restart needed
- **Mobile Responsive**: Works on phones, tablets, and desktops

## Stack

- **Backend**: Python / FastAPI
- **Frontend**: React (Vite)
- **Services**: Plex, Tautulli, Radarr, Sonarr, Seerr, TMDB
- **Optional AI**: Ollama, OpenAI-compatible, OpenAI, or Anthropic for enhanced features

## Quick Start

```bash
# Clone and configure
git clone https://github.com/Rayce185/Recommendarr.git
cd Recommendarr
cp .env.example .env
# Edit .env with your API keys (see .env.example for docs)

# Run
docker compose up -d
```

- **Frontend**: http://localhost:30801
- **Backend API**: http://localhost:30800/api/docs

## Requirements

- Docker + Docker Compose
- Plex Media Server (with admin token)
- Tautulli (for watch history)
- At least one of: Radarr, Sonarr (for library data)
- Seerr/Overseerr (for TMDB discovery + request proxy)
- TMDB API key (free at themoviedb.org)

## Optional: AI Integration

Recommendarr works without any LLM — all features have deterministic fallbacks. To enable AI-enhanced features:

1. Go to **Settings → AI Integration** in the web UI
2. Select a provider (Ollama, OpenAI-compatible, OpenAI, or Anthropic)
3. Configure endpoint + model
4. Enable features: **AI Mood** (natural language parsing) and/or **AI Explanations** (LLM-generated recommendation reasons)

Tested with **Ollama + gemma3:4b** (runs on any modern GPU with 4GB+ VRAM).

## API

46+ REST endpoints. Interactive docs at `/api/docs` when running.

## License

MIT
