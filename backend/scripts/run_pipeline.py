"""Data pipeline runner - TMDB sync, embed, history ingest.

Usage: cd src/backend && python scripts/run_pipeline.py [step]
Steps: sync | embed | history | users | all
"""
import asyncio, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.config import settings
from app.clients.plex import PlexClient
from app.clients.tautulli import TautulliClient
from app.clients.tmdb import TmdbClient
from app.services.tmdb_sync import TmdbSyncService
from app.services.embedding import EmbeddingService
from app.models import User, UserLibraryAccess, WatchHistory

def get_engine():
    return create_async_engine(settings.database_url, echo=False)

def get_session_factory(engine):
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def sync_users():
    print("\n=== USER SYNC ===")
    plex = PlexClient(settings.plex_url, settings.plex_token, settings.plex_machine_id)
    users = await plex.get_users()
    print(f"  Plex users found: {len(users)}")
    engine = get_engine()
    sf = get_session_factory(engine)
    async with sf() as db:
        for u in users:
            uid = int(u.id) if u.id else 0
            if uid == 0: continue  # skip anonymous account
            stmt = pg_insert(User).values(
                plex_user_id=uid, username=u.username,
                display_name=u.display_name or u.username,
                thumb_url=u.thumb_url, is_admin=u.is_admin,
            ).on_conflict_do_update(
                index_elements=["plex_user_id"],
                set_={"username": u.username, "display_name": u.display_name or u.username,
                       "thumb_url": u.thumb_url, "is_admin": u.is_admin},
            )
            await db.execute(stmt)
            result = await db.execute(select(User.id).where(User.plex_user_id == uid))
            db_uid = result.scalar_one()
            for sk in u.accessible_library_ids:
                ls = pg_insert(UserLibraryAccess).values(
                    user_id=db_uid, plex_section_key=int(sk), is_accessible=True,
                ).on_conflict_do_update(
                    index_elements=["user_id", "plex_section_key"], set_={"is_accessible": True},
                )
                await db.execute(ls)
        await db.commit()
    async with sf() as db:
        result = await db.execute(select(User))
        for usr in result.scalars():
            a = " [ADMIN]" if usr.is_admin else ""
            print(f"    [{usr.id}] {usr.username}{a}")
    await engine.dispose()

async def sync_tmdb():
    print("\n=== TMDB SYNC ===")
    plex = PlexClient(settings.plex_url, settings.plex_token, settings.plex_machine_id)
    tmdb = TmdbClient(settings.tmdb_api_key)
    engine = get_engine()
    sf = get_session_factory(engine)
    libs = await plex.get_libraries()
    movie_libs = [l for l in libs if l.type == "movie"]
    print(f"  Libraries: {[(l.name, l.item_count) for l in movie_libs]}")
    for lib in movie_libs:
        print(f"\n  Syncing [{lib.id}] {lib.name} ({lib.item_count} items)...")
        t0 = time.time()
        lr = [t0]
        async def progress(cur, tot, title):
            now = time.time()
            if now - lr[0] >= 5.0 or cur == tot:
                pct = cur/tot*100 if tot else 0
                el = now - t0
                rate = cur/el if el > 0 else 0
                eta = (tot-cur)/rate if rate > 0 else 0
                print(f"    [{cur}/{tot}] {pct:.0f}% | {rate:.1f}/s | ETA {eta:.0f}s | {title}")
                lr[0] = now
        async with sf() as db:
            svc = TmdbSyncService(tmdb, plex, db)
            r = await svc.sync_library(lib.id, progress_callback=progress, cache_ttl_days=7)
        el = time.time() - t0
        print(f"  Done: synced={r['synced']} skipped={r['skipped']} failed={r['failed']} total={r['total']} in {el:.0f}s")
    await engine.dispose()

async def run_embeddings():
    print("\n=== EMBEDDING PIPELINE ===")
    embed = EmbeddingService(
        ollama_url=settings.llm_base_url, chromadb_url=settings.chromadb_url,
        collection_name="recommendarr", model=settings.embedding_model,
    )
    status = await embed.test_connection()
    print(f"  Ollama: {'OK' if status['ollama'] else 'FAIL'}")
    print(f"  ChromaDB: {'OK' if status['chromadb'] else 'FAIL'}")
    if not all(status.values()):
        print("  ABORTING"); return
    cb = await embed.get_collection_count()
    print(f"  Items before: {cb}")
    engine = get_engine()
    sf = get_session_factory(engine)
    t0 = time.time()
    lr = [t0]
    async def progress(cur, tot, title):
        now = time.time()
        if now - lr[0] >= 10.0 or cur == tot:
            pct = cur/tot*100 if tot else 0
            el = now-t0; rate = cur/el if el > 0 else 0; eta = (tot-cur)/rate if rate > 0 else 0
            print(f"    [{cur}/{tot}] {pct:.0f}% | {rate:.1f}/s | ETA {eta:.0f}s | {title}")
            lr[0] = now
    async with sf() as db:
        r = await embed.embed_library(db, media_type="movie", batch_size=20, progress_callback=progress)
    el = time.time() - t0
    ca = await embed.get_collection_count()
    print(f"  Done: embedded={r['embedded']} skipped={r['skipped']} failed={r['failed']} in {el:.0f}s")
    print(f"  Items after: {ca}")
    await engine.dispose()

async def ingest_history():
    print("\n=== HISTORY INGEST ===")
    tau = TautulliClient(settings.tautulli_url, settings.tautulli_api_key)
    ok = await tau.test_connection()
    print(f"  Tautulli: {'OK' if ok else 'FAIL'}")
    if not ok: return
    engine = get_engine()
    sf = get_session_factory(engine)
    async with sf() as db:
        result = await db.execute(select(User))
        umap = {u.plex_user_id: u.id for u in result.scalars()}
    print(f"  User mapping: {len(umap)} users")
    print("  Pulling history...")
    t0 = time.time()
    history = await tau.get_history(limit=50000)
    print(f"  Records: {len(history)} ({time.time()-t0:.1f}s)")
    ins = 0; skip = 0; cache = {}
    async with sf() as db:
        for i, ev in enumerate(history):
            uid = umap.get(ev.user_id)
            if not uid: skip += 1; continue
            tid = ev.tmdb_id
            if not tid:
                ck = ev.item_key
                if ck in cache: tid = cache[ck]
                else:
                    tid = await tau.resolve_tmdb_id(ck, ev.media_type)
                    cache[ck] = tid
            if not tid: skip += 1; continue
            stmt = pg_insert(WatchHistory).values(
                user_id=uid, tmdb_id=tid, plex_rating_key=ev.item_key,
                media_type=ev.media_type, started_at=ev.started_at,
                duration_seconds=ev.duration_seconds,
                total_duration_seconds=ev.total_duration_seconds,
                completion_pct=ev.completion_pct, watch_count=ev.watch_count,
            ).on_conflict_do_update(
                index_elements=["user_id", "tmdb_id", "started_at"],
                set_={"completion_pct": ev.completion_pct, "duration_seconds": ev.duration_seconds,
                       "watch_count": ev.watch_count},
            )
            try: await db.execute(stmt); ins += 1
            except: skip += 1
            if (i+1) % 200 == 0:
                await db.commit()
                print(f"    [{i+1}/{len(history)}] {(i+1)/len(history)*100:.0f}% | ins={ins} skip={skip} | cache={len(cache)}")
        await db.commit()
    print(f"  Done: inserted={ins} skipped={skip} tmdb_cache={len(cache)}")
    await engine.dispose()

async def main():
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    print("=" * 50)
    print("  RECOMMENDARR Data Pipeline")
    print("=" * 50)
    print(f"  Step: {step}")
    if step in ("users", "all"): await sync_users()
    if step in ("sync", "all"): await sync_tmdb()
    if step in ("embed", "all"): await run_embeddings()
    if step in ("history", "all"): await ingest_history()
    print("\nPipeline complete.")

if __name__ == "__main__":
    asyncio.run(main())
