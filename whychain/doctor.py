"""Check every integration before a demo:  python -m whychain.doctor"""
from __future__ import annotations

import time

import psycopg

from whychain.config import SETTINGS
from whychain.llm import LLM


def line(ok: bool | None, name: str, detail: str) -> None:
    mark = {True: "OK  ", False: "FAIL", None: "--  "}[ok]
    print(f"[{mark}] {name:<22} {detail}")


def main() -> None:
    from whychain.config import utf8_output
    utf8_output()
    print(f"WhyChain doctor · harness preference: {SETTINGS.harness}\n")
    # data: each dataset's files, and its live tables in Postgres
    from whychain.datasets import DATASETS, default_key

    build = {"olist": "python -m datagen.olist", "kaveri": "python -m datagen.generate; python -m datagen.load_postgres"}
    for key, ds in DATASETS.items():
        tag = " (default)" if key == default_key() else ""
        if not ds.available:
            line(False, f"Data: {key}{tag}", f"no files in {ds.data_dir}  ({build.get(key, '')})")
            continue
        counts = ds.manifest.get("row_counts", {})
        summary = ", ".join(f"{v:,} {k}" for k, v in list(counts.items())[:3])
        line(True, f"Data: {key}{tag}", f"{'real' if ds.real else 'simulated'} · as of {ds.as_of} · {summary}")
        src, tables = next(iter(ds.pg_tables.items()))
        try:
            with psycopg.connect(SETTINGS.pg_dsn, connect_timeout=3) as c:
                n = c.execute(f'SELECT COUNT(*) FROM "{ds.pg_schema}"."{tables[-1] if key == "kaveri" else tables[0]}"').fetchone()[0]
            line(True, f"  Postgres: {src}", f"{n:,} rows in {ds.pg_schema}.{tables[-1] if key == 'kaveri' else tables[0]}")
        except Exception as e:
            line(None, f"  Postgres: {src}", f"{str(e).splitlines()[0][:80]}  (CSV fallback will be used; docker compose up -d)")
    from whychain.harness.zetaris import ZetarisHarness, configured

    if configured():
        z = ZetarisHarness()
        st = z.status()
        detail = f"{st['mode']} · {st.get('url')} {st.get('error', '')}"
        if st["ok"]:
            n = len(z.catalog())
            detail += f" · {n} tables registered for {z.dataset.key}" if n else \
                " · no tables registered yet (python scripts/register_zetaris.py)"
        line(st["ok"], "Zetaris", detail)
    else:
        line(None, "Zetaris", "neither ZETARIS_USER nor ZETARIS_API_KEY set (local DuckDB harness will be used)")
    # memory
    from whychain.memory import Memory

    m = Memory()
    st = m.status()
    if m.online:
        line(True, "memory", f"Meterless bridge at {SETTINGS.meterless_url} (optional adapter) · {st.get('embedder')}")
    else:
        if SETTINGS.meterless_url:
            line(None, "Meterless bridge", f"not reachable at {SETTINGS.meterless_url}; WhyChain's own memory is used")
        n = m.list(100000).get("count", 0)
        on = bool(m._emb and m._emb.active)
        sem = m._emb.embed(["probe"]) if on else None
        line(bool(sem) if on else None, "memory", f"WhyChain memory ({n} items) · recall: {st.get('embedder')}"
             + ("" if sem or not on else f" · embedding failed: {m._emb.last_error}"))
    # models
    llm = LLM()
    if not any(p.configured for p in llm.providers.values()):
        line(False, "models", "no model provider configured: set NEBIUS_API_KEY (Nebius Token Factory) in .env (without one, late-delivery and "
             "supply briefs are written by code only, and open-ended questions can't run)")
    for name, p in llm.providers.items():
        if not p.configured:
            line(None, f"model: {name}", "not configured")
            continue
        t0 = time.time()
        try:
            r = llm._client(p).chat.completions.create(model=p.model, max_tokens=5,
                                                        messages=[{"role": "user", "content": "Reply OK"}])
            line(True, f"model: {name}", f"{p.model} · {time.time() - t0:.1f}s · {r.choices[0].message.content!r}")
        except Exception as e:
            line(False, f"model: {name}", f"{p.model} · {str(e)[:100]}")


if __name__ == "__main__":
    main()
