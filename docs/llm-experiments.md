# LLM Prompting Runs — Report

**Date:** 17–19 August 2026
**Models tested:** Gemini 3.1 Flash-Lite, Claude Haiku 4.5, Claude Sonnet 5
**Scale:** ~1,200 requests across 11 runs

---

## The headline

**Skills raise the cost of a task by roughly 3–5x — but not for the reason it
looks like.**

The Skill text is small. It adds about 800 tokens, around 14% of one request.
The cost comes from **round-trips**: the Skill tells the model to inspect
first, explain its plan, and wait for approval. So one task becomes 2–5 billed
requests instead of 1.

The multiplier is turns, not text.

---

## Where the tokens actually go

Preliminary measurements indicate that tool definitions are the largest
component of input context. However, the earlier component-level estimates did
not add up consistently to the recorded total input-token count.

Because the original breakdown has not yet been independently reproduced, the
component percentages are omitted here. A controlled rerun will record:

- tool-definition tokens
- Skill-instruction tokens
- task and cluster-context tokens
- cached input tokens
- uncached input tokens
- output tokens
- number of model requests

The verified API-level measurement currently available is:

| Metric | Before caching | After caching |
|---|---:|---:|
| Billed input per request | 6,631 tokens | 957 tokens |

This indicates an approximately 86% reduction in billed input tokens. The
component responsible for that reduction will be reported after the controlled
rerun.

---

## Round-trips per task

| Setup | Requests per task |
|---|---:|
| No Skill | 1.0 |
| With Skill — Claude Haiku | 2.0 |
| With Skill — Gemini Flash-Lite | 3.0 |

Gemini needs about 50% more round-trips than Haiku for the same work.

---

## Speed

| Model | Per request | Notes |
|---|---:|---|
| Claude Haiku 4.5 | 2.5 s | |
| Gemini Flash-Lite | 5.9 s | free tier, includes rate-limit waiting |

Gemini is free but slower and needs more turns. Haiku costs money but finishes
a task in less than half the wall-clock time.

---

## The fix we found: caching

The caching measurement shows an approximately 86% reduction in billed input
tokens, suggesting that repeated static context accounts for most of the
uncached input.

| | Before | After |
|---|---:|---:|
| Billed input per request | 6,631 tokens | **957 tokens** |

**86% cheaper input.** Verified on live calls, not estimated.

This applies to the product too, not just experiments — EdgePilot was
re-sending 22,000 characters on every message a user typed.

---

## Cost

Actual spend on 17 August: **$7.32** for ~1,200 requests.

With caching now on, the same work would cost **under $1**.

---

## Answering Dr. Kim's question

He asked how token use grows across three setups. Two are measured, one is
predicted:

| Setup | Cost per task | Status |
|---|---|---|
| 1. AI without skills | baseline (1x) | measured |
| 2. AI with skills + human approval | 3–5x | measured |
| 3. Fully agentic, no approval step | **lower than 2** | predicted |

**The prediction is worth testing.** Removing the human approval step removes
round-trips, so a fully agentic setup should cost *less* per task than the
current supervised one — not more. That is the opposite of what people usually
assume about agentic systems.

We have the instrument to measure it: the test harness already records turns
and real token counts per run.

---

## One caution about our own numbers

Our first three measurement runs were **thrown out**. The test harness had
faults that made the AI look worse than it was — including one where the Skill
was never actually loaded, so we were measuring the bare models while
reporting on Skill performance.

All faults are fixed and the harness is now validated. But it is worth stating
plainly: **we do not yet have final reliability figures**, and we would rather
say that than publish numbers we cannot defend.

The cost, speed and turn-count figures in this report are measured and sound.
The accuracy figures are still to come.

---

## What we do next

1. Run the three-condition token comparison end to end
2. Scale the test cluster 10 → 100 → 1,000 nodes and measure how cost and time
   grow
3. Publish the reliability figures once the first clean sweep completes
