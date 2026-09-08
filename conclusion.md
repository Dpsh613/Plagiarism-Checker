# PaperLens — Demo Test Conclusion

End-to-end test with real embeddings (`all-MiniLM-L6-v2`), real arXiv downloads,
and a draft of known composition. Every number below was measured, not assumed.

## 1. Demo setup

**Database (4 sources, 1861 chunks total):**

| # | Source | Size | Chunks indexed |
|---|--------|------|----------------|
| 1 | arXiv `1712.06027v2` — Lifshitz transitions in multi-band Hubbard models | 212 KB | 233 |
| 2 | arXiv `1108.1197v4` — Gauge-gravity duality / condensed matter | 881 KB | 633 |
| 3 | arXiv `1709.00466v1` — Cavity QED with hybrid nanocircuits | 2.6 MB | 983 |
| 4 | Local file `bose_hubbard_notes.txt` (Bose-Hubbard model notes) | ~2 KB | 12 |

**Draft under test (395 real words, known composition):**

| Passage | Type | Approx. words |
|---------|------|---------------|
| Gauge-gravity paragraph ×2 | Verbatim copy from source 2 | ~170 |
| Bose-Hubbard paragraph ×2 | Verbatim copy from source 4 | ~100 |
| Holography paragraph ×2 | Manual paraphrase of source 2 | ~80 |
| Blacksmith paragraph ×2 | Fully original | ~30 |
| Dispersion-relation sentences | Math-heavy (`E=mc2`, `t/U`, `and/or`) | ~15 |

So ~68% of the draft is word-for-word copied. Expected score: ~65–70%.

## 2. Results

**Analysis output:**

| Metric | Measured |
|--------|----------|
| `plagiarism_percent` | **44.56%** (expected ~68%) |
| `total_words` | 579 (real: 395 → **inflated +47%**) |
| `plagiarized_words` | 258 |
| Segments | 8× EXACT MATCH, 7× ORIGINAL, **0× PARAPHRASED** |
| Sources attributed | Only 2 of the copied sources found |

**Functionality checks (all via the real API):**

| Check | Result |
|-------|--------|
| Register → login, no email step | ✅ works |
| arXiv search + index | ✅ works, but slow, no progress feedback |
| Local file index | ✅ works (12 chunks) |
| List sources | ✅ works |
| Delete source | ✅ deletes, list confirms removal |
| Short/empty document | ⚠️ HTTP 200 `{"error": "No text extracted."}` — **crashes the frontend** (`analysis.segments` is undefined) |
| Wrong file type (`.exe`) | ✅ 400 rejected |
| Delete non-existent source | ❌ reports success (`Deleted vectors for nope.pdf`) |

## 3. Flaws that need fixing

### Phase 1 — Scoring correctness (the score misleads users today)
1. **Copy-paste under-scores (~45% for ~68% copied).** `checker.py`: numerator counts
   *unique* matched words per chunk (`set`), denominator counts *all* words, so
   natural prose with repeated vocabulary can never reach 100%.
   *Fix: map matching trigrams back to word positions and count occurrences.*
2. **Word counts inflated ~47%.** Overlapping sliding windows are summed instead of
   counting the document once (395 → 579; earlier probe: 300 → 465).
   *Fix: compute `total_words` from the raw document, not summed chunks.*
3. **Paraphrase detection is effectively dead.** A genuine rewrite sharing topic
   vocabulary scored zero (`PARAPHRASED` never triggered in this demo).
   *Fix: lower/secondary semantic-similarity signal per segment instead of relying
   solely on trigram coverage; tune thresholds on labeled data.*
4. **Math/content silently deleted.** `normalize_text` drops *entire lines*
   containing `= + / \` — the `E=mc2` / `and/or` sentences vanished from the
   analysis completely (verified absent from output segments).
   *Fix: replace with a symbol-density heuristic; never delete whole lines on a
   single character.*

### Phase 2 — Import robustness (works, but fragile and opaque)
5. **Large papers hit silent caps.** A 100+ page paper took 191s to extract, hit the
   100-page and 1500-chunk caps with no warning; each paper costs minutes of UI hang
   (sync work in async endpoints, no progress).
   *Fix: background indexing with progress + `truncated: true` flag in responses.*
6. **arXiv failures are cryptic.** Search 429-rate-limits with no backoff
   (reproduced); `.pdf`-suffixed URLs rejected (`allow_redirects=False`, reproduced
   with a live 301); killed runs leave orphan files in `dataset_pdfs/`.
   *Fix: same-host redirect following, retry with backoff, temp-file cleanup.*
7. **Sources are unidentifiable.** Indexed files are named by URL hash
   (`arxiv_7bd38f60….pdf`); the submitted paper title is ignored.
   *Fix: store title + URL in metadata, show titles in UI.*

### Phase 3 — Small correctness bugs
8. Short/empty docs return HTTP 200 `{"error": …}` → frontend crash.
   *Fix: return 400 with `detail`; guard `response.data.error` in UI.*
9. Deleting an unknown source returns success. *Fix: 404 when nothing matched.*
10. UI delete URL is not encoded — filenames with spaces break.
    *Fix: `encodeURIComponent(filename)`.*

## 4. What already works well
Auth (hashing, JWT+CSRF, rate limits), file-type/size guards, empty-database
analysis (0%, no crash), duplicate indexing (safe upsert), arXiv URL validation,
and the existing security test suite (5/5). The security posture is solid —
the gaps are scoring math, import robustness, and the small contract bugs above.

## 5. Phase 1 fixes — implemented and verified

| Fix | Change | Verified result |
|-----|--------|-----------------|
| Positional trigram counting | `checker.py`: matched words counted per occurrence, not per unique word | Identical text scores coverage 1.0 regardless of vocabulary repetition |
| True document word count | Denominator from raw page text, counted once | 402 vs 395 real words (was 579) |
| Semantic paraphrase fallback | Cosine-similarity signal (`PARAPHRASE_SIMILARITY = 0.80`, calibrated: medium rewrites ≈ 0.84, unrelated ≈ 0.0, topical-but-original < 0.5) | Light/medium rewrites flag; heavy rewrites remain a known limitation (need sentence-level alignment) |
| Math-line heuristic | `utils.py`: symbol-density (>30%) per line instead of deleting any line containing `= + / \` | `E=mc2`, `and/or`, `C++` prose survives; symbol-dense garble still removed |

**Demo re-run after fixes:** 44.56% → **70.9%** (expected ~68%), 8× EXACT MATCH,
heavy paraphrase honestly ORIGINAL, math content present in analysis.
New suite `tests/test_scoring.py`: 8/8 pass. Full suite: 13/13 pass.
## 6. Phase 2 fixes — implemented and verified

| Fix | Change | Verified result |
|-----|--------|-----------------|
| Truncation flags | `utils.py` extraction/windowing return `(data, info)`; `truncated` surfaces in analyze summary, index messages, and a UI badge | Demo re-run: `truncated: False` correctly; oversized txt now truncates with flag instead of "No text extracted" |
| Same-host redirects | `arxiv_manager.py` follows up to 3 hops pinned to `arxiv.org`/`export.arxiv.org` | Previously-rejected versioned `.pdf` URL (live 301) now downloads; evil-host/abs-URL targets rejected (unit-tested) |
| 429/5xx backoff | Search retries ×3, download retries ×2 with exponential backoff; 502 message names rate-limiting | Search wrapper preserves behavior; download failure message tells user to retry |
| Orphan temp sweep | `cleanup_stale_temp_files()` at backend start removes `arxiv_*.pdf` older than 24h | Unit-tested (stale removed, fresh kept) |
| Readable source titles | Title + URL stored in chunk metadata; `/database/files` returns `{filename, title}`; UI shows titles with filename tooltip; match overview shows titles | Live import stores/displays real titles (legacy chunks fall back to filename) |

**Regression check:** demo re-run scores identically (70.9%), full suite 22/22 pass
(5 security + 8 scoring + 9 robustness), frontend eslint clean.
Remaining future work (out of scope): true background indexing jobs with progress
streaming, and sentence-level paraphrase alignment.

## 7. Reliability round — implemented and verified

| Fix | Change | Verified result |
|-----|--------|-----------------|
| Non-blocking heavy work | `api.py`: embedding/index/analyze/search run via `run_in_threadpool` | `/health/deep` answers in ~3.6s mid-load (previously would hang) |
| Backpressure | `MAX_HEAVY_JOBS` semaphore (default 2); saturated jobs get 503 + `Retry-After` | 3 concurrent analyzes → 2×200 + 1×503; unit-tested |
| SQLite hardening | WAL + `busy_timeout=5000` on `users.sqlite` | Concurrent register/login/index bursts: zero `database is locked` errors |
| Loud DB errors | `get_all_indexed_sources` failure → logged + 503 (never phantom-empty) | Contract covered by `/database/files` handler |
| Crash-safety | `temp_uploads/` startup sweep; global handler returns generic 500s, tracebacks stay server-side | Unknown/novel failures leak no paths |
| Deep health | `/health/deep`: model, vector DB heartbeat, users DB, disk free | Live: all green under load; degraded → 503 |
| Quotas | `MAX_VECTORS_PER_USER` (default 10k) enforced with clear message | Unit-tested rejection path |
| Honest UI | Global 30s axios timeout (240s analyze, 600s index), cancel button, 503/`Retry-After` and backend-error messages, `{"error"}` responses shown instead of crashing | eslint clean |

**Feature checklist (post-round):** register ✅ / login ✅ / analyze ✅ /
list sources ✅ / delete source ✅ / arXiv search ✅ / arXiv index ✅ /
validation rejections ✅ / concurrent use ✅ (bounded) / error UX ✅.
**Full suite: 25/25 pass** (5 security + 8 scoring + 12 robustness).
Known remaining limits: heavy paraphrase, true background jobs, account
deletion, response pagination — queued for the next round.

## 8. Current system architecture

### 8.1 Deployment shape
- **Frontend:** static Vite + React + Tailwind build (`ui/`, `vite.config.js`), served
  separately (e.g. Vercel). It talks to the backend only through `VITE_API_BASE_URL`
  (`App.jsx`), sending the JWT as `Authorization: Bearer` plus `X-CSRF-Token` on
  mutations. No dev proxy is configured — the CORS allow-list (`FRONTEND_URLS` in
  `api.py`) is the only browser bridge.
- **Backend:** one FastAPI app (`api.py`) on one uvicorn process. The `Procfile`
  runs `uvicorn api:app` with no `--workers` flag, so production today is a
  **single worker**: one event loop, one ONNX model in RAM, one Chroma client.
- **Secrets/config:** environment variables only (`.env` file is gitignored and
  local-only; production values live in the host dashboard). Production hardens
  itself at import: HTTPS-only origins, `Secure` cookies, mandatory
  `JWT_SECRET_KEY` (`api.py:30-55`).

### 8.2 Local desktop vs deployed — what actually differs
The code is identical; the environment changes everything:

| Aspect | Local desktop | Deployed (single container) |
|--------|---------------|-----------------------------|
| State storage | `./my_plagiarism_db`, `users.sqlite`, `dataset_pdfs/`, `temp_uploads/` persist on your disk | Same relative paths — **if the host disk is ephemeral (e.g. Render free tier), every restart/redeploy wipes vector DB, user accounts, and temp files** |
| First request | Model downloads once (~90MB), then cached in temp dir | Same, but the cold download happens on a stranger's first click, behind a proxy timeout |
| Concurrency | One user, no contention | All users share 1 worker, 1 model, 1 Chroma SQLite file |
| Cookies | `SameSite=lax`, non-secure works | Cross-site frontend→backend needs `COOKIE_SECURE=true` + `SameSite=none`, or logins silently fail |
| Observability | You watch the console | Only Render logs + `/health` + `/health/deep` |

The ephemeral-disk row is the most dangerous difference: **verify that
`my_plagiarism_db/` and `users.sqlite` live on a persistent disk/volume —
otherwise a redeploy deletes every user's library and account**. If the host
cannot provide one, the next architecture step is Postgres (users) + Chroma
server mode or pgvector (vectors) + object storage (files).

### 8.3 How papers/files are stored, indexed, and accessed
**Analyze path** (`POST /analyze`): streamed upload (5MB cap, magic-byte checked)
→ `temp_uploads/` → pdfplumber text extraction (10% header/footer crop,
100-page / 500k-char caps, all flagged) → overlapping 40-word windows
(15-word overlap, 1500 cap, flagged) → MiniLM-L6-v2 embeddings (384-dim) →
per-chunk top-3 cosine query against the user's collection → trigram coverage
with occurrence counting + similarity fallback → one JSON report. The temp file
is deleted in a `finally` block; stale leftovers are swept at boot.

**Index path** (arXiv): metadata search (retries + backoff) → same-host
redirect resolution → bounded 10MB download → `dataset_pdfs/` temp →
identical extract/embed pipeline → `collection.add` with metadata
`{source, title, url, page}` and deterministic ids `{filename}_{i}`.
Old chunks under the same filename are upserted, so re-indexing is safe.

**Read path:** `GET /database/files` returns `{filename, title}` pairs;
`DELETE` removes by `source` metadata filter.

### 8.4 What the system is best at
Private, per-user plagiarism pre-checking against a self-curated library:
calibrated copy detection (70.9% measured on a ~68%-copied draft), honest word
counts and truncation flags, strict upload validation, JWT+CSRF auth with rate
limits, readable paper titles, and backpressure instead of silent hangs.

### 8.5 Multi-user handling and data isolation
- Identity: bcrypt-hashed passwords (12 rounds), 8-hour JWT (`sub` = integer
  user id) + per-session CSRF token; every data route resolves `user_id` from
  the token server-side — clients can never request another user's id.
- Isolation unit: one Chroma collection per user (`user_{id}_docs`). Separation
  is by **naming convention only** — correct as long as token plumbing holds;
  there are no per-collection keys or audit logs (defense in depth: missing).
- Fairness: one global 2-slot heavy-job semaphore (`MAX_HEAVY_JOBS`) is shared
  FIFO-ish across users; per-user vector quota (`MAX_VECTORS_PER_USER`, 10k)
  caps library size; slowapi rate limits are per-IP, so users behind one NAT
  (a classroom) share a bucket and can throttle each other.
- Gaps: no account deletion (collections/rows accumulate forever), no per-user
  usage metering, no admin view.

### 8.6 Current limitations and weaknesses
Scoring: heavy paraphrase, translation, and cross-language copying are missed
(English-centric MiniLM + trigram overlap); thresholds (`0.60/0.20/0.80`) are
tuned on one draft with no evaluation harness. Scale: single worker, single
SQLite-backed vector store, in-process threadpool instead of a real job queue,
~10-minute worst-case jobs behind proxy timeouts, multi-MB unpaginated JSON
responses rendered without virtualization. Operations: logs + two health
endpoints are the whole observability story; no backups, no metrics, no alerting.

### 8.7 How to scale for more users and larger datasets
1. **Now (no new infra):** persistent disk for `my_plagiarism_db/` +
   `users.sqlite`; raise `MAX_HEAVY_JOBS` only with a bigger instance.
2. **Next:** managed Postgres (users) + Chroma server mode or pgvector (vectors)
   + object storage (uploads/PDFs); RQ/Redis or Celery job queue with persistent
   jobs, retries, and progress streaming; multi-worker uvicorn behind the queue.
3. **Later:** per-user metering and quotas on analyses, paginated/streamed
   reports, virtualized results UI, threshold evaluation harness, metrics/alerts.

### 8.8 Technical stack and responsibilities
| Part | Role |
|------|------|
| React + Vite + Tailwind + axios + Lucide (`ui/`) | Upload/analyze/database UI, auth screens, score visualization |
| FastAPI + uvicorn (`api.py`, `Procfile`) | Routing, JWT/CSRF auth, rate limits, backpressure, health |
| SQLite + WAL (`auth_db.py`, `users.sqlite`) | Accounts and password hashes |
| ChromaDB (`db_manager.py`, `my_plagiarism_db/`) | Per-user vector collections + source metadata |
| fastembed MiniLM-L6-v2 (`model_manager.py`) | 384-dim embeddings for retrieval + similarity fallback |
| pdfplumber (`utils.py`) | PDF text extraction, header/footer crop, sliding windows |
| `arxiv` lib + requests (`arxiv_manager.py`) | Search, redirect-safe bounded download, retries |
| PyJWT + bcrypt + slowapi | Sessions, password hashing, brute-force protection |

### 8.9 Bottlenecks and failure points to watch
1. Single uvicorn worker — one crash takes everyone down (SPOF).
2. Chroma's SQLite lock under concurrent writes — bounded today by the 2-slot
   semaphore; the first thing to saturate past tens of users.
3. ONNX CPU inference — embedding throughput caps analyses/minute per instance.
4. 1500-chunk jobs (minutes each) vs proxy/client timeouts — expect retries that
   amplify load; the 503 backpressure is the relief valve, not a fix.
5. Ephemeral disk — silent total data loss on redeploy if unaddressed.
6. First-run model download — cold starts are minutes long with no progress signal.

## 9. Durable data on ephemeral hosting (free tier)

`users.sqlite` + `my_plagiarism_db/` are now snapshot to S3-compatible object
storage (`storage_sync.py`): restore on boot when local state is empty,
debounced background backup after every index/delete, final flush on graceful
shutdown. Vector-store writes hold a shared lock so backups never zip a
half-written store. All paths honor `CHECKMATE_DATA_DIR`; everything is a
no-op without snapshot env vars. Verified: snapshot roundtrip, traversal
rejection, and no-op behavior unit-tested (`tests/test_persistence.py`, 5/5).
Requires free R2-style bucket + Render env vars (see README section 1).
Transient files need no backup: uploads are deleted after analysis and arXiv
PDFs are re-downloadable. Full suite after this change: 30/30 pass.

