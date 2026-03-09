# Domain Pitfalls

**Domain:** Production ML pipeline — transcription + OCR + LLM inference in a Celery/FastAPI/Docker backend
**Researched:** 2026-03-09
**Confidence:** HIGH for pitfalls directly observed in prototype code; MEDIUM for Docker/runtime behaviour patterns; noted where each applies

---

## Critical Pitfalls

Mistakes that cause rewrites, job failures that are invisible to callers, or container startup failures in production.

---

### Pitfall 1: EasyOCR Downloads Models at Runtime into a Non-Persistent Container Layer

**What goes wrong:**
EasyOCR downloads CRAFT (text detection) and language recognition model weights the first time `easyocr.Reader(...)` is called. By default the download target is `~/.EasyOCR/model/` — which inside a Docker container resolves to `/root/.EasyOCR/model/`. This directory is inside the container's writable layer, not on any mounted volume. The result: every container restart triggers a fresh model download from GitHub releases, taking 30–90 seconds and requiring internet access from within the container.

**Why it happens:**
The prototype's lazy-load pattern (`_get_reader()` defers `import easyocr` until first call) was correct for a Streamlit dev environment where models are cached in the developer's home directory between runs. In Docker, the home directory is ephemeral by default.

**Observed in prototype:**
`text_extractor.py` line 38: `self._reader = easyocr.Reader(self.languages, gpu=self.gpu)`. The lazy load is deliberately deferred but there is no pre-download or volume mount strategy.

**Consequences:**
- First job after container restart fails or takes 90+ seconds with no user feedback
- Container fails entirely if it has no outbound internet access (production policy at some orgs)
- Multiple concurrent worker containers each download independently, amplifying the problem
- Burst cold-starts (e.g., after a deploy) produce a thundering-herd of model downloads

**Prevention:**
Three-part solution:
1. Set the model directory to a named Docker volume: pass `model_storage_directory` to `easyocr.Reader()` pointing to a path under `/app/models/` (the same volume mechanism already used for video storage).
2. Pre-download during Docker image build: add a `RUN python -c "import easyocr; easyocr.Reader(['en','es'], gpu=False)"` layer in the Dockerfile so models are baked into the image.
3. Never rely on `~/.EasyOCR/` inside a container.

**Detection:**
Worker logs show `Downloading detection model` or `Downloading recognition model` after container start. Job latency spikes on first post-restart job. Jobs time out if internet is blocked.

---

### Pitfall 2: faster-whisper Loads the Model Inside Each Celery Task — One Load Per Job

**What goes wrong:**
The prototype calls `WhisperModel("base", device="cpu", compute_type="int8")` inside `_transcribe_local_faster_whisper()`, which is called from inside the Celery task on every invocation. This means every job loads the model from disk into RAM, runs inference, and then the model object is garbage collected when the function returns. For the "base" model this is ~150MB RAM allocation + ~2–4 seconds model load time per job. For "medium" or "large" models the cost is proportionally worse.

**Why it happens:**
In the prototype (Streamlit), the model load happens once per session because the Streamlit process persists between user interactions and Python module-level state is preserved. Celery tasks are functions — they have no persistent state between invocations unless explicitly managed.

**Observed in prototype:**
`transcription.py` line 60: `model = WhisperModel("base", device="cpu", compute_type="int8")` is a local variable inside `_transcribe_local_faster_whisper`. No module-level singleton.

**Consequences:**
- 2–4 seconds of dead time added to every job, before any audio is processed
- RAM spikes on every task invocation, which can cause OOM kills in a memory-constrained container
- Multiple concurrent tasks each load a separate model copy simultaneously — RAM usage is N × model_size for N concurrent tasks
- Model load time is not reflected in job latency metrics, making profiling misleading

**Prevention:**
Use a Celery worker-level singleton pattern. At module level in `tasks.py` (or a separate `models.py`), define `_whisper_model: WhisperModel | None = None`. Load on first use (lazy, but cached) or use Celery's `worker_process_init` signal to load eagerly when the worker process starts. The model instance is then reused for all tasks within that worker process.

**Detection:**
Profile task execution: if transcription time has a consistent 2–4 second floor that doesn't shrink with repeated calls, the model is reloading. Worker memory grows then drops sharply around each task.

---

### Pitfall 3: LLM Provider Abstraction Breaks on Response Shape Differences

**What goes wrong:**
The prototype has three separate functions (`analyze`, `analyze2`, `analyze_local_mistral`) that share `_extract_json_block` for parsing but diverge in how they call the provider. The production port is planned to unify these behind a pluggable interface. The danger is assuming OpenAI's response shape is universal. Key differences:

- **OpenAI / Azure**: `resp.choices[0].message.content` — a string
- **Ollama**: `data["message"]["content"]` — accessed from a raw `dict` after `r.json()`, not an SDK object
- **Anthropic Claude**: `resp.content[0].text` — a completely different path; `resp.content` is a list of content blocks, not `choices`

Attempting to wrap all three behind `provider.complete(prompt) -> str` is the right instinct but the implementation must correctly normalize before returning. Any missed edge case silently returns `""` or `None`, which then hits `_extract_json_block` and produces `CANNOT_RECOGNIZE` with no logged error.

**Observed in prototype:**
`analysis.py` line 218: `content = data.get("message", {}).get("content", "")` — the Ollama path already handles missing keys gracefully by defaulting to empty string, meaning a misconfigured Ollama response silently produces a `CANNOT_RECOGNIZE` result with no error raised. Azure path (`analyze2`) calls `st.error(...)` on exception but returns `CANNOT_RECOGNIZE` — the caller never knows the difference between "video has unrecognizable content" and "API call failed".

**Consequences:**
- Provider configuration mistakes produce valid-looking results (`CANNOT_RECOGNIZE`) rather than errors
- Silent fallback to empty strings makes provider errors invisible in DB — job shows `SUCCESS` but label is always `CANNOT_RECOGNIZE`
- Adding a new provider (Anthropic, Gemini) requires reading SDK docs carefully; wrong content extraction path breaks silently

**Prevention:**
Define a `ProviderResult` typed dataclass with `raw_text: str` and raise `ProviderError` (not return `CANNOT_RECOGNIZE`) when the API call fails. Reserve `CANNOT_RECOGNIZE` for classification results, not infrastructure errors. Each provider adapter is responsible for extracting `raw_text` and raising on failure. `_extract_json_block` receives `raw_text` only after a successful API call.

**Detection:**
If job `status=SUCCESS` but `label=CANNOT_RECOGNIZE` is unusually frequent, check whether it is a classification result or a masked provider error. Add a `error_message` field to the Result model to distinguish the two cases.

---

### Pitfall 4: JSON Parsing Fails on LLM Output That Works in Prototype Testing

**What goes wrong:**
The prototype's `_extract_json_block` handles three known failure modes: markdown code fences (` ```json `), non-string input, and no JSON object found. It does not handle several failure modes that appear in production volumes:

1. **Nested JSON with escaped quotes**: LLMs sometimes include quoted text inside `explanation` that breaks `json.loads` with an unclosed string literal. `re.finditer(r"\{.*\}", cleaned, flags=re.DOTALL)` greedily matches the outer braces, but the content may contain unescaped quotes from the transcript.
2. **Trailing commas**: Many LLMs (especially Ollama local models) emit `{"key": "value",}` — valid in JS, invalid in Python's `json.loads`.
3. **Unicode escape sequences**: Transcripts of multilingual videos pass through the prompt and may produce `\u0000` null bytes or unusual Unicode that the JSON parser rejects.
4. **Response truncated at token limit**: The model cuts off mid-JSON. `re.finditer` finds no complete `{...}` block, returns `CANNOT_RECOGNIZE`. No error is logged.
5. **Multiple JSON objects in response**: The prototype takes the first match, but if the LLM emits a "reasoning" JSON blob before the answer JSON, the wrong object is parsed.

**Observed in prototype:**
`analysis.py` lines 55–81: The `for match in re.finditer(...)` loop tries each match in order and catches `Exception`, continuing to the next match. This handles some cases but the loop processes all `{.*}` patterns including any that are not the answer object. The regex is DOTALL but greedy — `{.*}` matches from the first `{` to the last `}` in the entire response, which on long responses can include multiple JSON objects smeared together.

**Consequences:**
- Sporadic `CANNOT_RECOGNIZE` results on real-world inputs that passed dev testing
- Production error rate higher than prototype error rate because prompt + transcript combinations are more diverse
- Silent: the caller gets a valid-looking dict, not an exception

**Prevention:**
Replace the regex-based extraction with a more robust approach:
- Strip code fences first (the prototype does this correctly)
- Use `json.loads` on the whole stripped string first — if it succeeds, done
- Fall back to `re.search(r'\{[^{}]*\}', ...)` for flat objects, then try `json5` or `demjson3` as a last resort for trailing-comma tolerance
- Log the raw LLM response at DEBUG level whenever `_extract_json_block` returns the fallback dict, so failures are visible
- Set `max_tokens` on the API call to ensure the response is never truncated mid-JSON

**Detection:**
Log every call to `_extract_json_block` that hits the fallback return. Track `CANNOT_RECOGNIZE` rate by provider and model — a spike on a specific provider means parsing is failing, not that content is unrecognizable.

---

### Pitfall 5: Celery Workers and ML Model Instances Do Not Compose Safely with Fork-Based Concurrency

**What goes wrong:**
Celery's default worker concurrency model on Linux is `prefork` (multiprocessing). If a model is loaded at worker startup (module level or via `worker_process_init`) and the worker then forks child processes for concurrency, the model's internal state — CUDA contexts, file descriptors, memory-mapped weight files, thread pools — is forked into each child. This produces:
- CTranslate2 (faster-whisper backend): uses OpenMP thread pools that are unsafe to fork; may deadlock
- EasyOCR: uses torch under the hood; PyTorch CUDA contexts cannot be forked safely; even CPU mode uses internal thread state
- OpenCV: generally fork-safe for CPU operations, but some builds with OpenCL can deadlock

**Why it happens:**
The prototype runs everything in a single process (Streamlit). There is no fork. The production system will have `--concurrency N` workers where N > 1, and the default is the CPU count.

**Consequences:**
- Deadlocks on transcription or OCR calls in concurrent workers — hangs indefinitely, job never completes
- Corrupted inference results when two forked processes share internal model state
- Difficult to reproduce locally (single-core dev environments may not trigger fork)

**Prevention:**
Use `--pool=solo` for the worker during development to eliminate concurrency and isolate this class of bug. For production concurrency, use `--pool=threads` (thread-based, avoids fork) or Celery's `gevent` pool with CPU-bound tasks pinned to separate queue workers. Alternatively, set `worker_max_tasks_per_child=1` so each task spawns a fresh process — expensive but safe. The cleanest solution is to load models inside the task (accepting the reload cost) and run one worker per process with `--concurrency=1 --autoscale`.

**Detection:**
Worker hangs with no log output after accepting a task. CPU shows one worker pegged at 100%, others at 0%. `celery inspect active` shows the task running for hours.

---

### Pitfall 6: Streamlit Removal Is Not Just Removing `import streamlit as st`

**What goes wrong:**
The prototype's `transcription.py` uses `st.error()`, `st.warning()`, `st.info()` as the error reporting mechanism throughout — 7 call sites. The analysis module (`analysis.py`) calls `st.error(f"Analysis failed: {e}")` in both `analyze` and `analyze2` error handlers, and `analyze_local_mistral` calls `st.error` in two catch blocks. Simply removing these `import` statements causes `NameError: name 'st' is not defined` at runtime. Commenting them out silently swallows all errors.

**Observed in prototype:**
`transcription.py` line 7: `import streamlit as st`. Used in lines 53, 113, 144, 158, and 162 — all error/warning handlers.
`analysis.py` line 6: `import streamlit as st`. Used in lines 136–137, 169–170, 224–225 — all error paths.

**Consequences:**
- If `import streamlit` is removed without replacing call sites, the module raises `NameError` on first error condition
- If call sites are replaced with `pass` or `return`, all errors are silently dropped
- Error information that was shown to the user is now thrown away, making `CANNOT_RECOGNIZE` results undiagnosable
- The `_token_limit_warning` function in `analysis.py` takes a `container` argument that is a Streamlit status container — callers passing `None` crash with `AttributeError: 'NoneType' has no attribute 'update'`

**Prevention:**
Replace every `st.error()` / `st.warning()` call with `logging.error()` / `logging.warning()` using Python's standard logging module. Replace `container.update(...)` calls with structured log entries. Remove the `container` parameter from the `analyze` function signature entirely — the production interface should not accept UI objects. Audit with `grep -r "import streamlit" backend/` as a CI check.

**Detection:**
Add a CI lint step: `python -c "import ast; ast.parse(open('file.py').read())"` won't catch this. Use `grep -r "streamlit" backend/` and fail the build if any match is found.

---

## Moderate Pitfalls

---

### Pitfall 7: EasyOCR Frame Extraction Loads All Frames into RAM Before Processing

**What goes wrong:**
`text_extractor.py`'s `extract_frames()` method returns a `List[np.ndarray]` — all sampled frames held in memory simultaneously. For a 60-second TikTok at 30fps sampled at 1fps, this is 60 frames. Each frame at 1080p is `1920 × 1080 × 3 bytes ≈ 6MB`. Total: ~360MB of frame data in the Celery worker's RAM before OCR begins. In a constrained container (e.g., 1GB RAM limit), this can trigger OOM before any OCR runs.

**Observed in prototype:**
`text_extractor.py` lines 53–73: `extract_frames` builds `frames = []` and appends every sampled frame before returning.

**Prevention:**
Refactor to a generator that yields one frame at a time, processes it, and discards it before reading the next. `cv2.VideoCapture` already supports this access pattern. The `extract_text_from_video` method iterates frames in a loop — converting to a generator is a mechanical change with large memory benefit.

---

### Pitfall 8: Confidence Score Semantics Are Not Validated Against the Label Schema

**What goes wrong:**
The `_extract_json_block` function does `float(obj.get("confidence", 0.5))` with no range validation. An LLM can return `"confidence": 1.5`, `"confidence": -0.2`, or `"confidence": "high"` (string). The first two store invalid floats in the DB; the third raises `ValueError` inside `_extract_json_block` which is caught by the bare `except Exception: continue`, silently discarding the parse result and returning `CANNOT_RECOGNIZE`.

**Prevention:**
Add explicit validation: `conf = max(0.0, min(1.0, float(obj.get("confidence", 0.5))))` with a `try/except ValueError` that defaults to `0.5` rather than aborting the parse. Add a DB-level constraint: `CheckConstraint("confidence >= 0 AND confidence <= 1")` on the Result model.

---

### Pitfall 9: OpenAI Whisper API Has a 25MB File Size Limit

**What goes wrong:**
The prototype's `_transcribe_openai` function passes the video file directly to `client.audio.transcriptions.create`. The OpenAI Whisper API enforces a 25MB file size limit and rejects larger files with a 413 error. The prototype handles this by auto-splitting files above 20MB (the `transcriber` function in `transcription.py`). The production port must preserve this split logic — if it is not carried over, any video over 25MB causes a hard API error.

**Observed in prototype:**
`transcription.py` lines 141–148: The 20MB threshold split. This is in `transcriber()` which is the Streamlit entry point. The cleaner `transcribe2()` (which will be the basis for the production port) does NOT include splitting logic.

**Prevention:**
Port the size-check and splitting logic into the production extraction module, not just the `_transcribe_openai` backend. The split must happen before the file is handed to any backend. Use a `StorageService.prepare_for_transcription(path) -> list[path]` that returns a list of chunk paths (or the original if under 25MB).

---

### Pitfall 10: Ollama URL is Hardcoded to localhost

**What goes wrong:**
`analysis.py` line 203: `url = "http://localhost:11434/api/chat"`. In the Docker-compose environment, Ollama (if added as a service) would be reachable at `http://ollama:11434`, not `localhost`. This URL is embedded directly in the function body with no config lookup.

**Prevention:**
Pull the Ollama base URL from `settings.OLLAMA_BASE_URL` (add to config.py). Default to `http://localhost:11434` for local non-Docker dev. Use `http://ollama:11434` for Docker deployments.

---

### Pitfall 11: No Retry Logic on Transient Provider Failures

**What goes wrong:**
All three provider functions in `analysis.py` have a single `try/except` that catches all exceptions and returns `CANNOT_RECOGNIZE`. Network timeouts, rate limit responses (429), and transient 500 errors from the provider are treated identically to permanent failures. A job that could succeed on retry is permanently marked `FAILED` or worse, `SUCCESS` with `CANNOT_RECOGNIZE` label.

**Prevention:**
Add `tenacity` retry decorator to each provider call with exponential backoff for `429` and `5xx` status codes. Distinguish between retryable errors (network timeout, rate limit) and permanent errors (invalid API key, model not found). Use `max_attempts=3` and `wait_exponential_multiplier=1` as a reasonable default. Celery also has built-in task retry (`self.retry(exc=e, countdown=60)`).

---

## Minor Pitfalls

---

### Pitfall 12: EasyOCR Confidence Threshold Applied Inconsistently

**What goes wrong:**
`text_extractor.py` applies confidence filtering twice: once at `conf > 0.3` inside `extract_text_from_frame` (lines 88–89), and once at `conf >= min_confidence` (default `0.5`) in `extract_text_from_video` (lines 120–121). The first filter is always active at 0.3 regardless of the caller's `min_confidence` argument. A caller passing `min_confidence=0.8` still gets all detections above 0.3, just filtered again at 0.8 — the 0.3 filter is redundant but not harmful. However, if the 0.3 threshold in `extract_text_from_frame` is ever changed, behavior changes for all callers silently.

**Prevention:**
Remove the hardcoded 0.3 filter from `extract_text_from_frame` and apply a single threshold in `extract_text_from_video` only. Make `min_confidence` the single source of truth.

---

### Pitfall 13: `unique_text` Is Order-Non-Deterministic

**What goes wrong:**
`text_extractor.py` line 132: `unique_text = list(set(all_text_list))`. Python `set` does not preserve insertion order. The same video processed twice may return different `unique_text` orderings. This is harmless for the multimodal fusion input (order rarely matters for LLM context) but makes test assertions using exact list equality fragile.

**Prevention:**
Use `list(dict.fromkeys(all_text_list))` which preserves first-seen order while deduplicating. More predictable, equally fast.

---

### Pitfall 14: `time_taken_secs` Field Leaks into the DB Result Model If Not Stripped

**What goes wrong:**
The prototype's `analyze` / `analyze2` / `analyze_local_mistral` functions all add `result["time_taken_secs"]` to the returned dict. This is a UI convenience field. If the production port passes this dict directly to the `Result` ORM model constructor (e.g., `Result(**result)`), it causes `TypeError: unexpected keyword argument 'time_taken_secs'` unless the field is explicitly declared on the model.

**Prevention:**
Define a `ClassificationResult` Pydantic model for the output of the inference layer with only the canonical fields: `label`, `confidence`, `explanation`, `evidence_sentences`, `keywords`. Strip timing fields before returning from the provider interface. Latency should be captured by the Celery task layer using `time.time()` around the inference call, not inside the provider function.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Port OCR module | EasyOCR model not found in container | Pre-download in Dockerfile; mount model dir to persistent volume |
| Port OCR module | OOM on long videos | Convert frame list to generator; cap max frames sampled |
| Port transcription | Model reload on every task | Worker-level singleton or `worker_process_init` eager load |
| Port transcription | Videos over 25MB crash OpenAI backend | Preserve split logic from `transcriber()`; apply in pipeline layer, not backend |
| Port inference | `st.error` calls cause NameError | Audit and replace every Streamlit call before running; add CI grep check |
| Port inference | CANNOT_RECOGNIZE masks provider errors | Separate infrastructure errors from classification fallback in Result model |
| Wire pipeline | Fork-unsafe model state with Celery prefork | Use `--pool=solo` in dev; validate concurrency config before enabling `--concurrency>1` |
| Wire pipeline | Race condition on job status update | Already identified in CONCERNS.md; pre-generate Celery task ID before first DB commit |
| Add Result model | `time_taken_secs` from prototype dict | Strip via Pydantic model before ORM construction |
| LLM provider abstraction | Hardcoded Ollama localhost | Pull from `settings.OLLAMA_BASE_URL`; document Docker service name vs localhost |
| Testing ML pipeline | LLM mocking returns wrong shape | Mock at provider interface boundary, not at HTTP level; return typed `ClassificationResult` objects |
| Testing ML pipeline | EasyOCR/Whisper hard to mock | Use dependency injection; pass model/reader as constructor args so tests can inject stubs |

---

## Testing ML Pipelines: Specific Gotchas

This section expands on the testing dimension because the prototype has zero tests and the production port must build them from scratch.

### What Makes Mocking LLM Calls Hard

**The raw string problem.** LLM responses are strings. Mocks that return a perfectly-formed JSON string miss the real failure modes — truncated responses, trailing commas, Unicode edge cases. Tests should include a library of deliberately malformed LLM responses as fixtures and assert that the parser handles each without crashing.

**The `container` parameter anti-pattern.** The prototype's `analyze()` function signature is `analyze(transcript, model, client, container)` where `container` is a Streamlit status object. Tests that mock `client` still must pass something for `container`. The production interface must remove this parameter entirely — tests only need to care about `(transcript, model, provider) -> ClassificationResult`.

**Provider SDK version drift.** Mocking `openai.Client` directly is fragile — the SDK response schema changed between v0.x and v1.x. Mock at your own interface boundary (the `analyze(transcript) -> ClassificationResult` function), not at the SDK call. Tests should not know whether the underlying provider is OpenAI or Anthropic.

**Celery task testing.** Call `process_video_task.apply(args=[job_id])` in tests — this runs the task synchronously in-process without a broker, using `CELERY_TASK_ALWAYS_EAGER=True` (or the `eager_mode` pytest fixture). Do not try to spin up a real Redis broker in unit tests.

**EasyOCR/Whisper in unit tests.** These load large model files. Unit tests must not import the real models. The recommended pattern is to make the extractor classes accept the model/reader as a constructor parameter. Tests inject a mock reader that returns pre-canned output. Integration tests (marked `@pytest.mark.integration`) spin up the real models in CI with a real video file.

**Confidence:** HIGH for the Streamlit removal pitfalls (directly observed in code). HIGH for the JSON parsing pitfalls (directly observed in `_extract_json_block`). MEDIUM for the Celery fork/memory pitfalls (well-established patterns, not directly observable in current stub code). MEDIUM for EasyOCR Docker behaviour (based on library internals, no direct runtime observation in this environment).

---

## Sources

- Direct code analysis: `D:\Python files\tiktok-2026-01-29\pages\processes\analysis.py` (read 2026-03-09)
- Direct code analysis: `D:\Python files\tiktok-2026-01-29\pages\processes\transcription.py` (read 2026-03-09)
- Direct code analysis: `D:\Python files\tiktok-2026-01-29\pages\processes\ocr\text_extractor.py` (read 2026-03-09)
- Codebase concerns audit: `D:\Python files\who-infodemic-monitor\.planning\codebase\CONCERNS.md` (read 2026-03-09)
- Project requirements: `D:\Python files\who-infodemic-monitor\.planning\PROJECT.md` (read 2026-03-09)
- EasyOCR library internals: model_storage_directory parameter, known Docker behaviour (HIGH confidence — well-documented in EasyOCR README and GitHub issues)
- faster-whisper / CTranslate2: model loading patterns (MEDIUM confidence — based on library documentation and known Celery/fork interaction patterns)
- Celery prefork pool + native thread libraries: documented incompatibility pattern (MEDIUM confidence — Celery documentation and known Python multiprocessing constraints)
- OpenAI Whisper API 25MB limit: (HIGH confidence — documented in OpenAI API reference)
