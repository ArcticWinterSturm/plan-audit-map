#!/usr/bin/env python3
"""
mtd_intervention.py — the Intervention Paste Bar engine.

The missing middle, shipped as a manual lever
---------------------------------------------
Weak/preview models routinely use the plan-audit-map MCP for the first stretch
of a solution, then silently drop back to native chain-of-thought that is
uninformed by prior errors and start to flail in circles.  This module powers
a small section in the taskbar desk bar where a human pastes the circling
agent's last few messages and gets back a compact, copy-paste intervention:

  1. RETRIEVED CONTEXT — chunks of the single most relevant skill document,
     pulled from ONE folder of skill files via a fast local embedding model
     (Nomic embed via Ollama / LM Studio when present, deterministic hashed
     fallback when not — everything is stdlib).
  2. INSTRUCTION — an explicit "use the plan-audit-map tool NOW" directive with
     a seeded first tool call (continuing the best-matching prior session).
  3. THE NUMBER — an estimated performance improvement from re-engaging the
     MCP ("~14%"), derived from REAL computed quantities, never placeholders:
       * repetition diagnostics on the pasted text itself,
       * the agent's own prior plan-audit-map history in memory.db
         (sessions, thoughts, outcomes, calibration table),
       * the cognitive metrics the MCP already computes (parsed from the
         last recorded tool response in the wire log),
       * wire-log evidence that tool usage dropped off.

No ground-truth corpus is pre-loaded into the agent; the human pays two
copy-paste round trips, the agent gets proven context on demand.  If it can
re-derive a better solution from the injected framing, good; if not, the
retrieved chunks still point at the documented fix.

Everything here is stdlib-only and safe to run headless (used by tests).
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import mtd_shared

APP = "planauditmap-intervention"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_INTERVENTION_CONFIG: Dict[str, Any] = {
    "skills_dir": "",              # "" -> <desk>/skills, then ~/.plan-audit-map/skills
    "embedding_provider": "auto",  # auto | ollama | lmstudio | nomic | local
    "embedding_endpoint": "",      # e.g. http://127.0.0.1:11434
    "embedding_model": "nomic-embed-text",
    "top_k": 3,
    "min_score": 0.04,
    "max_chunk_chars": 1400,
    "max_message_chars": 3000,     # cap the copy-paste block (token budget!)
    "min_paste_chars": 40,
    "max_paste_chars": 12000,      # analyse at most this much of the paste
}

STOPWORDS = set(
    """a an the and or but if then else for to of in on at by with from as is are
    was were be been being it its this that these those i you he she they we me
    my your our their them his her not no yes do does did done can could should
    would will shall may might must have has had let lets let's im i'm ive i've
    dont don't doesnt doesn't wasnt wasn't whats what's thats that's theres
    there's about into over under again more most some such only own same so
    than too very just now also back out up down here when where which who
    whom why how all any both each few nor other own s t d ll m o re ve y
    """.split()
)

_RETRY_MARKERS = (
    "let me try", "let me check", "try again", "one more", "another approach",
    "wait,", "hmm,", "actually,", "apologize", "apologies", "misread",
    "let me re", "re-examine", "recheck", "start over", "go back",
    "still failing", "same error", "again:", "attempt",
)


def intervention_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Merge intervention settings over defaults.

    Accepts either the full desk-bar config shape ({"intervention": {...}})
    or a flat dict of intervention keys directly (handy for tests/scripts).
    """
    out = dict(DEFAULT_INTERVENTION_CONFIG)
    section = cfg.get("intervention")
    if not isinstance(section, dict):
        section = {k: v for k, v in cfg.items() if k in out}
    for k, v in section.items():
        if k in out:
            out[k] = v
    return out


def skills_dir_for(cfg: Dict[str, Any]) -> Optional[Path]:
    """Resolve the ONE folder of skill documents to chunk + embed."""
    raw = cfg.get("skills_dir") or ""
    if raw:
        p = Path(os.path.expandvars(os.path.expanduser(raw)))
        return p if p.is_dir() else None
    desk = mtd_shared.desk_dir()
    for cand in (desk / "skills",            # flat layout: desk files + skills/
                 desk.parent / "skills",     # shipped layout: plan-audit-map-desk/skills/
                 mtd_shared.config_dir() / "skills"):
        if cand.is_dir():
            return cand
    return None


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")


def chunk_markdown(text: str, max_chars: int = 1400) -> List[Dict[str, str]]:
    """Split a markdown skill into titled chunks.

    Sections are cut at ## / ### headings; over-long sections are windowed at
    paragraph boundaries with a small overlap so retrieval always gets a
    self-contained piece of the document.
    """
    sections: List[Tuple[str, str]] = []
    title = "(top)"
    buf: List[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append((title, body))
        buf.clear()

    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m and len(m.group(1)) <= 2:  # cut at ## (### stays inside)
            flush()
            title = m.group(2).strip()[:120] or "(heading)"
        elif m:  # ### subheading: soft cut
            flush()
            title = m.group(2).strip()[:120] or "(sub)"
        buf.append(line)
    flush()

    chunks: List[Dict[str, str]] = []
    for sec_title, body in sections:
        if len(body) <= max_chars:
            chunks.append({"title": sec_title, "text": body})
            continue
        # window the long section at paragraph boundaries
        paras = body.split("\n\n")
        window: List[str] = []
        size = 0
        for para in paras:
            if size + len(para) > max_chars and window:
                chunks.append({"title": sec_title,
                               "text": "\n\n".join(window).strip()})
                window = window[-1:]  # 1-paragraph overlap
                size = len(window[0]) if window else 0
            window.append(para)
            size += len(para) + 2
        if window:
            chunks.append({"title": sec_title, "text": "\n\n".join(window).strip()})
    return chunks


# ---------------------------------------------------------------------------
# Embedding providers
# ---------------------------------------------------------------------------

class HashedEmbedder:
    """Deterministic offline fallback: hashed uni+bi-gram TF vector.

    Not semantic — but it is fast, dependency-free, stable across runs, and
    good enough to pull the right *document* when the paste shares
    vocabulary with it (which circling traces usually do: they name tools,
    files and errors that the skills also name).
    """

    name = "local-hashed"
    dim = 512

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        toks = tokenize(text)
        grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        for g in grams:
            vec[_stable_hash(g) % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def _stable_hash(s: str) -> int:
    import hashlib

    return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:12], 16)


class HttpEmbedder:
    """Embeddings from a local HTTP endpoint (Ollama / LM Studio / OpenAI-ish)."""

    def __init__(self, endpoint: str, model: str, style: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.style = style  # "ollama" | "openai"
        self.name = f"http:{style}@{endpoint}"

    # -- transport ---------------------------------------------------------

    def _post(self, path: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        req = urllib.request.Request(
            self.endpoint + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path: str, timeout: float) -> Any:
        with urllib.request.urlopen(self.endpoint + path, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def alive(self) -> bool:
        try:
            if self.style == "ollama":
                self._get("/api/tags", timeout=1.0)
            else:
                self._get("/v1/models", timeout=1.0)
            return True
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            return False

    # -- embedding ---------------------------------------------------------

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        if self.style == "ollama":
            try:  # modern batch endpoint (Ollama >= 0.2.6)
                data = self._post("/api/embed", {"model": self.model,
                                                 "input": list(texts)},
                                  timeout=60.0)
                embs = data.get("embeddings")
                if isinstance(embs, list) and len(embs) == len(texts):
                    return [_l2(e) for e in embs]
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                pass
            # legacy single-prompt endpoint
            out: List[List[float]] = []
            for t in texts:
                data = self._post("/api/embeddings",
                                  {"model": self.model, "prompt": t},
                                  timeout=60.0)
                out.append(_l2(data["embedding"]))
            return out
        # OpenAI-compatible (LM Studio, llama.cpp server, vLLM, ...)
        data = self._post("/v1/embeddings",
                          {"model": self.model, "input": list(texts)},
                          timeout=60.0)
        items = sorted(data["data"], key=lambda d: d.get("index", 0))
        return [_l2(d["embedding"]) for d in items]


class NomicCloudEmbedder:
    """api.nomic.ai (only used when explicitly configured — it costs money)."""

    name = "nomic-cloud"

    def __init__(self, model: str = "nomic-embed-text-v1.5") -> None:
        self.model = model
        self.key = os.environ.get("NOMIC_API_KEY", "")

    def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        req = urllib.request.Request(
            "https://api.nomic.ai/v1/embedding/text",
            data=json.dumps({"model": self.model, "texts": list(texts),
                             "task_type": "search_document"}).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [_l2(e) for e in data["embeddings"]]


def _l2(vec: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(float(v) * float(v) for v in vec)) or 1.0
    return [float(v) / norm for v in vec]


def resolve_provider(cfg: Dict[str, Any],
                     log: Callable[[str], None] = lambda m: None
                     ) -> Tuple[Any, str]:
    """Pick the embedding provider. Returns (embedder, description)."""
    want = str(cfg.get("embedding_provider") or "auto").lower()
    model = cfg.get("embedding_model") or "nomic-embed-text"
    endpoint = cfg.get("embedding_endpoint") or ""

    def ollama(ep: str) -> HttpEmbedder:
        return HttpEmbedder(ep, model, "ollama")

    def lmstudio(ep: str) -> HttpEmbedder:
        return HttpEmbedder(ep, model, "openai")

    if want == "local":
        return HashedEmbedder(), "offline fallback (forced by config)"
    if want == "nomic":
        emb = NomicCloudEmbedder()
        if not emb.key:
            log("NOMIC_API_KEY not set — falling back to local embedding")
            return HashedEmbedder(), "offline fallback (no NOMIC_API_KEY)"
        return emb, f"nomic cloud ({emb.model})"

    if want in ("ollama", "lmstudio") and endpoint:
        cand = ollama(endpoint) if want == "ollama" else lmstudio(endpoint)
        if cand.alive():
            return cand, f"{want} @ {endpoint} ({model})"
        log(f"{want} not reachable at {endpoint} — falling back")
        return HashedEmbedder(), "offline fallback (endpoint unreachable)"

    if want == "auto" or want in ("ollama", "lmstudio"):
        for cand, desc in ((ollama(endpoint or "http://127.0.0.1:11434"),
                            f"ollama ({model})"),
                           (lmstudio(endpoint or "http://127.0.0.1:1234"),
                            f"lmstudio ({model})")):
            try:
                if cand.alive():
                    return cand, desc
            except Exception:  # noqa: BLE001
                continue
        if want == "auto":
            log("no local embedding server found — using offline fallback")
            return HashedEmbedder(), "offline fallback (no server found)"
        return HashedEmbedder(), "offline fallback (forced provider unavailable)"
    return HashedEmbedder(), "offline fallback (unknown provider)"


# ---------------------------------------------------------------------------
# Skills index (one folder -> chunked -> embedded -> cached)
# ---------------------------------------------------------------------------

class SkillsIndex:
    """Chunked + embedded view of the skills folder, cached on disk."""

    VERSION = 1

    def __init__(self, directory: Path, embedder: Any, max_chunk_chars: int = 1400,
                 log: Callable[[str], None] = lambda m: None) -> None:
        self.dir = directory
        self.embedder = embedder
        self.max_chunk_chars = max_chunk_chars
        self.log = log
        self.chunks: List[Dict[str, Any]] = []
        self.cache_path = mtd_shared.config_dir(create=True) / "skills-index.json"
        self.loaded_from_cache = False

    # -- build --------------------------------------------------------------

    def build(self) -> int:
        files = sorted(p for p in self.dir.glob("*.md")
                       if not p.name.upper().startswith("README"))
        if not files:
            self.chunks = []
            return 0

        cache = self._load_cache()
        by_path: Dict[str, Dict[str, Any]] = {}
        if cache:
            for entry in cache.get("files", []):
                by_path[entry["path"]] = entry

        rebuilt_files = 0
        entries: List[Dict[str, Any]] = []
        for path in files:
            stat = path.stat()
            key = str(path)
            cached = by_path.get(key)
            if (cached and cached.get("mtime") == stat.st_mtime
                    and cached.get("size") == stat.st_size):
                entries.append(cached)          # reuse cached chunks + vectors
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            pieces = chunk_markdown(text, self.max_chunk_chars)
            vecs = self.embedder.embed_batch([p["text"] for p in pieces]) \
                if pieces else []
            entries.append({
                "path": key, "name": path.name,
                "mtime": stat.st_mtime, "size": stat.st_size,
                "chunks": [{"title": p["title"],
                            "text": p["text"],
                            "file": path.name,
                            "vec": v}
                           for p, v in zip(pieces, vecs)],
            })
            rebuilt_files += 1
            self.log(f"indexed {path.name} ({len(pieces)} chunks)")

        if rebuilt_files:
            self._save_cache(entries)
        elif cache and not self.chunks:
            self.loaded_from_cache = True
        self.chunks = [dict(c, file=e["name"])
                       for e in entries for c in e["chunks"]]
        # ensure cache exists even when everything was fresh
        if not self.cache_path.exists():
            self._save_cache(entries)
            self.loaded_from_cache = False
        return len(self.chunks)

    def _load_cache(self) -> Optional[Dict[str, Any]]:
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (raw.get("version") != self.VERSION
                or raw.get("provider") != self.embedder.name):
            return None
        return raw

    def _save_cache(self, entries: List[Dict[str, Any]]) -> None:
        try:
            self.cache_path.write_text(
                json.dumps({"version": self.VERSION,
                            "provider": self.embedder.name,
                            "built": mtd_shared.iso_now(),
                            "files": entries}),
                encoding="utf-8")
        except OSError as exc:
            self.log(f"could not save skills index cache: {exc}")

    # -- search -------------------------------------------------------------

    def search(self, query_vec: List[float], paste_tokens: List[str],
               top_k: int = 3,
               min_score: float = 0.04) -> List[Tuple[float, Dict[str, Any]]]:
        """Hybrid retrieval: 0.65 * embedding cosine + 0.35 * lexical overlap.

        The lexical half keeps retrieval honest when the embedder is the
        offline hashed fallback (pure bag-of-words): a paste quoting
        "sqlite segfault / node 20" still lands on the troubleshooting table
        that says "better-sqlite3@13 on Node 20".
        """
        top = set(_top_tokens(paste_tokens, 15))
        if not top:
            top = set(paste_tokens)
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for chunk in self.chunks:
            vec = chunk.get("vec")
            if not vec:
                continue
            cos = sum(a * b for a, b in zip(query_vec, vec))
            toks = set(chunk.get("toks") or tokenize(chunk.get("text", "")))
            lexical = (len(top & toks) / len(top)) if top else 0.0
            score = 0.65 * cos + 0.35 * lexical
            if score >= min_score:
                scored.append((score, chunk))
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored[:top_k]


# ---------------------------------------------------------------------------
# Diagnostics on the pasted trace (real numbers, cheaply computed)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN_RE.findall(text.lower())
            if t not in STOPWORDS and len(t) > 2]


def diagnose(paste: str) -> Dict[str, Any]:
    """Circularity metrics for the pasted reasoning trace."""
    tokens = _TOKEN_RE.findall(paste.lower())
    content = [t for t in tokens if t not in STOPWORDS]
    n = len(tokens)

    # repeated 5-gram ratio: of all 5-gram positions, the fraction whose
    # 5-gram occurs more than once in the paste
    five = [tuple(tokens[i:i + 5]) for i in range(max(0, n - 4))]
    counts: Dict[Tuple[str, ...], int] = {}
    if five:
        for g in five:
            counts[g] = counts.get(g, 0) + 1
        repeated = sum(c for c in counts.values() if c > 1)
        rep_ratio = repeated / len(five)
    else:
        rep_ratio = 0.0

    distinct = len(set(content)) / len(content) if content else 1.0

    low = paste.lower()
    retry_hits = sum(low.count(m) for m in _RETRY_MARKERS)

    # longest repeated block (in tokens): first-occurrence map + greedy
    # backward extension from the second occurrence of a repeated 5-gram
    longest = 0
    if counts:
        first: Dict[Tuple[str, ...], int] = {}
        for i, g in enumerate(five):
            if g in first:
                longest = max(longest, 5)
                j, k = first[g], 0
                while j - k - 1 >= 0 and i - k - 1 >= 0 and \
                        five[j - k - 1] == five[i - k - 1]:
                    k += 1
                longest = max(longest, 5 + k)
            else:
                first[g] = i

    return {
        "chars": len(paste),
        "tokens": n,
        "content_tokens": len(content),
        "distinct_ratio": round(distinct, 3),
        "rep5_ratio": round(rep_ratio, 3),
        "longest_repeat_tokens": longest,
        "retry_markers": retry_hits,
    }


# ---------------------------------------------------------------------------
# Prior work in memory.db (the proven-reasoning store)
# ---------------------------------------------------------------------------

class PriorWork:
    """Read-only mining of the plan-audit-map memory database."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.path = Path(db_path) if db_path else mtd_shared.db_path()
        self.ok = False
        self.conn: Optional[sqlite3.Connection] = None
        if self.path.exists():
            try:
                uri = f"file:{self.path.as_posix()}?mode=ro"
                self.conn = sqlite3.connect(uri, uri=True, timeout=5.0)
                self.conn.row_factory = sqlite3.Row
                self.conn.execute("PRAGMA busy_timeout = 5000")
                self.ok = True
            except sqlite3.Error:
                self.ok = False

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def _has(self, table: str) -> bool:
        if not self.ok:
            return False
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view')"
            " AND name=?", (table,)).fetchone()
        return row is not None

    def collect(self, paste_tokens: List[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "db_exists": self.ok, "sessions": 0, "thoughts": 0, "outcomes": 0,
            "matched_thoughts": 0, "matched_sessions": 0, "best_session": None,
            "best_session_goal": None, "best_session_confidence": None,
            "recall": 0.0, "calibration_gap": None, "calibration_rows": 0,
            "calibration_samples": 0, "last_cognitive": None,
            "mcp_calls_total": 0, "events_since_last_mcp_call": None,
            "top_tokens_matched": [],
        }
        if not self.ok:
            return out
        conn = self.conn

        for table, key in (("sessions", "sessions"), ("thoughts", "thoughts"),
                           ("outcomes", "outcomes")):
            if self._has(table):
                try:
                    out[key] = conn.execute(
                        f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
                except sqlite3.Error:
                    pass

        # ---- match prior thoughts against the paste's salient tokens ------
        top_tokens = _top_tokens(paste_tokens, 12)
        if top_tokens and self._has("thoughts"):
            like = " OR ".join(f"thought LIKE ?" for _ in top_tokens)
            args = [f"%{t}%" for t in top_tokens]
            try:
                rows = conn.execute(
                    f"SELECT session_id, COUNT(*) hits FROM thoughts"
                    f" WHERE {like} GROUP BY session_id"
                    f" ORDER BY hits DESC LIMIT 5", args).fetchall()
                out["matched_thoughts"] = sum(r["hits"] for r in rows)
                out["matched_sessions"] = len(rows)
                if rows:
                    out["best_session"] = rows[0]["session_id"]
                    # recall: share of the paste's top tokens that exist in
                    # prior thoughts at all (real coverage of prior work)
                    any_like = " OR ".join(f"thought LIKE ?" for _ in top_tokens)
                    found = 0
                    for t in top_tokens:
                        hit = conn.execute(
                            f"SELECT 1 FROM thoughts WHERE thought LIKE ?"
                            f" LIMIT 1", (f"%{t}%",)).fetchone()
                        if hit:
                            found += 1
                    out["recall"] = round(found / len(top_tokens), 3)
                    out["top_tokens_matched"] = [
                        t for t in top_tokens
                        if conn.execute("SELECT 1 FROM thoughts WHERE thought"
                                        " LIKE ? LIMIT 1",
                                        (f"%{t}%",)).fetchone()]
            except sqlite3.Error:
                pass

        # ---- best prior session outcome ------------------------------------
        if out["best_session"] and self._has("sessions"):
            try:
                row = conn.execute(
                    "SELECT goal_achieved, confidence_level FROM sessions"
                    " WHERE id = ?", (out["best_session"],)).fetchone()
                if row:
                    out["best_session_goal"] = row["goal_achieved"]
                    out["best_session_confidence"] = row["confidence_level"]
            except sqlite3.Error:
                pass

        # ---- calibration (the MCP's own number crunching, persisted) -------
        if self._has("confidence_calibration"):
            try:
                row = conn.execute(
                    "SELECT COUNT(*) rows_, COALESCE(SUM(sample_size),0) n,"
                    " CASE WHEN COALESCE(SUM(sample_size),0) > 0"
                    "      THEN SUM(sample_size * ABS(predicted_bucket -"
                    "                actual_success_rate)) / SUM(sample_size)"
                    "      ELSE AVG(ABS(predicted_bucket - actual_success_rate))"
                    " END gap"
                    " FROM confidence_calibration").fetchone()
                out["calibration_rows"] = row["rows_"]
                out["calibration_samples"] = row["n"]
                if row["rows_"]:
                    out["calibration_gap"] = round(row["gap"], 3)
            except sqlite3.Error:
                pass

        # ---- wire log: cognitive metrics + did MCP usage drop off? ---------
        if self._has("raw_mcp_events"):
            try:
                row = conn.execute(
                    "SELECT COUNT(*) c FROM raw_mcp_events"
                    " WHERE method='tools/call' AND direction IN"
                    " ('request','response')").fetchone()
                out["mcp_calls_total"] = row["c"]
                last = conn.execute(
                    "SELECT id, response_json FROM raw_mcp_events"
                    " WHERE method='tools/call' AND response_json IS NOT NULL"
                    " ORDER BY id DESC LIMIT 1").fetchone()
                if last:
                    out["events_since_last_mcp_call"] = conn.execute(
                        "SELECT COUNT(*) c FROM raw_mcp_events WHERE id > ?",
                        (last["id"],)).fetchone()["c"]
                    out["last_cognitive"] = _parse_cognitive(last["response_json"])
            except sqlite3.Error:
                pass
        return out


def _top_tokens(tokens: List[str], k: int) -> List[str]:
    counts: Dict[str, int] = {}
    for t in tokens:
        if len(t) > 3:
            counts[t] = counts.get(t, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [t for t, _ in ranked[:k]]


def _parse_cognitive(response_json: str) -> Optional[Dict[str, Any]]:
    """Pull the cognitive metrics out of a stored tools/call response."""
    try:
        resp = json.loads(response_json)
        content = (resp.get("result") or {}).get("content") or []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                payload = json.loads(item.get("text", ""))
                if isinstance(payload, dict):
                    keep = {}
                    for key in ("session_id", "thought_number",
                                "total_thoughts", "next_thought_needed",
                                "reasoning_mode", "metacognitive_awareness",
                                "breakthrough_likelihood", "creative_pressure",
                                "cognitive_flexibility", "insight_potential",
                                "detected_biases"):
                        if key in payload:
                            keep[key] = payload[key]
                    return keep or None
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return None


# ---------------------------------------------------------------------------
# The improvement estimate (rough, but every input is a real measurement)
# ---------------------------------------------------------------------------

def estimate_improvement(diag: Dict[str, Any], prior: Dict[str, Any]
                         ) -> Dict[str, Any]:
    """Derive the '~X% better with plan-audit-map' number, with shown work.

    Components (all measured, none invented):
      rep_gain     — pasted trace is rep5_ratio duplicated reasoning; a
                     structured re-entry with memory avoids re-deriving it.
                     rep5_ratio * 25 pts.
      calib_gain   — the agent's self-confidence is off from actual success
                     by calibration_gap on record; the MCP's calibrated
                     confidence table corrects that. calibration_gap * 30 pts.
      recall_gain  — recall share of the problem already solved in prior
                     plan-audit-map thoughts; re-derivation duplicates it.
                     recall * 20 pts.
      drop_bonus   — wire log shows tools/call stopped while the
                     conversation kept going (the classic "forgot the MCP").
                     +4 pts flat when events_since_last_mcp_call >= 10.
      transfer     — 0.6: not all recovered effort converts to performance.
    """
    rep_gain = diag.get("rep5_ratio", 0.0) * 25.0
    gap = prior.get("calibration_gap")
    calib_gain = (gap * 30.0) if gap is not None else 0.0
    recall_gain = prior.get("recall", 0.0) * 20.0
    since = prior.get("events_since_last_mcp_call")
    drop_bonus = 4.0 if (since is not None and since >= 10) else 0.0

    raw = rep_gain + calib_gain + recall_gain + drop_bonus
    estimate = max(5, min(45, round(raw * 0.6)))

    parts = [f"repetition {diag.get('rep5_ratio', 0):.2f}→+{rep_gain:.1f}"]
    if gap is not None:
        parts.append(f"calibration gap {gap:.2f} "
                     f"(n={prior.get('calibration_samples', 0)})→+{calib_gain:.1f}")
    else:
        parts.append("calibration gap n/a→+0")
    parts.append(f"prior-work recall {prior.get('recall', 0):.2f}→+{recall_gain:.1f}")
    if drop_bonus:
        parts.append(f"mcp dropped ({since} events since last call)→+{drop_bonus:.0f}")
    return {
        "estimate": estimate,
        "work": "; ".join(parts) + f"; ×0.6 transfer = {raw * 0.6:.1f} → ~{estimate}%",
        "rep_gain": round(rep_gain, 1),
        "calib_gain": round(calib_gain, 1),
        "recall_gain": round(recall_gain, 1),
        "drop_bonus": drop_bonus,
    }


# ---------------------------------------------------------------------------
# Build the intervention
# ---------------------------------------------------------------------------

def build_intervention(paste: str, cfg: Dict[str, Any],
                       log: Callable[[str], None] = lambda m: None
                       ) -> Dict[str, Any]:
    """Full pipeline: paste text -> ready-to-paste intervention block."""
    out: Dict[str, Any] = {
        "ok": False, "error": "", "provider": "", "message": "",
        "diagnostics": None, "prior": None, "estimate": None,
        "chunks": [], "index_chunks": 0, "index_files": 0,
        "elapsed_ms": 0,
    }
    t0 = time.time()
    ivp = intervention_config(cfg)

    paste = (paste or "").strip()
    if len(paste) < int(ivp.get("min_paste_chars", 40)):
        out["error"] = ("Paste the agent's last few messages first (a few "
                        "lines of its circling output).")
        return out
    paste = paste[: int(ivp.get("max_paste_chars", 12000))]

    # ---- 0. diagnostics on the paste --------------------------------------
    diag = diagnose(paste)
    out["diagnostics"] = diag
    paste_tokens = tokenize(paste)

    # ---- 1. skills folder -> chunks -> embedding -> retrieval -------------
    sdir = skills_dir_for(ivp)
    if sdir is None:
        out["error"] = ("No skills folder found. Drop *.md skill files into "
                        "plan-audit-map-desk/skills/ (or set "
                        "intervention.skills_dir in desk-bar.json).")
        return out
    embedder, provider_desc = resolve_provider(ivp, log=log)
    out["provider"] = provider_desc
    index = SkillsIndex(sdir, embedder,
                        int(ivp.get("max_chunk_chars", 1400)), log=log)
    n_chunks = index.build()
    out["index_chunks"] = n_chunks
    out["index_files"] = len([p for p in sdir.glob("*.md")
                              if not p.name.upper().startswith("README")])
    if n_chunks == 0:
        out["error"] = f"No .md skill documents found in {sdir}"
        return out

    query_vec = embedder.embed_batch([paste])[0]
    hits = index.search(query_vec, paste_tokens,
                        int(ivp.get("top_k", 3)),
                        float(ivp.get("min_score", 0.04)))
    out["chunks"] = [
        {"file": h.get("file"), "title": h.get("title"),
         "score": round(s, 3), "text": h.get("text", "")}
        for s, h in hits
    ]

    # ---- 2. prior work in memory.db ---------------------------------------
    prior = PriorWork().collect(paste_tokens)
    out["prior"] = prior

    # ---- 3. the number -----------------------------------------------------
    est = estimate_improvement(diag, prior)
    out["estimate"] = est

    # ---- 4. render the copy-paste block ------------------------------------
    out["message"] = _render(paste, diag, prior, est, out["chunks"], ivp)
    out["ok"] = True
    out["elapsed_ms"] = int((time.time() - t0) * 1000)
    return out


def _render(paste: str, diag: Dict[str, Any], prior: Dict[str, Any],
            est: Dict[str, Any], chunks: List[Dict[str, Any]],
            ivp: Dict[str, Any]) -> str:
    """Assemble the intervention block under a strict character budget.

    Priority order when the budget is tight (it usually is — the whole point
    is NOT pre-loading thousands of tokens): diagnosis + instruction first,
    retrieved chunks fill whatever budget remains.  The instruction must
    never be truncated away by chunk text.
    """
    cap = int(ivp.get("max_message_chars", 2600))

    # ---- part A: header + diagnosis ----------------------------------------
    a: List[str] = []
    add = a.append
    add("═" * 62)
    add("PLAN-AUDIT-MAP INTERVENTION — you are circling. Use the plan-audit-map")
    add("MCP tool for your NEXT step; do not answer from unaided memory.")
    add("═" * 62)
    add("")
    add("DIAGNOSIS (measured from your paste + this machine's plan-audit-map")
    add("memory — every number below is computed, none invented):")
    add(f"- Pasted trace: {diag['tokens']} tokens, "
        f"{int(diag['rep5_ratio'] * 100)}% repeated 5-grams "
        f"(longest repeat ≈ {diag['longest_repeat_tokens']} tokens, "
        f"{diag['retry_markers']} retry/hedge markers).")
    if prior.get("db_exists"):
        add(f"- Memory: {prior['sessions']} session(s) / {prior['thoughts']} "
            f"thought(s) / {prior['outcomes']} outcome(s), "
            f"{prior['mcp_calls_total']} MCP tool calls on the wire.")
        if prior.get("matched_thoughts"):
            goal = ("goal ACHIEVED" if prior.get("best_session_goal")
                    else "goal not marked achieved")
            add(f"- Overlaps prior work: {prior['matched_thoughts']} matching "
                f"thought(s) over {prior['matched_sessions']} session(s); best "
                f"prior session {str(prior['best_session'])[:16]}… ({goal}, "
                f"confidence {prior.get('best_session_confidence')}); "
                f"{int(prior['recall'] * 100)}% of the paste's key terms are "
                f"already solved there — you are re-deriving solved ground.")
        else:
            add("- No prior thoughts match this problem's terms yet; "
                "text-diagnostics only.")
        if prior.get("last_cognitive"):
            cog = prior["last_cognitive"]
            add(f"- Last cognitive state you recorded: reasoning_mode="
                f"{cog.get('reasoning_mode')}, metacognitive_awareness="
                f"{cog.get('metacognitive_awareness')}, "
                f"breakthrough_likelihood="
                f"{cog.get('breakthrough_likelihood')}.")
        if prior.get("events_since_last_mcp_call") is not None and \
                prior["events_since_last_mcp_call"] >= 10:
            add(f"- Wire log: {prior['events_since_last_mcp_call']} events "
                f"since your last plan-audit-map tool call — you dropped "
                f"structured reasoning and started flailing.")
    else:
        add("- No memory DB yet (first run?) — text-diagnostics only.")
    add(f"- ESTIMATED improvement from re-engaging plan-audit-map NOW: "
        f"~{est['estimate']}%  [{est['work']}]")
    part_a = "\n".join(a)

    # ---- part B: the instruction (never truncated) --------------------------
    b: List[str] = []
    add = b.append
    add("")
    add("2) INSTRUCTION — call the plan-audit-map tool NOW (name may also be "
        "'code-reasoning'; args are snake_case):")
    seed = _seed_thought(paste, chunks, prior)
    add(json.dumps({
        "thought": seed,
        "thought_number": 1,
        "total_thoughts": 5,
        "next_thought_needed": True,
    }, ensure_ascii=False))
    if prior.get("best_session"):
        add(f"(If your client can resume, continue prior session "
            f"{prior['best_session']} — its history already covers this "
            f"problem; otherwise a fresh session is fine, memory will "
            f"recapture it.)")
    part_b = "\n".join(b)

    # ---- part C: feedback loop + footer --------------------------------------
    c: List[str] = ["", "3) Keep using the tool for every step; record results "
                     "with plan-audit-map-feedback (actual_outcome: success | "
                     "partial | failure) so the next intervention retrieves "
                     "YOUR fix, not generic advice.", "═" * 62]
    part_c = "\n".join(c)

    # ---- part 1: retrieved chunks — packed into whatever budget remains -----
    # Exact accounting: the must-have parts (A/B/C) are never cut; chunks get
    # the remainder, dropping to a titles-only line if that is all that fits.
    overhead = len(part_a) + len(part_b) + len(part_c)
    budget = cap - overhead - 100  # headers + join slack

    if budget >= 240 and chunks:
        d: List[str] = ["", "1) RETRIEVED CONTEXT (top match"
                        + ("es" if len(chunks) > 1 else "")
                        + " from the local skills folder):"]
        used = 0
        for i, ch in enumerate(chunks, 1):
            header = (f"--- [{i}] {ch['file']} :: {ch['title']} "
                      f"(similarity {ch['score']}) ---")
            room = budget - used - len(header) - 8
            body = ch["text"].strip()
            if room <= 140:
                if i == 1:  # always include the best chunk, trimmed hard
                    body = body[:max(140, room)] + "\n…[chunk trimmed]"
                else:
                    break
            elif len(body) > room:
                body = body[:room] + "\n…[chunk trimmed]"
            d.append(header)
            d.append(body)
            used += len(header) + len(body) + 8
        part_d = "\n".join(d)
    elif chunks:
        titles = "; ".join(f"[{i}] {ch['file']} :: {ch['title']} "
                           f"(sim {ch['score']})" for i, ch in enumerate(chunks, 1))
        part_d = ("\n1) RETRIEVED CONTEXT (titles only — raise "
                  "intervention.max_message_chars for full text): " + titles)
    else:
        part_d = ("\n1) RETRIEVED CONTEXT: no skill chunk cleared the "
                  "similarity threshold for this paste.")

    return "\n".join([part_a, part_d, part_b, part_c])


def _seed_thought(paste: str, chunks: List[Dict[str, Any]],
                  prior: Dict[str, Any]) -> str:
    """Pre-write the agent's first structured thought (compact, factual)."""
    diag = diagnose(paste)
    parts = [f"circular trace: {int(diag['rep5_ratio'] * 100)}% repeated "
             f"5-grams, {diag['retry_markers']} retry markers"]
    if prior.get("matched_thoughts"):
        parts.append(f"{prior['matched_thoughts']} prior plan-audit-map "
                     f"thought(s) already match "
                     f"(session {str(prior['best_session'])[:16]}…)")
    if chunks:
        parts.append(f"relevant procedure: '{chunks[0]['file']} :: "
                     f"{chunks[0]['title']}' (sim {chunks[0]['score']})")
    snippet = " ".join(paste.split())[:140]
    return ("Re-entering structured reasoning after circular native CoT. "
            + "; ".join(parts)
            + ". Failing trace begins: \"" + snippet + "…\". "
            "Step 1: state the single most likely root cause as a testable "
            "hypothesis, name the cheapest deterministic check that proves "
            "or kills it, and identify which prior thought or skill chunk "
            "already addresses it before inventing anything new.")
