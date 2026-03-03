"""Live integration smoke test — runs against actual services.

Usage: python -m tests.test_live_integration
NOT for CI — requires live Plex, Tautulli, TMDB connections.
"""

import asyncio
import os
import sys
import json

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_plex(url: str, token: str, machine_id: str | None):
    """Test Plex client against live server."""
    from app.clients.plex import PlexClient
    client = PlexClient(url, token, machine_id)

    print("\n═══ PLEX ═══")
    ok = await client.test_connection()
    print(f"  Connection: {'✅' if ok else '❌'}")
    if not ok:
        return

    libs = await client.get_libraries()
    print(f"  Libraries: {len(libs)}")
    for lib in libs:
        print(f"    [{lib.id}] {lib.name} ({lib.type}, {lib.item_count} items)")

    users = await client.get_users()
    print(f"  Users: {len(users)}")
    for u in users:
        admin_tag = " [ADMIN]" if u.is_admin else ""
        libs_access = f", libs={u.accessible_library_ids}" if u.accessible_library_ids else ""
        print(f"    {u.username}{admin_tag}{libs_access}")

    # Test GUID extraction on first movie library
    movie_libs = [l for l in libs if l.type == "movie"]
    if movie_libs:
        guids = await client.get_all_library_guids(movie_libs[0].id)
        sample = list(guids.items())[:3]
        print(f"  GUID map sample ({movie_libs[0].name}, {len(guids)} total):")
        for key, tmdb in sample:
            print(f"    ratingKey={key} → tmdb={tmdb}")

    clients = await client.get_clients()
    print(f"  Active clients: {len(clients)}")
    for c in clients:
        print(f"    {c.name} ({c.platform}, {c.state})")


async def test_tautulli(url: str, api_key: str):
    """Test Tautulli client against live server."""
    from app.clients.tautulli import TautulliClient
    client = TautulliClient(url, api_key)

    print("\n═══ TAUTULLI ═══")
    ok = await client.test_connection()
    print(f"  Connection: {'✅' if ok else '❌'}")
    if not ok:
        return

    users = await client.get_users()
    print(f"  Users: {len(users)}")

    # Pull last 5 history entries
    history = await client.get_history(limit=5)
    print(f"  Recent history ({len(history)} entries):")
    for h in history:
        pct = f"{h.completion_pct:.0f}%"
        print(f"    user={h.user_id} key={h.item_key} tmdb={h.tmdb_id} {pct} ({h.media_type})")


async def test_tmdb(api_key: str):
    """Test TMDB client."""
    from app.clients.tmdb import TmdbClient
    client = TmdbClient(api_key)

    print("\n═══ TMDB ═══")
    ok = await client.test_connection()
    print(f"  Connection: {'✅' if ok else '❌'}")
    if not ok:
        return

    # Fetch a known movie (Oppenheimer)
    movie = await client.get_movie(872585)
    print(f"  Test fetch: {movie['title']} ({movie['year']})")
    print(f"    Genres: {list(movie['genres'].values())}")
    print(f"    Cast: {[c['name'] for c in movie['cast_crew']['cast'][:3]]}")
    print(f"    Trailer: https://youtube.com/watch?v={movie['trailer_key']}" if movie['trailer_key'] else "    Trailer: None")
    print(f"    Similar: {len(movie['similar_ids'])} titles")
    print(f"    Keywords: {movie['keywords'][:5]}")

    genres = await client.get_movie_genres()
    print(f"  Movie genres: {len(genres)}")


async def test_database(db_url: str):
    """Test PostgreSQL connection."""
    print("\n═══ DATABASE ═══")
    try:
        import asyncpg
        # Convert SQLAlchemy URL to asyncpg format
        pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(pg_url)
        version = await conn.fetchval("SELECT version()")
        print(f"  Connection: ✅")
        print(f"  Version: {version[:60]}...")
        await conn.close()
    except Exception as e:
        print(f"  Connection: ❌ ({e})")


async def test_ollama(url: str):
    """Test Ollama connection and list models."""
    import httpx
    print("\n═══ OLLAMA ═══")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/api/tags")
            data = resp.json()
            models = data.get("models", [])
            print(f"  Connection: ✅")
            print(f"  Models: {len(models)}")
            for m in models[:10]:
                size_gb = m.get("size", 0) / 1e9
                print(f"    {m['name']} ({size_gb:.1f} GB)")
    except Exception as e:
        print(f"  Connection: ❌ ({e})")


async def test_chromadb(url: str):
    """Test ChromaDB connection."""
    import httpx
    print("\n═══ CHROMADB ═══")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/api/v1/heartbeat")
            print(f"  Connection: ✅")
            try:
                resp2 = await client.get(f"{url}/api/v1/collections")
                collections = resp2.json()
                if isinstance(collections, list):
                    print(f"  Collections: {len(collections)}")
                    for c in collections[:5]:
                        name = c.get('name', '?') if isinstance(c, dict) else str(c)
                        print(f"    {name}")
                else:
                    print(f"  Collections: (non-list response)")
            except Exception as e2:
                print(f"  Collections: ⚠️ list error ({e2})")
    except Exception as e:
        print(f"  Connection: ❌ ({e})")


async def main():
    print("╔══════════════════════════════════════════════════╗")
    print("║  RECOMMENDARR — Live Integration Smoke Test     ║")
    print("╚══════════════════════════════════════════════════╝")

    # Read from env or use defaults
    plex_url = os.environ.get("PLEX_URL", "http://192.168.0.111:32400")
    plex_token = os.environ.get("PLEX_TOKEN", "")
    plex_machine_id = os.environ.get("PLEX_MACHINE_ID", "")
    tautulli_url = os.environ.get("TAUTULLI_URL", "http://192.168.0.111:30181")
    tautulli_key = os.environ.get("TAUTULLI_API_KEY", "")
    tmdb_key = os.environ.get("TMDB_API_KEY", "")
    db_url = os.environ.get("DATABASE_URL", "")
    ollama_url = os.environ.get("LLM_BASE_URL", "http://192.168.0.111:11434")
    chroma_url = os.environ.get("CHROMADB_URL", "http://192.168.0.111:20002")

    await test_database(db_url)
    await test_chromadb(chroma_url)
    await test_ollama(ollama_url)

    if plex_token:
        await test_plex(plex_url, plex_token, plex_machine_id)
    else:
        print("\n═══ PLEX ═══\n  ⏭ Skipped (PLEX_TOKEN not set)")

    if tautulli_key:
        await test_tautulli(tautulli_url, tautulli_key)
    else:
        print("\n═══ TAUTULLI ═══\n  ⏭ Skipped (TAUTULLI_API_KEY not set)")

    if tmdb_key:
        await test_tmdb(tmdb_key)
    else:
        print("\n═══ TMDB ═══\n  ⏭ Skipped (TMDB_API_KEY not set)")

    print("\n══════════════════════════════════════════════════")
    print("Done. Review results above for any ❌ failures.")


if __name__ == "__main__":
    asyncio.run(main())
