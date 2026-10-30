# WhyChain: submission draft for the Nebius x NVIDIA Global AI Hackathon

Paste-ready text for the Devpost fields. Track: **Best Apps and Agents**. Repository: https://github.com/Dakshhhhh-ops/whychain-nebius. Links to fill in: demo URL, video.

## Project name and tagline

**WhyChain**: an agent that explains *why* a supply-chain problem happened, with the evidence to prove it. Built on NVIDIA Nemotron, served by Nebius Token Factory, hosted on Nebius AI Cloud.

## Inspiration

When deliveries go late, the dashboard says *that* it happened, never *why*. The answer is scattered: order timestamps in one system, seller hand-overs in another, customer reviews in a third, and the news of the day (a strike, a storm, a holiday) somewhere else. An analyst needs half a day to stitch it together, and the obvious story is often wrong: in March 2018 Brazil's postal workers went on strike, and the strike gets the blame, but the data says lateness was already high before it began. We wanted an agent that does that half-day of work in minutes, refuses to blame the red herring, and shows every number's working.

## What it does

Ask in plain English, for example "Why did late deliveries jump to 19% for orders placed in March 2018?". WhyChain investigates across six source systems (order management, seller platform, payments, reviews, an external-events feed and news briefs) and returns a brief:

- **what happened, in money**: 1,328 of 7,003 orders late (19.0% against a normal 5.6%), worth R$ 187,138, rated 2.1 stars against 4.2;
- **why**, each cause with its share: carrier transit got slower (72.7% of the rise), promised delivery windows got shorter (26.7%);
- **what it ruled out and why**: the Correios strike, Carnival, a Rio storm, a volume surge, seller hand-over, data artefacts;
- **where it sits** (Rio de Janeiro first), with a one-click "ask why next";
- **what to do**, sized from the data (per-state promise buffers), with risky actions held for a manager's approval. On the simulated distributor it also solves a proven-optimal stock transfer (a linear program with a duality certificate) and, once approved, drafts the transfer order and the supplier email.

Every number in the brief opens the SQL and the table it came from. A preliminary answer, computed by code, appears in seconds; the full brief, with the news quoted word for word, follows in one to two minutes.

## How we built it

- **NVIDIA Nemotron on Nebius Token Factory for every model call.** One OpenAI-compatible client, pointed at Token Factory, with agents asking for a *role* rather than a model: **Nemotron 3 Super** (`nvidia/nemotron-3-super-120b-a12b`) with reasoning off, in JSON mode, for the Document Analyst, Data Scout, SQL investigators, Risk & Action, the Action Executor and the brief's short answer; the same model with reasoning on (`chat_template_kwargs.enable_thinking`) for the Planner and Evaluator; **Nemotron 3 Ultra** (`nvidia/Nemotron-3-Ultra-550b-a55b`) as the backup model on the same endpoint. We picked the models with a probe on Token Factory (below).
- **Code computes, Nemotron reads and writes.** A deterministic analysis engine turns the question into a fixed battery of tests: counterfactual late rates per delivery stage with exact Shapley shares, shift-share by region, event tests against the prior trend, coded verdict rules. Nemotron reads and quotes the written record (quotes are verified verbatim), plans and challenges open-ended investigations, and phrases the answer; a numbers check then verifies every figure in the brief against the cell it came from. That keeps a real-data investigation to 5 to 9 model calls (about 15,000 to 40,000 tokens) and makes the answer reproducible.
- **Memory with provenance**, recalled by meaning with **Qwen3-Embedding-8B on Token Factory** (Token Factory's only embedder): confirmed and ruled-out causes, lessons and manager decisions, each with the run, agent and query behind it; corroborated findings are promoted to long-term memory.
- **Data in place**: DuckDB queries the CSV and JSON exports (and Postgres when it runs) with the agents' Spark SQL translated by sqlglot.
- **Hosting on Nebius AI Cloud**: one Docker image (React app, FastAPI API, both datasets) for a **Serverless Endpoint** pulled from **Nebius Container Registry**. Keyless by default, it replays recorded investigations step by step; with a Token Factory key it runs live investigations behind an access code, a daily run cap and a daily token budget, so a public URL can't drain credits.
- Python, LangGraph, pandas, OR-Tools, FastAPI with Server-Sent Events, React 19 + Vite + Tailwind; 67 tests that run without keys.

## Challenges we ran into

- **Moving models without moving answers.** WhyChain previously ran on NVIDIA NIM's `nemotron-3.5-super-vl-120b-a12b`, which Token Factory doesn't serve. Because numbers and verdicts come from code, the swap to Nemotron 3 Super changed none of them: the March 2018 investigation on Token Factory produced the same 14 verdicts and the same 72.7% / 26.7% shares as the recorded NIM run.
- **No Nemotron embedder on Token Factory.** Memory recall had used `nemotron-3-embed-1b` (2,048 dimensions). We switched to Qwen3-Embedding-8B, asked for 1,024 of its Matryoshka dimensions, added Qwen's query instruction, and re-embed any memory whose vector came from another model.
- **Embedding latency.** Single-text embedding calls took 1 to 12 s; the first port embedded each memory as it was written and spent almost three minutes of a five-minute run on it. We now batch a run's memories into one call (20 texts in about 6 s).
- **Long JSON outputs and a 60 s client timeout.** The Data Scout's data map runs to 2 to 3 thousand tokens; on Token Factory that took 17 to 60 s, and our first eval run hit the old 60 s timeout and fell back to Ultra. We raised the Token Factory timeout to 120 s.
- **Bringing memory, routing and the cause graph in-house without breaking the product.** They used to live in an external Node service; we rebuilt each inside WhyChain (memory with provenance and semantic recall, the injection guard and router, the why chain folded from each run's trace) and kept the old integrations as optional adapters.

## Accomplishments that we're proud of

- The same answers on a different model and provider: all 18 eval questions pass on Token Factory (root cause 18/18, red herring avoided 15/15, right action 8/8, held-out 4/4), every headline identical to the NIM version's, in 105 model calls and 392,006 tokens in all. On March 2018, all 14 verdicts and both shares matched the recorded NIM run, in 5 calls and 15,191 tokens.
- Red herrings ruled out by tests, not by the model's opinion: the strike, Carnival and a storm are each refuted with the trend before them.
- Every number is clickable down to its SQL, and numbers the cells don't support are marked "(unverified)" instead of shipped.
- A public demo that is safe to share: keyless replay by default, access code and spend caps for live runs.

## What we learned

- On Token Factory, Nemotron 3 Super with reasoning off was as accurate as Lightning, Nano and Ultra on our document-reading probe and no slower; reasoning on was the only setting that got it fully right, at about four times the latency. So reasoning goes only where judgement is (planning, evaluating), and everything else runs fast.
- Putting the model where language is (reading, quoting, phrasing, planning) and code where numbers are makes an agent portable: the port changed the plumbing, not the answers.
- OpenAI compatibility is real: the same client, JSON mode and the same `chat_template_kwargs` reasoning switch worked on Token Factory as on NIM; the port was base URL, key, model ids and the embedder.

## What's next for WhyChain

- Eval cases for the open-ended agent loop, written by someone other than the author.
- Long investigations as a Nebius Serverless Job, and memory and runs in Nebius Managed PostgreSQL and Object Storage, so several replicas share them.
- Connectors to live order systems, and a scheduled watch that opens an investigation when the control tower's rules fire.

## Built with

NVIDIA Nemotron 3 Super · NVIDIA Nemotron 3 Ultra · Nebius Token Factory · Qwen3-Embedding-8B (on Token Factory) · Nebius AI Cloud Serverless Endpoints · Nebius Container Registry · Docker · Python · LangGraph · FastAPI · pandas · DuckDB · sqlglot · OR-Tools · React · TypeScript · Vite · Tailwind CSS

## Feedback on Nebius Token Factory and NVIDIA tools

Concrete observations from porting WhyChain from NVIDIA NIM to Token Factory on 30 Oct 2026:

1. **The OpenAI-compatible API was a drop-in.** Same `openai` client, `response_format={"type": "json_object"}`, and Nemotron's reasoning switch through `extra_body={"chat_template_kwargs": {"enable_thinking": ...}}` behaved as on NIM. No provider-specific parameter we sent was rejected.
2. **Model ids differ from NIM in spelling and case**, which made a port error-prone: `nvidia/nemotron-3-super-120b-a12b` (lower case) next to `nvidia/Nemotron-3-Ultra-550b-a55b`, `nvidia/Nemotron-3_5-Lightning` (underscore) and `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`. NIM's `nvidia/nemotron-3-ultra-550b-a55b` is a different string from Token Factory's. Case-insensitive ids, or aliases matching NIM's, would help. Nemotron 3.5 Super VL was not available.
3. **Latency, measured** (a ~150-token JSON reply, 3 calls each, reasoning off): Ultra 0.9 s median, Super 1.1 s, Lightning 1.2 s, Nano 30B 1.3 s; Super with reasoning on 4.3 s (650 to 860 output tokens). Lightning, which we expected to be the fast option, was not faster than Super for us. In real runs Super's median call was about 2 s; long outputs varied widely (1,161 tokens in 29 s once, 2,387 in 17 s another time).
4. **Quality, measured**: on a four-point document-reading probe all four models scored 3/4 with reasoning off; Super with reasoning on scored 4/4 every time.
5. **Embeddings are the weak spot.** There is no Nemotron embedder (NIM has `nemotron-3-embed-1b`); `Qwen/Qwen3-Embedding-8B` is the only option. It works well, honours `dimensions` (we use 1,024), and silently accepts NIM-style `input_type`, `truncate` and `encoding_format`, but single-text latency was 1 to 12 s, which is slow for interactive recall. A small, fast embedder (or Nemotron Embed) would make retrieval-heavy agents much snappier.
6. **Structured output.** `json_schema` is enforced on shape, but field descriptions in the schema don't reach the model, so anything a field needs to say has to be repeated in the prompt. Worth documenting.
7. **One endpoint for chat and embeddings, one key, per-token billing** made a spend cap easy to build: WhyChain counts tokens per run from the `usage` field and stops live runs past a daily budget.
8. **Nebius CLI (WSL, v0.12.298):** our cached profile could still run `iam whoami`, but `registry list` failed with `PermissionDenied: unknown subject` and `ai endpoint list` opened a browser re-login, so a non-interactive deploy script can't tell an expired session from a missing permission. A clearer "session expired, run `nebius profile create`" message would save time.
