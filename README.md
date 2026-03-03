# Recommendarr

A self-hosted media recommendation engine for Plex. Learns from viewing behavior across all server users to generate personalized, explainable recommendations.

## Features

- **5 Recommendation Modes**: Watch Tonight, Worth Grabbing, Rediscover, Mood Match, Trending
- **Plex OAuth Authentication**: Secure login via Plex account with server access verification
- **Multi-Source Trending**: Global TMDB, by country, by streaming provider, new releases, anime
- **Taste Profiles**: Auto-generated from watch history with manual genre/keyword tuning
- **Feedback Loop**: Thumbs up/down/dismiss on recommendations — improves future suggestions
- **Plex Watchlist Integration**: Add/remove directly from recommendation cards
- **Seerr Request Integration**: Request media not yet in your library
- **Admin User Switcher**: Preview any user's recommendations
- **Mobile Responsive**: Works on phones, tablets, and desktops

## Stack

- **Backend**: Python / FastAPI
- **Frontend**: React (Vite)
- **Services**: Plex, Tautulli, Radarr, Sonarr, Seerr, TMDB

## Quick Start

```bash
# Clone and configure
git clone https://github.com/Rayce185/Recommendarr.git
cd Recommendarr
cp .env.example .env
# Edit .env with your API keys (see .env.example for docs)

# Run
docker compose -f docker-compose.v2.yml up -d
```

- **Frontend**: http://localhost:30801
- **Backend API**: http://localhost:30800

## Requirements

- Docker + Docker Compose
- Plex Media Server (with admin token)
- Tautulli (for watch history)
- At least one of: Radarr, Sonarr (for library data)
- Seerr/Overseerr (for TMDB discovery + request proxy)
- TMDB API key (free at themoviedb.org)

## Optional Integrations

- **LLM** (Ollama/LiteLLM/OpenAI-compatible): Enhanced explanations, natural language mood matching
- **ChromaDB**: Semantic search for mood matching and cultural pulse features

## API

31+ REST endpoints. See backend health check at `/api/v1/health`.

## License

MIT
