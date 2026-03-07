"""Bootstrap script — creates tables, syncs TMDB, embeds, ingests history.

Run once to populate the PoC. After this, the API serves real recommendations.
Usage: python bootstrap.py [step]
Steps: tables, sync, embed, history, all
"""

import asyncio
import os
import sys
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


async def create_tables():
    """Step 1: Create all database tables."""
    print("\n═══ STEP 1: CREATE TABLES ═══")
    from app.database import engine, Base
    import app.models  # noqa — register all models with Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Verify
    async with engine.begin() as conn:
        result = await conn.execute(
            __import__("sqlalchemy").text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            )
        )
        tables = [r[0] for r in result.fetchall()]

    print(f"  Created {len(tables)} tables:")
    for t in tables:
        print(f"    ✅ {t}")

    await engine.dispose()
    return len(tables)


async def sync_tmdb():
    """Step 2: Sync all Plex libraries with TMDB metadata."""
    print("\n═══ STEP 2: TMDB SYNC ═══")
    from app.database import async_session, engine
    from app.clients.plex import PlexClient
    from app.clients.tmdb import TmdbClient
    from app.services.tmdb_sync import TmdbSyncService

    plex = PlexClient(
        os.environ["PLEX_URL"],
        os.environ["PLEX_TOKEN"],
        os.environ.get("PLEX_MACHINE_ID", ""),
    )
    tmdb = TmdbClient(os.environ["TMDB_API_KEY"])

    libs = await plex.get_libraries()
    total_synced = 0

    for lib in libs:
        print(f"\n  Library [{lib.id}] {lib.name} ({lib.type}, {lib.item_count} items)")
        t0 = time.time()

        async with async_session() as db:
            sync = TmdbSyncService(tmdb, plex, db)

            async def progress(current, total, title):
                if current % 50 == 0 or current == total:
                    elapsed = time.time() - t0
                    rate = current / elapsed if elapsed > 0 else 0
                    eta = (total - current) / rate if rate > 0 else 0
                    print(f"    [{current}/{total}] {rate:.1f}/s ETA {eta:.0f}s — {title}")

            result = await sync.sync_library(lib.id, progress_callback=progress)

        elapsed = time.time() - t0
        print(f"    Done in {elapsed:.1f}s — synced={result['synced']} skipped={result['skipped']} failed={result['failed']}")
        total_synced += result["synced"]

    await engine.dispose()
    print(f"\n  Total synced: {total_synced}")
    return total_synced


async def embed_library():
    """Step 3: Generate embeddings for all cached TMDB items."""
    print("\n═══ STEP 3: EMBED LIBRARY ═══")
    from app.database import async_session, engine
    from app.services.embedding import EmbeddingService

    embed = EmbeddingService(
        ollama_url=os.environ.get("LLM_BASE_URL", "http://192.168.0.111:20434"),
        chromadb_url=os.environ.get("CHROMADB_URL", "http://192.168.0.111:20002"),
        collection_name="recommendarr",
        model=os.environ.get("EMBEDDING_MODEL", "nomic-embed-text"),
    )

    for media_type in ("movie", "show"):
        print(f"\n  Embedding {media_type}s...")
        t0 = time.time()

        async with async_session() as db:
            async def progress(current, total, title):
                if current % 50 == 0 or current == total:
                    elapsed = time.time() - t0
                    rate = current / elapsed if elapsed > 0 else 0
                    eta = (total - current) / rate if rate > 0 else 0
                    print(f"    [{current}/{total}] {rate:.1f}/s ETA {eta:.0f}s — {title}")

            result = await embed.embed_library(db, media_type=media_type, batch_size=20, progress_callback=progress)

        elapsed = time.time() - t0
        print(f"    Done in {elapsed:.1f}s — embedded={result['embedded']} skipped={result['skipped']} failed={result['failed']}")

    count = await embed.get_collection_count()
    print(f"\n  ChromaDB collection total: {count} vectors")

    await engine.dispose()
    return count


async def ingest_history():
    """Step 4: Pull watch history from Tautulli into the database."""
    print("\n═══ STEP 4: INGEST WATCH HISTORY ═══")
    from app.database import async_session, engine
    from app.clients.tautulli import TautulliClient
    from app.clients.plex import PlexClient
    from app.models import User, WatchHistory, UserLibraryAccess
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    plex = PlexClient(
        os.environ["PLEX_URL"],
        os.environ["PLEX_TOKEN"],
        os.environ.get("PLEX_MACHINE_ID", ""),
    )
    tautulli = TautulliClient(
        os.environ["TAUTULLI_URL"],
        os.environ["TAUTULLI_API_KEY"],
    )

    # Step 4a: Sync Plex users into the database
    print("  Syncing Plex users...")
    plex_users = await plex.get_users()
    libs = await plex.get_libraries()

    async with async_session() as db:
        user_count = 0
        for pu in plex_users:
            if not pu.username:  # Skip empty server owner entry
                continue

            # Try to get numeric Plex user ID from Tautulli
            plex_id_int = int(pu.id) if pu.id.isdigit() else hash(pu.username) % (2**31)

            stmt = pg_insert(User).values(
                plex_user_id=plex_id_int,
                username=pu.username,
                display_name=pu.display_name,
                thumb_url=pu.thumb_url,
                is_admin=pu.is_admin,
            ).on_conflict_do_update(
                index_elements=["plex_user_id"],
                set_={"username": pu.username, "display_name": pu.display_name, "thumb_url": pu.thumb_url},
            )
            await db.execute(stmt)

            # Sync library access
            for lib in libs:
                is_accessible = pu.is_admin or lib.id in pu.accessible_library_ids
                lib_stmt = pg_insert(UserLibraryAccess).values(
                    user_id=plex_id_int,  # We'll fix FK after user insert
                    plex_section_key=int(lib.id),
                    library_title=lib.name,
                    library_type=lib.type,
                    is_accessible=is_accessible,
                ).on_conflict_do_update(
                    index_elements=["user_id", "plex_section_key"],
                    set_={"is_accessible": is_accessible, "library_title": lib.name},
                )
                try:
                    await db.execute(lib_stmt)
                except Exception:
                    pass  # FK might not resolve yet

            user_count += 1

        await db.commit()
        print(f"  Synced {user_count} users")

    # Step 4b: Pull watch history and resolve TMDB IDs
    print("  Pulling watch history from Tautulli...")
    all_history = await tautulli.get_history(limit=10000)
    print(f"  Got {len(all_history)} history entries")

    # Resolve TMDB IDs in batches
    print("  Resolving TMDB IDs...")
    resolved = 0
    failed = 0
    t0 = time.time()

    async with async_session() as db:
        for i, event in enumerate(all_history):
            if event.tmdb_id:
                tmdb_id = event.tmdb_id
            else:
                tmdb_id = await tautulli.resolve_tmdb_id(event.item_key, event.media_type)

            if not tmdb_id:
                failed += 1
                continue

            # Map Tautulli user_id to our DB user
            # Tautulli user_id is the Plex user ID
            try:
                tautulli_uid = int(event.user_id)
            except (ValueError, TypeError):
                failed += 1
                continue

            result = await db.execute(
                select(User.id).where(User.plex_user_id == tautulli_uid)
            )
            db_user_id = result.scalar_one_or_none()
            if not db_user_id:
                failed += 1
                continue

            # For episodes, map to show TMDB ID
            media_type = "movie" if event.media_type == "movie" else "show"

            stmt = pg_insert(WatchHistory).values(
                user_id=db_user_id,
                tmdb_id=tmdb_id,
                media_type=media_type,
                plex_rating_key=event.item_key,
                started_at=event.started_at,
                duration_seconds=event.duration_seconds,
                total_duration_seconds=event.total_duration_seconds,
                completion_pct=event.completion_pct,
                watch_count=event.watch_count,
            ).on_conflict_do_nothing()  # Skip duplicates
            try:
                await db.execute(stmt)
                resolved += 1
            except Exception:
                failed += 1

            if (i + 1) % 100 == 0:
                await db.commit()
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                print(f"    [{i+1}/{len(all_history)}] {rate:.1f}/s resolved={resolved} failed={failed}")

        await db.commit()

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s — resolved={resolved} failed={failed}")

    await engine.dispose()
    return resolved


async def main():
    step = sys.argv[1] if len(sys.argv) > 1 else "all"

    print("╔══════════════════════════════════════════════════╗")
    print("║  RECOMMENDARR — Bootstrap Pipeline              ║")
    print("╚══════════════════════════════════════════════════╝")

    if step in ("tables", "all"):
        await create_tables()

    if step in ("sync", "all"):
        await sync_tmdb()

    if step in ("embed", "all"):
        await embed_library()

    if step in ("history", "all"):
        await ingest_history()

    print("\n══════════════════════════════════════════════════")
    print("Bootstrap complete. Start the API with:")
    print("  cd /mnt/user/system/claude/recommendarr/src/backend")
    print("  uvicorn app.main:app --host 0.0.0.0 --port 30800")


if __name__ == "__main__":
    asyncio.run(main())
