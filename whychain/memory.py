"""Shared memory and the why-chain graph, owned by WhyChain.

- Memory holds what agents learn, with provenance: confirmed causes, ruled-out causes, lessons, manager decisions and
  the Data Scout's map of how the sources join. It persists across runs (a JSON file in the runs folder), so the
  second investigation starts with what the first one learned. Recall is semantic: every memory and every query is
  embedded with Qwen3-Embedding-8B on Nebius Token Factory and ranked by cosine similarity. Without a key, recall
  falls back to keyword overlap and the UI says so.
- The why-chain graph of a run is folded from the relations its agents wrote to the run's own trace (trace.jsonl),
  so every run's state is event-sourced without a separate service.

Optional adapter: with METERLESS_BRIDGE_URL set and the bridge healthy, memory and the graph go to the Meterless
engines instead (H-MEM and the World Model).
"""
from __future__ import annotations

import json
import math
import queue
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path

import httpx

from whychain.config import SETTINGS, TF_EMBED, env, is_placeholder

WORLD_KINDS_SKIP = {"llm_call"}  # high-volume; still in trace.jsonl
EMBED_DIM = 1024   # Qwen3-Embedding-8B is Matryoshka-trained: 1024 of its 4096 dimensions keep the store small
QUERY_INSTRUCTION = "Instruct: Given a supply-chain question, retrieve earlier findings and lessons that answer it\nQuery: "
MIN_SEMANTIC = 0.35   # below this cosine a memory is unrelated to the question
_FILE_LOCK = threading.Lock()


class Embedder:
    """Qwen3-Embedding-8B on Nebius Token Factory (OpenAI-compatible /embeddings). Never raises: returns None."""

    def __init__(self):
        self.model = embed_model()
        self.key = env("NEBIUS_API_KEY")
        self.url = env("NEBIUS_BASE_URL", "https://api.tokenfactory.us-central1.nebius.com/v1/").rstrip("/") + "/embeddings"
        self.active = self.model.lower() != "off" and not is_placeholder(self.key)
        self.calls = 0
        self.failures = 0
        self.last_error: str | None = None

    def embed(self, texts: list[str], query: bool = False, timeout: float = 30.0) -> list[list[float]] | None:
        if not self.active or not texts:
            return None
        out: list[list[float]] = []
        try:
            for i in range(0, len(texts), 32):
                batch = [(QUERY_INSTRUCTION + t if query else t)[:8000] or " " for t in texts[i:i + 32]]
                self.calls += 1
                r = httpx.post(self.url, timeout=timeout, headers={"authorization": f"Bearer {self.key}"},
                               json={"model": self.model, "input": batch, "dimensions": EMBED_DIM})
                r.raise_for_status()
                for d in sorted(r.json()["data"], key=lambda d: d["index"]):
                    v = d["embedding"]
                    n = math.sqrt(sum(x * x for x in v)) or 1.0
                    out.append([round(x / n, 5) for x in v])
            return out
        except Exception as e:
            self.failures += 1
            self.last_error = f"{type(e).__name__}: {str(e)[:160]}"
            return None

    def label(self) -> str:
        return f"{self.model} (Nebius Token Factory)" if self.active else "keyword overlap (no NEBIUS_API_KEY)"


def embed_model() -> str:
    """Read at use time, so tests (and the doctor) can switch embeddings off with WHYCHAIN_EMBED_MODEL=off."""
    return env("WHYCHAIN_EMBED_MODEL", TF_EMBED)


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class Memory:
    def __init__(self, url: str | None = None, local_path=None):
        self.url = (url if url is not None else SETTINGS.meterless_url or "").rstrip("/")
        self.http = httpx.Client(timeout=15.0)
        self.local_path = Path(local_path or SETTINGS.runs_dir / "_local_memory.json")
        self.vec_path = self.local_path.with_name(self.local_path.stem + "_vectors.json")
        self.engines: dict = {}
        self.embedder: str | None = None
        self.scout: dict | None = None
        # True only when the optional Meterless bridge is configured and healthy
        self.online = bool(self.url) and self._health()
        self._emb = None if self.online else Embedder()
        if self._emb is not None:
            self.embedder = self._emb.label()
        self._q: queue.Queue = queue.Queue()
        if self.online:
            threading.Thread(target=self._drain, daemon=True).start()

    @property
    def backend(self) -> str:
        return "meterless" if self.online else "whychain"

    # ------------------------------------------------------------------ status
    def _health(self) -> bool:
        try:
            r = self.http.get(f"{self.url}/health", timeout=3.0)
            body = r.json()
            self.engines = body.get("engines", {})
            self.embedder = (body.get("embeddings") or {}).get("embedder")
            self.scout = body.get("scout")
            return r.status_code == 200 and bool(body.get("ok"))
        except Exception:
            return False

    def status(self) -> dict:
        if self.online:
            return {"online": True, "url": self.url, "engines": self.engines, "embedder": self.embedder,
                    "scout": self.scout, "backend": "meterless"}
        return {"online": True, "url": self.local_path.name, "engines": {}, "embedder": self.embedder,
                "semantic": bool(self._emb and self._emb.active), "scout": None, "backend": "whychain"}

    # ------------------------------------------------------------------ memory
    def write(self, run_id: str, agent: str, kind: str, content: str, provenance: dict | None = None,
              confidence: float = 0.7, tags: list[str] | None = None) -> str:
        item = {"run_id": run_id, "agent": agent, "kind": kind, "content": content,
                "provenance": provenance or {}, "confidence": confidence, "tags": tags or []}
        if self.online:
            try:
                r = self.http.post(f"{self.url}/memory/write", json=item)
                r.raise_for_status()
                return str(r.json().get("id"))
            except Exception:
                pass
        return self._local_write(item)

    def recall(self, query: str, k: int = 6, tags: list[str] | None = None, kinds: list[str] | None = None,
               exclude_run_id: str | None = None) -> list[dict]:
        if self.online:
            try:
                body = {"query": query, "k": k}
                if tags:
                    body["tags"] = tags
                if kinds:
                    body["kinds"] = kinds
                if exclude_run_id:
                    body["exclude_run_id"] = exclude_run_id
                r = self.http.post(f"{self.url}/memory/recall", json=body)
                r.raise_for_status()
                return r.json().get("items", [])
            except Exception:
                pass
        return self._local_recall(query, k, tags, kinds, exclude_run_id)

    def consolidate(self, run_id: str) -> dict:
        if self.online:
            try:
                r = self.http.post(f"{self.url}/memory/consolidate", json={"run_id": run_id}, timeout=60.0)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                return {"error": str(e)[:200]}
        return self._local_consolidate(run_id)

    def audit(self, limit: int = 50) -> list[dict]:
        if self.online:
            try:
                r = self.http.get(f"{self.url}/memory/audit", params={"limit": limit})
                r.raise_for_status()
                body = r.json()
                return body.get("items", body.get("audit", body if isinstance(body, list) else []))
            except Exception:
                return []
        return self._local_load()[-limit:]

    def list(self, limit: int = 100) -> dict:
        """Browse memories, newest first (for the Memory page)."""
        if self.online:
            try:
                r = self.http.get(f"{self.url}/memory/list", params={"limit": limit})
                r.raise_for_status()
                return r.json()
            except Exception:
                pass
        all_items = self._local_load()
        tiers: dict[str, int] = {}
        for it in all_items:
            tiers[it.get("tier", "working")] = tiers.get(it.get("tier", "working"), 0) + 1
        items = list(reversed(all_items))[:limit]
        return {"count": len(items), "items": items, "tiers": tiers}

    # ------------------------------------------------------------------ the why-chain graph
    def record(self, run_id: str, kind: str, agent: str, data: dict, seq: int | None = None) -> None:
        if self.online and kind not in WORLD_KINDS_SKIP:
            ev = {"run_id": run_id, "type": kind, "actor": agent, "payload": _small(data)}
            if seq is not None:
                ev["event_id"] = f"{run_id}-{seq}"  # makes retries idempotent in the World Model
            self._q.put(ev)

    def world_state(self, run_id: str) -> dict:
        if self.online:
            try:
                return self.http.get(f"{self.url}/world/state", params={"run_id": run_id}).json()
            except Exception:
                return {}
        if not re.fullmatch(r"[\w\-]+", run_id or ""):
            return {}
        return world_from_trace(SETTINGS.runs_dir / run_id / "trace.jsonl")

    def flush(self, timeout: float = 5.0) -> None:
        if self.online:
            done = threading.Event()
            self._q.put(done)
            done.wait(timeout)

    def _drain(self) -> None:
        while True:
            ev = self._q.get()
            if isinstance(ev, threading.Event):
                ev.set()
                continue
            try:
                self.http.post(f"{self.url}/world/events", json=ev, timeout=5.0)
            except Exception:
                pass

    # ------------------------------------------------------------------ WhyChain's own store
    def _local_load(self) -> list[dict]:
        try:
            return json.loads(self.local_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, items: list[dict]) -> None:
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.local_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.local_path)

    def _vectors(self) -> dict:
        model = embed_model()
        fresh = {"model": model, "dim": EMBED_DIM, "vectors": {}}
        try:
            v = json.loads(self.vec_path.read_text(encoding="utf-8"))
            return v if v.get("model") == model and v.get("dim") == EMBED_DIM else fresh
        except Exception:
            return fresh

    def _save_vectors(self, v: dict) -> None:
        self.vec_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.vec_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(v), encoding="utf-8")
        tmp.replace(self.vec_path)

    def _local_write(self, item: dict) -> str:
        item = {**item, "id": uuid.uuid4().hex[:10], "created_at": datetime.now().isoformat(timespec="seconds"),
                "tier": "working"}
        with _FILE_LOCK:   # embedded later, in one batch (consolidation, or the next recall)
            items = self._local_load()
            items.append(item)
            self._save(items)
        return item["id"]

    def _embed_missing(self, pool: list[dict]) -> dict:
        """Vectors for every memory in the pool, embedding the ones that have none in one batched call."""
        with _FILE_LOCK:
            v = self._vectors()
            missing = [it for it in pool if it.get("id") not in v["vectors"]]
            if missing and self._emb and self._emb.active:
                got = self._emb.embed([it.get("content", "") for it in missing])
                if got:
                    for it, vec in zip(missing, got):
                        v["vectors"][it["id"]] = vec
                    self._save_vectors(v)
        return v

    def _local_recall(self, query: str, k: int, tags: list[str] | None, kinds: list[str] | None = None,
                      exclude_run_id: str | None = None) -> list[dict]:
        pool = [it for it in self._local_load()
                if (not tags or set(tags) & set(it.get("tags", [])))
                and (not kinds or it.get("kind") in kinds)
                and (not exclude_run_id or it.get("run_id") != exclude_run_id)]
        if not pool:
            return []
        # the data map is matched by its catalog fingerprint, not by meaning: no embedding call for it
        scored = None if "data_map" in (tags or []) else self._semantic(query, pool)
        if scored is None:   # no embeddings: keyword overlap
            words = set(re.findall(r"[a-z0-9\-]{3,}", query.lower()))
            scored = []
            for it in pool:
                text = (it.get("content", "") + " " + " ".join(it.get("tags", []))).lower()
                s = sum(1 for w in words if w in text)
                if s or tags:
                    scored.append((float(s), it))
        scored.sort(key=lambda x: -x[0])
        return [dict(it, score=round(s, 3)) for s, it in scored[:k]]

    def _semantic(self, query: str, pool: list[dict]) -> list[tuple[float, dict]] | None:
        if not (self._emb and self._emb.active):
            return None
        q = self._emb.embed([query], query=True, timeout=10.0)   # recall waits on it: keywords if it's slow
        if not q:
            return None
        v = self._embed_missing(pool)
        out = []
        for it in pool:
            vec = v["vectors"].get(it.get("id"))
            if vec is None:
                continue
            s = _cos(q[0], vec)
            if s >= MIN_SEMANTIC or "data_map" in (it.get("tags") or []):
                out.append((s, it))
        return out

    def _local_consolidate(self, run_id: str) -> dict:
        """A memory another investigation reached too is corroborated: it moves from the working tier to the
        long-term one, with the corroborating runs in its provenance. Exact repeats of a long-term memory are
        dropped."""
        self._embed_missing([it for it in self._local_load() if "data_map" not in (it.get("tags") or [])])
        with _FILE_LOCK:
            items = self._local_load()
            v = self._vectors()["vectors"]
            others = [it for it in items if it.get("run_id") != run_id and it.get("kind") in ("finding", "fact", "lesson")]
            promoted, dropped, keep = 0, 0, {it["id"] for it in items}
            for it in items:
                if it.get("run_id") != run_id or it.get("kind") not in ("finding", "fact", "lesson") \
                        or "data_map" in (it.get("tags") or []):
                    continue
                body = _claim(it.get("content", ""))
                twins = [o for o in others if _claim(o.get("content", "")) == body
                         or (it["id"] in v and o.get("id") in v and _cos(v[it["id"]], v[o["id"]]) >= 0.92)]
                if not twins:
                    continue
                if any(o.get("content") == it.get("content") and o.get("tier") == "long_term" for o in twins):
                    keep.discard(it["id"])
                    dropped += 1
                    continue
                it["tier"] = "long_term"
                it.setdefault("provenance", {})["corroborated_by"] = sorted({str(o.get("run_id")) for o in twins})[:5]
                promoted += 1
            if promoted or dropped:
                self._save([it for it in items if it["id"] in keep])
        return {"promoted": promoted, "duplicates_dropped": dropped, "backend": "whychain"}


def _claim(text: str) -> str:
    """A memory's claim without its date stamp, for comparing findings across runs."""
    return re.sub(r"\(\d{4}-\d\d-\d\d\)", "", text or "").strip().lower()


def world_from_trace(path: Path) -> dict:
    """The why-chain graph of one run: the relations and entities its agents wrote, folded in trace order (a later
    relation between the same two nodes replaces the earlier one)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}
    rels: dict[tuple, dict] = {}
    ents: dict[str, dict] = {}
    for line in lines:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        for e in ev.get("entities") or []:
            if isinstance(e, dict) and e.get("name"):
                eid = str(e.get("id") or f"{e.get('type', 'thing')}:{e['name']}")
                ents[eid] = {"id": eid, "type": e.get("type", "thing"), "name": e["name"]}
        for r in ev.get("relations") or []:
            if not isinstance(r, dict):
                continue
            f, t = r.get("from") or {}, r.get("to") or {}
            fn = f.get("name") if isinstance(f, dict) else str(f)
            tn = t.get("name") if isinstance(t, dict) else str(t)
            if not fn or not tn:
                continue
            for node in (f, t):
                if isinstance(node, dict) and node.get("name"):
                    eid = f"{node.get('type', 'thing')}:{node['name']}"
                    ents.setdefault(eid, {"id": eid, "type": node.get("type", "thing"), "name": node["name"]})
            rels[(fn, r.get("type"), tn)] = {"from_name": fn, "type": r.get("type"), "to_name": tn,
                                             "confidence": r.get("confidence"), "attrs": r.get("attrs") or {},
                                             "open": bool(r.get("open", False))}
    if not rels and not ents:
        return {}
    return {"relations": list(rels.values()), "entities": list(ents.values()), "backend": "whychain-trace"}


WORLD_KEYS = {"status", "facts", "entities", "relations"}  # structured keys the World Model folds into its graph


def _small(data: dict, limit: int = 1500) -> dict:
    out = {}
    for k, v in data.items():
        if k in WORLD_KEYS:
            out[k] = v
            continue
        s = v if isinstance(v, (int, float, bool)) or v is None else str(v)
        out[k] = s[:limit] if isinstance(s, str) else s
    return out
