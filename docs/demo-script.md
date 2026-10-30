# WhyChain demo video: script and shot list

Target length about 3 minutes. Screen recording at 1600×1000 or larger, browser zoom 100%, the app at
`http://localhost:8000` (or the Nebius Serverless Endpoint URL). **[Nemotron]** marks where NVIDIA Nemotron on Nebius
Token Factory is doing the work on screen.

A preliminary answer, computed from the data, appears within seconds of starting a run; the full brief follows in one
to two minutes. Show the preliminary answer live, then cut ahead to the brief and say so ("about a minute later").
Never present a replay as live: a replay is labelled "Replaying" in the app.

## Before recording

1. `.env` has `NEBIUS_API_KEY`. Run `start.cmd` (Windows) or `./start.sh`, or `docker run -p 8000:8000 -e NEBIUS_API_KEY whychain`.
   Wait for "Warm-up done" (it loads the analysis tables, so the first question doesn't wait for them).
2. `python -m whychain.doctor`: data OK, memory "Qwen/Qwen3-Embedding-8B (Nebius Token Factory)", models `tf`,
   `tf-reason`, `tf-backup` green.
3. Run the two demo questions once, so there are finished runs to fall back on and memory holds an earlier March
   2018 investigation (for shot 6). Fallback if a live call is slow: `http://localhost:8000/runs/20261030-060526-66f1?replay=1`
   (the Token Factory run, replayed at real speed, badged "Replaying").

## Shots

| # | Time | Screen | Action | Say |
|---|---|---|---|---|
| 1 | 0:00–0:15 | Control tower, Olist | Hold on the chart with event markers | "When deliveries go late, a manager needs to know *why*: which stage broke, where, and whether the strike in the news is really to blame. The answer is spread across the order system, seller exports, reviews and news. WhyChain investigates it, on NVIDIA Nemotron served by Nebius Token Factory." |
| 2 | 0:15–0:30 | Control tower | Point at the March 2018 spike, click **Investigate why** | "Real Brazilian marketplace data, 99,000 orders. In March 2018, 19% of deliveries were late, and there was a postal strike that month. Let's ask why." |
| 3 | 0:30–0:55 | Investigation, live | The activity feed (tick **Technical detail**: routed by WhyChain's rules to the analysis engine; every SQL query); the **Preliminary answer** card appears within seconds | "The numbers come from code, not the model, so a first answer is here in seconds: 1,328 late orders worth 187,000 reais, rated 2.1 stars against 4.2. Meanwhile **[Nemotron 3 Super]** on Token Factory reads the news briefs and must quote them word for word." Cut: "about a minute later". |
| 4 | 0:55–1:30 | **Brief** | Read **In short**; point at the **why chain** (the strike crossed out); click a numbered source to open the table and its SQL; open the **Trace** tab and show a model call: provider `tf`, `nvidia/nemotron-3-super-120b-a12b` | "19% late against a normal 5.6%. Carrier transit explains 72.7% of the rise, shorter promises 26.7%. The strike? Ruled out: transit was already 14 days before it began. Every number is checked against the cell it came from. **[Nemotron]** writes only the short answer, from those checked facts; five model calls in all, every one on Token Factory." |
| 5 | 1:30–2:05 | Switch to **Kaveri**; run **Pune orders at risk** | Preliminary answer with the transfer; the brief; **Approve** the transfer; show the deliverables | "A simulated distributor. Pune orders are at risk because a supplier's purchase orders are stuck behind a port strike. The fix is a stock transfer from Mumbai, solved as a linear program and proven optimal. Approve it, and the Action Executor, on **[Nemotron]**, prepares the transfer order and the supplier email." |
| 6 | 2:05–2:30 | Olist: ask a reworded March 2018 question; open its **Memory** tab | "Recalled N memories", with provenance; the cause graph | "WhyChain remembers what it found, with provenance. Recall is by meaning, with Qwen3 embeddings on Token Factory, so a reworded question finds the earlier finding, as a hint it re-checks, never as evidence." |
| 7 | 2:30–2:55 | The Nebius console (Serverless Endpoint running the WhyChain image) or the README's Nebius table | Show the endpoint and the app at its URL | "The whole app is one container on a Nebius AI Cloud Serverless Endpoint, pulled from Nebius Container Registry. Without a key it replays recorded investigations; live runs sit behind an access code and a daily token budget. WhyChain: an agent that explains why, with the evidence to prove it." |

## Where Nemotron and Nebius appear

- Document Analyst (shots 3–4): Nemotron 3 Super (reasoning off) on Token Factory finds and quotes the written record.
- Brief answer (shot 4): Nemotron 3 Super phrases the short answer from computed, checked facts.
- Action Executor and the open-ended agent loop (shot 5): Nemotron 3 Super; planning and judging with reasoning on.
- Memory (shot 6): Qwen3-Embedding-8B on Token Factory (Token Factory serves no Nemotron embedder).
- Fallback (not on screen): Nemotron 3 Ultra on Token Factory.
- Hosting (shot 7): Nebius AI Cloud Serverless Endpoint, image in Nebius Container Registry.
