<p align="center">
  <strong>English</strong> · <a href="./README.ja.md">日本語</a> · <a href="./README.md">简体中文</a>
</p>

<p align="center">
  <img src="./assets/readme/hero.png" width="100%" alt="idiolect: make an AI character speak in character, and prove it got closer. The illustration shows the five members of MyGO!!!!! — Anon, Tomori, Taki, Soyo and Rana.">
</p>

<h1 align="center">idiolect</h1>

<p align="center">
  <strong>Make an AI character speak in character, and evaluate the result with reproducible evidence.</strong>
</p>

<p align="center">
  <sub>~~Rikki, why are you holding a guitar — is it because the author was too lazy to re-render the image?~~</sub>
</p>

<p align="center">
  <a href="https://github.com/puresky271/idiolect/actions/workflows/ci.yml"><img src="https://github.com/puresky271/idiolect/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/runtime%20deps-0-brightgreen" alt="runtime dependencies: 0">
</p>

<p align="center">
  <a href="#-what-you-actually-get">What you get</a> ·
  <a href="#watch-the-demo-then-inspect-the-evidence">Demo &amp; evidence</a> ·
  <a href="#-quick-start">Quick start</a> ·
  <a href="#-four-layers-how-the-prompt-is-assembled">Four layers</a> ·
  <a href="#-docs">Docs</a>
</p>

Folks, as vendors keep pushing models harder on coding and agents, AI roleplay is getting harder and harder to keep a straight face through. This repository is one author's write-up of what actually worked: **a methodology for evaluating AI character-dialogue systems, plus a field log of prompt-engineering pitfalls**, with a reusable constraint framework on top. If you are building AI characters, I hope it saves you some of the pain.

If you let a general model play a character, the replies drift into one customer-service voice: they grow longer, "I completely understand how you feel" shows up, every conversation ends on a meaningful note, and then it sits there comforting you indefinitely. This repository works the other way round: it **measures how the character actually talks** from the original script — how long a line is, how many sentences, which verbal tics, what changes by scene — writes those measurements into the prompt as hard constraints, and then runs automated checks on whether the output really got closer. No fine-tuning, and no original script text in the repository — only the statistics.

The running example is the five members of **BanG Dream! It's MyGO!!!!!**. Note that **the method itself is show-agnostic**: it transfers to other works, but the character profiles, corpus baselines and verification scenes all have to be rebuilt. We solve exactly one thing — proving a reply sounds in character — and make it standalone and reproducible.

> [!IMPORTANT]
> **Let us get rights and licensing straight first.**
> **Code** (`idiolect/`, `tools/`, `docs/`, `tests/`) is MIT — use it freely ([`LICENSE`](LICENSE)).
> **The characters and the work are not ours**: MyGO!!!!! characters, settings, story and music belong to **Bushiroad / Craft Egg and the relevant rights holders**. This is an **unofficial fan-made technical project**, not affiliated with, authorised by, or endorsed by them.
> **The repository contains no original script text** (no game script, dialogue or lyrics) and no audio; `data/` holds aggregate statistics only, and the sample illustration is fan usage, not official artwork.
> Details in [`NOTICE.md`](NOTICE.md) and the [Copyright, licence and disclaimer](#-copyright-licence-and-disclaimer) section below.

## 🆕 v0.1.2: from "sounds right" to "says only what it can see"

v0.1 answers one question: **does this character sound like herself?** v0.1.2 adds a second, independent question beside it: **is the reply constrained by the evidence it can actually see?** — say current things directly, put a time on past things, neither invent nor wrongly deny what is unknown, and never let a single word of someone else's private chat or the evaluation's gold answers leak into the prompt. On top of both sits a question that spans them: **can this evaluation reach a conclusion at all?**

| What's new | In one line |
|---|---|
| **Evidence contract** `evidence-context/v1` | A versioned record of "what the model can see this turn": three states (current / history / unknown), stable IDs, time and scene, provenance, visibility; missing fields, dangling references, private paths and evaluation fields are all rejected |
| **Explicit snapshot adapter** | The host system hands in a snapshot that is **already redacted and carries a permission declaration**; the adapter opens no database, infers no tense, and lets through no record the observer cannot see |
| **grounding evaluation** | 11 pre-registrable task types: current fact, historical qualification, unknown, false premise, citation, isolation of invisible information, stale-as-current, correction, budget removal, private metadata, style only |
| **Two-axis report** | The style axis and the grounding axis are judged and aggregated separately and **never weighted into one overall score**; response quality (usable / empty / error / truncated) and evaluation validity (coverage, N/A reasons, missing measurements) are listed alongside |
| **Optional capabilities** | `spatiotemporal` (spatiotemporal grounding) and `long-context-stress` (long-context stress) are enabled explicitly; without them, the default language workflow **needs not a single line changed** |
| **Experiment manifest + comparability gate** | Version, content SHA, code revision (including dirty state), clock, assembly, scorer and labels are all recorded; any change that was not pre-registered blocks pooling and any "improvement" verdict |
| **Same-chain mutation self-test** | 25 mutants and 9 healthy counter-controls run through **the same** evaluation chain; a "hollow gate" that swallows its arguments is caught by the canary that every run carries |
| **Unified CLI + offline inspect report** | `idiolect eval / compare / report / selftest …`, zero keys, zero network; paid calls require an explicit `--yes` and a call cap |
| **Code and comment style gate** | A new lint job in CI: ruff checks code correctness, and `style_gate.py` checks Chinese docstrings, comment format, traditional characters and English-only comments |

The runtime still has **zero third-party dependencies**: all of the above ships in the wheel with `pip install`, and CI installs that wheel with `--no-deps` in a clean environment outside the repository and runs everything again. Upgrade and migration notes are in [`docs/11-upgrade-guide.md`](docs/11-upgrade-guide.md).

## 📦 What you actually get

| You get | Concretely |
|---|---|
| **A drop-in assembly library** | `pip install .` then `from idiolect.assemble import build_messages` returns the four-layer prompt. **Zero third-party runtime dependencies** — openai / numpy / jieba are only needed for probing and distillation |
| **An evaluation loop that proves "closer"** | Probe → (distribution fit / within-cell repetition / verbatim-copy audit) → multi-arm pooling → power estimate. Two dedicated probes cover boundary refusal and multi-turn drift, and an evidence gate checks fact consistency. The table below is one real run of 105 replies |
| **An evaluation that checks "is it right"** | Evidence contract + grounding tasks + two-axis gate + experiment registry; 4 built-in suites (including opaque generic tasks and a five-character same-question showcase), synthetic replays and negative controls — all run offline once the package is installed |
| **Seven mechanical gates plus a prompt-diff gate** | Prompt edits should not rest on vibes: one `offline_smoke.py` run covers assembly, scene coverage, trigger matrix, content red lines, data shape, the evaluation contract, the same-chain self-test, the gates and a zero-write check |
| **Tooling that transfers to another work** | 69 scripts: acquisition and cleaning, corpus splitting, scene discovery, tic distillation, length-target export, probing and scoring, prompt and workspace dumps. The method is not tied to one show — point it at another cast and re-run |
| **Ready-made character data (aggregates only)** | 26 scenes (13 general + 13 character-specific), 130 character × scene length targets, 114 per-scene tic cells, style profiles for five characters |
| **Twelve methodology documents** | Where the corpus comes from, how the five feature classes are computed and landed, how to evaluate, the evidence contract and grounding, long-context stress, the pitfalls already paid for, and how to upgrade — each readable on its own |

### A portable roleplay Skill

Copy the complete [mygo-five-roleplay folder](skills/mygo-five-roleplay/SKILL.md) into your agent's skills directory. Claude/Codex can then read the bundled character materials and reply directly, without Python or an API key. Select a member, or name her together with your topic; say "exit roleplay" to return to the assistant. Character directories are optional and loaded on selection.

These static materials share the library's sources but do not execute its dynamic routing, session state or post-processing. A good experience does not certify quality — evaluation, distillation and the gates remain the main line. See the [installation and export guide](docs/01-quickstart.md#先体验五人-skill).

### Watch the demo, then inspect the evidence

[![Native-color Claude Code terminal recording: Rana](assets/readme/roleplay-demo.gif)](assets/readme/roleplay-demo.mp4)

**[Play / download the clip](assets/readme/roleplay-demo.mp4)** · [Static preview](assets/readme/roleplay-poster.png) · [Transcript and provenance](assets/readme/roleplay-transcript.json)

This **25-second** clip records **Claude Code** directly in Windows Terminal, preserving its native colors and showing a real reply from Rana on **DeepSeek-v4-pro[1m]**. Only the idle stretches at both ends were trimmed; generation was not sped up. The Skill and Rana's materials were explicitly loaded, and the input was supplied as the initial message. This does not test automatic Skill discovery or multi-turn stability.

![Offline evaluation overview: filters, missing conditions and character metrics](assets/readme/evaluation-overview.png)

The offline evaluation page for probe batches keeps the warnings about missing conditions in historical batches; since v0.1.2 it also judges the **comparability** of two batches — old batches have no manifest fields, so they can only be browsed and are never compared automatically. Expand Rana's comfort scene to set the model's original replies against the cleaned ones.

![Rana comfort scene: diagnostics and original versus cleaned replies](assets/readme/evaluation-evidence.png)

Run `py -X utf8 tools/score/report_html.py --labels <label>` on your own batch to open the probe evidence page; for grounding evaluation, `idiolect eval … --html` produces a per-task inspect page (see below). These screenshots come from the historical `repo_standalone` batch, a separate experiment from the host demo above.

## 🚀 Quick start

**First, get it — pick one of four routes:**

| Route | One command | Notes |
|---|---|---|
| **Let an agent do it** | paste the prompt below into your coding agent | least work: it clones, installs and runs the self-check itself |
| **uv (one line, nothing left behind)** | `uvx --from git+https://github.com/puresky271/idiolect idiolect prompt Rana "你今天又想去哪找猫"` | see a prompt immediately; no clone, no environment to set up |
| **pip as a library** | `pip install git+https://github.com/puresky271/idiolect` | use it as a dependency; zero third-party runtime deps |
| **Files only** | `npx degit puresky271/idiolect idiolect` or `git clone --depth 1 https://github.com/puresky271/idiolect` | you want the toolchain or the source |

Prompt for your agent (Claude Code, Codex, anything similar):

> Set up https://github.com/puresky271/idiolect for me: clone it, read `AGENTS.md`, run `python bootstrap.py`, then show me the self-check result, the five characters' complete prompts (`py -X utf8 tools/gates/dump_prompt.py --all --matrix`) and the output of `python -m idiolect selftest`. After that I want to switch to my own characters, following `.claude/skills/idiolect-pipeline/`.

**Then run this from the repository root** (Python 3.11+):

```bash
pip install .                                        # zero third-party runtime dependencies
python -m idiolect list                              # the five built-in characters
python -m idiolect prompt 乐奈 "你今天又想去哪找猫"     # the full system prompt for this message
python -m idiolect showcase "我今天有点撑不住了"        # side-by-side five-character view (no model call)
python -m idiolect chat 乐奈 "你今天又想去哪找猫"       # one real chat turn (env vars below)
```

**Evaluation (all offline, zero keys):**

```bash
python -m idiolect capabilities                      # which evaluation capabilities exist, what each covers and what it does not
python -m idiolect bench list                        # built-in suites and synthetic replays
python -m idiolect eval --suite spatiotemporal-core \
    --responses builtin:spatiotemporal-core.healthy --capabilities spatiotemporal --html
python -m idiolect selftest                          # the evaluation chain's own detection power
```

To set up the toolchain as well, one command is enough — it creates `.venv`, installs the requirements, runs the `offline_smoke` self-check and prints one character's per-layer sizes:

```bash
python bootstrap.py
```

On Windows, prefer `py -X utf8` over a bare `python`, which may resolve to an interpreter without the dependencies. `chat` and `run --yes` talk to any OpenAI-compatible endpoint: set `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` and `pip install "idiolect[llm]"`.

From code:

```python
from idiolect.assemble import build_messages
messages = build_messages("乐奈", "你今天又想去哪找猫")   # ready to send to the model
```

## 🧭 Two evaluation axes, judged separately, never merged into one score

| | Style axis | grounding axis |
|---|---|---|
| Question it answers | Does it sound like this character? | Is it constrained by the visible evidence? |
| Enabled by default | Yes | No: `--capabilities spatiotemporal` / `long-context-stress` |
| Per-reply checks | Hard length cap (the same number the prompt states), sentence cap, high-severity boundary features, canon facts, thinking-tag leaks | Contract validation → prompt boundary (is the key evidence visible, tense alignment, provenance alignment, isolation of hidden values and private metadata, layer order) → reply (claims, denials, time qualification, refusals, corrections, citations, hidden values) |
| Batch level | Distribution metrics of a probe batch: headline metric, control column, scene fit, within-cell repetition, copy audit (see the historical batch below) | family-level pass rate + paired sign test |
| When it cannot judge | Scoring module absent from this install → not applicable, listed in the gate notes | Open rewording → `needs_review`, awaiting human blind-judgement labels |

Every verdict carries **applicability, status, reason, numerator/denominator, evidence and scorer version**. The status is always one of `pass`, `fail`, `not_applicable`, `missing`, `needs_review`, `error`, `empty`, `underpowered`. The gate's rules are fixed in code:

- the denominator counts only `pass + fail`; missing measurements, N/A, empty replies and dry-run placeholders **never count as passing and are never folded into an average**;
- any `fail / error / empty / missing`, an enabled capability with zero valid verdicts, or all N/A → **FAIL**; only `needs_review` left → **INCONCLUSIVE** (exit code 3);
- **the family is the independent unit**: arms, turns, repeats and checkpoints within one family are nested observations; when the number of families is below the pre-registered minimum, PASS only means "no violation detected" and supports no capability claim;
- a model judge is recorded as auxiliary only (stating how the judge relates to the generating model) and **does not change** the mechanical verdicts; human blind-judgement labels can only rewrite `needs_review`.

## 🧪 Four modes: style only by default, capabilities enabled explicitly

| Mode | Command | Tasks it applies to |
|---|---|---|
| Language only (default) | `idiolect eval --suite language-only --responses builtin:language-only.healthy` | five characters × four messages; no spatiotemporal schema needed |
| Spatiotemporal alone | `… --suite spatiotemporal-core --capabilities spatiotemporal` | Evidence contract + grounding tasks |
| Long context alone | `… --suite long-context-smoke --capabilities long-context-stress` | Length × position matrix, budget-truncation controls |
| Both together | `… --capabilities long-context-stress,spatiotemporal` | Adds a "history/current conflict × multi-turn" family |

A task that needs both capabilities shows `not_applicable`, with the reason, when only one is enabled; when a capability is off, its evidence block **does not** enter the prompt. The five-character same-question showcase (`mygo-five-showcase`) runs with or without the temporal capability: with it, both axes are judged; without it, style only. Every built-in replay is a **synthetic reply** used only to validate the evaluation chain — a demo is not empirical evidence.

## 🧾 Evidence contract: what the model can see this turn

```python
from idiolect.evidence_contract import parse_evidence_context
from idiolect.workspace import build_workspace_messages

context = parse_evidence_context({
    "schema_version": "evidence-context/v1",
    "observer_id": "actor_a", "as_of": "2026-09-12T15:00:00+09:00", "scene_id": "scene_02",
    "current": [{"evidence_id": "evidence_17", "status": "current", "text": "actor_b 在车站东侧入口。"}],
    "history": [{"evidence_id": "evidence_09", "status": "history", "text": "周三排练时 actor_b 在旧练习室。",
                 "as_of": "2026-09-09T18:30:00+09:00"}],
    "unknown": [],
})
messages = build_workspace_messages("乐奈", "她现在在哪？", evidence_context=context)
```

The contract describes only the **model-visible** side; expected answers, values that must not leak, and gold live in the evaluation task's `expect` / `oracle`, and the prompt-boundary check scans the final messages to confirm none of them slipped in. Rendering emits whitelisted metadata only: evidence_id, the time of history entries, a safe opaque locator, and the allowed provenance keys. current / history / unknown are projected upstream — idiolect does not derive world truth from timestamps, and does no image recognition, audio/video decoding or geographic projection. Host-system context can only come in through an [explicit snapshot](docs/09-evidence-grounding.md#3-显式快照-adapter): `idiolect contract project <snapshot-file>` lists the invisible records that were dropped (IDs and reasons only).

The old unversioned form (`TemporalEvidenceContext.from_dict(unversioned_dict)`) still works but emits a `DeprecationWarning`; it treats a missing status as current, which the strict contract does not.

## 🔬 The evaluation chain has to be tested too

A gate can "pass" merely because its input was dropped upstream, because the comparison was guaranteed by a signature, or because the denominator was empty. So:

- **Same-chain mutants**: 25 mutants each change one thing at one injection point — input contract, adapter, rendering, assembly budget, reply, scorer, aggregation, manifest — and travel **the same** chain as a real evaluation; the report says, stage by stage, what caught each one (structure / prompt boundary / reply / aggregation / gate / comparison). Among them, 1 is an equivalent variant that "wraps the function and renames a parameter", and it must **not** be judged different — detection rests on behaviour, not on signatures.
- **Healthy counter-controls**: 9 alternative phrasings of correct answers (third-person denial, a legitimate "I don't know", the same name in a different scene, full-width digits, the five characters' short lines and ellipses…) must stay PASS, which keeps false positives in check.
- **A canary in every run**: a known hidden value and a private path are planted in the boundary check, and a known violation in the reply check — the checker must flip its verdict, or the run FAILs outright. A gate that accepts a hidden argument and then discards it gives itself away here.
- **Representation operators certified one by one**: benign transformations — full-width digits, digit-grouping commas, case, whitespace, ellipses, Japanese context — must preserve the verdict; Chinese numeral readings and traditional characters are **not certified** and go to `needs_review` when they appear.
- **Manifest and comparability**: two batches are comparable only if they differ in the pre-registered intervention variable alone; any non-intervention change in model, clock, scorer, labels or suite blocks automatic pooling and any "improvement" verdict; a missing field means `incomparable`; if an artifact in the registered directory has been modified, the comparison fails closed.

Catching a mutant only shows that "this kind of injected defect can be detected by this chain"; it is not a detection rate for natural defects, still less an improvement in model capability.

## 🔍 Sample analysis of the example cast

Using the MyGO!!!!! five as the example:

| Character | Typical line length (median) | Sentences per turn | Signature habits |
|---|---|---|---|
| Anon | 20 chars | 1.6 | 35% of lines carry an exclamation mark; tics "啊、诶、哦" |
| Tomori | 11 chars | 1.2 | 81% of lines carry ellipses, long runs of "······" |
| Taki | 15 chars | 1.4 | Short and direct; 39% of her original lines open with a bare noun |
| Soyo | 16 chars | 1.4 | Gentle and restrained; exclamation rate only 6% |
| Rana | 6 chars | 1.2 | Extremely short, 3% exclamation rate, topic often hijacked by cats |

Every median, sentence count and punctuation share in the table can be looked up in [`data/style_profiles.json`](data/style_profiles.json); Taki's noun-opening rate is a corpus-level count, and `tools/score/_noun_initial.py <run-label>` prints the original baseline alongside the arm.

The gap widens per scene too: in a confession scene, for instance, Rana says 7 characters and Soyo 17. That is exactly why the constraints have to be "this character in this situation", not one shared average.

## ❓ Why it exists

A model playing a character makes the same four mistakes, and none of them require the model to fail — they are what the training objective produces:

1. **Replies get long**: where the character says 7 characters in the original, the model writes 700.
2. **Empathy templates**: "I completely understand how you feel. When pressure surges like a tide..."
3. **The meaningful ending**: every exchange lands a neat, positive conclusion.
4. **Breaking cover**: the model talks about its own setup, leaking inner monologue or thinking tags.

Once a character is wired into a system with memory, schedules and world state, a second set of mistakes appears: treating last week's location as the present, repeating the other person's private chat, inventing an answer to something it does not know, and, when asked "since you've seen the photo", going along and describing the photo. None of this is about sounding right, and no style score, however high, will stop it — so v0.1.2 judges it separately, on a second axis.

If every character answers with the same paragraph of comfort, there is no character left. So the whole method fits in one sentence: **turn both "does it sound right" and "is it right" into measurable things, then iterate on the numbers**.

- **Compare only against the same character in the same scene.** Not against general human speech, and not against the character's global average.
- **Numbers raise suspects; they don't convict.** One character's output runs 5x the reference length, half of it because her ellipses count as characters — you have to read the reply to judge.
- **Small samples mean "no conclusion".** With 6 replies per cell, the same scene and prompt can swing one character's score from 0.551 to 0.350 — more than the effect being measured.
- **No meta vocabulary in character-visible text.** Words like "corpus", "median" or "baseline" inside a prompt invite the model to discuss its own construction.
- **Evaluation answers never enter the prompt**, and what cannot be judged is reported as such: a blank is not a valid refusal, and unknown is not a denial.

Full method: [`docs/00-methodology.md`](docs/00-methodology.md) (Chinese).

## 📊 Historical probe batch (qualitative example only)

This table is one real probe run, not a design target. A probe sends each character a batch of messages, then collects the replies and scores them item by item:

```bash
py -X utf8 tools/probe/probe_runner.py --label repo_standalone \
    --assemble --turn-logic --registry --cats 通用场景 --runs 3
py -X utf8 tools/score/probe_report.py --label repo_standalone --scenes crisis,comfort --cat 通用场景
```

| Character | Replies | composite (likeness, 100) | fidelity (style fit, control column) | Red-line rate | Leak rate | Scene fit |
|---|---|---|---|---|---|---|
| Anon | 21 | 64.6 | 86.5 | 4.9% | 0% | 0.545 |
| Soyo | 21 | 90.5 | 85.4 | 0.0% | 0% | 0.532 |
| Taki | 21 | 75.6 | 82.4 | 0.0% | 0% | 0.386 |
| Tomori | 21 | 86.9 | 79.9 | 0.0% | 0% | 0.365 |
| Rana | 21 | 86.9 | 79.9 | 0.0% | 0% | 0.504 |

- Conditions: `deepseek-flash`, temperature 0.75, max_tokens 420, clock pinned to daytime, 3 samples per cell, 105 replies, zero errors.
- **composite** is the headline metric: 0.65 style fidelity + 0.35 content anchors (see `docs/04-evaluation.md` §2.1). fidelity only measures length and sentence-count distributions and stays a control column — on its own it rewards correct-but-empty assistant tone. Anon is the live example: top fidelity, bottom composite (polished phrasing, few concrete details). When the two disagree, inspect the anchors, the actual replies and the blind judgments; composite can also lose sensitivity once anchor scores saturate.
- **Scene fit** measures how closely a reply's length and sentence count match the original same-character-same-scene distribution; 1.0 is full agreement, and this batch averages 0.466 over 35 cells. It is a **relative** score for before/after comparison inside one batch — not comparable across models or fixtures.
- Replies that differ from the other two in their cell of 3: 93/105. Verbatim reuse of prompt text: 1%, and the 3 copied characters were the verbal tic "诶……", not an example sentence.
- Leak rate covers thinking tags, inner monologue, speaker echo and Chinese stage directions — all 0 here.
- The raw artifacts behind this table (`report/probe_*.jsonl` and the scoring reports) are not shipped, per the artifact discipline: re-running the commands above reproduces the **process**, and you get your own batch of numbers. This batch was run before v0.1.2 and has no manifest, so it can only be browsed and is never compared automatically against new batches.

Here is what happens to the same inputs when the four layers are replaced by an empty system prompt:

| Scene | Empty system | Four layers |
|---|---|---|
| Rana / comforted | "I completely understand how you feel. When pressure surges like a tide..." (380 chars) | "Mm." "Cat. Under the eaves." (median 10) |
| Rana / low mood | "When pressure surges and even breathing feels like effort..." (718 chars) | "Mm. ... A cat over there." |

The two columns come from different places: the **four layers** column is from the `repo_standalone` batch above and is reproducible; the **empty system** column is one manual side-run — the raw record of those two generic-assistant replies — whose probe artifacts are not shipped, so treat it as a qualitative illustration only.

> [!WARNING]
> This cell is tiny and proves nothing on its own, but it shows one thing: **a probe must assemble its own prompt** — the shipped fixtures have an empty system field, so without `--assemble` you are measuring a bare model with no character prompt at all.

## 🧩 Four layers: how the prompt is assembled

Everything measured lands in four layers, in a fixed order — stable parts first (they cache well), per-turn parts last:

| Layer | Plain reading | Content | Frequency | Chars for Rana's cat scene |
|---|---|---|---|---|
| `canon` | Who she is | Long profile | static | 12223 |
| `voice` | How she talks | Sentence patterns, tics, per-person attitude differences, anti-template hard constraints | static | 1940 |
| `style_target` | How much to say this turn | Verifiable numbers for length, sentence count, endings, first person; scene-specific values on a match | per turn | 541 |
| `turn_logic` | What situation this turn is | This turn's scene/topic guidance | per turn (only on match) | 846 |

These four layers are this repository's complete answer to "how do measured features reach the prompt". A real system can put memory, world state and schedules in front of them; those layers are unrelated to the method.

`tools/gates/dump_prompt.py` prints each layer for inspection. Use `--phase current` both before and after a change, keeping inputs, clock and flags identical and saving to separate report directories. The workspace path beyond the four layers (external blocks, history, execution packet, budget tail-trimming, evidence block) gets the same before/after comparison with `tools/gates/dump_workspace.py`.

**What surrounds the four layers in a real system?** Every turn, the model also needs to know what time it is, where the character is, what was just being discussed, and what the user mentioned last week. That context is organised as a **workspace**: a dozen-odd candidate sources are collected, scored, ranked, trimmed to a budget, then assembled in a fixed layer order — the four layers sit in the `persona` slot, and the evidence block in the `on_demand_evidence` slot. The skeleton lives in `idiolect/workspace.py` (zero dependencies); see [`docs/08-context-workspace.md`](docs/08-context-workspace.md):

```python
from idiolect.workspace import build_workspace_messages
trace = {}
messages = build_workspace_messages(
    "乐奈", "你今天又想去哪找猫",
    blocks=[("current_state", "乐奈在 RiNG 排练室，下午没课"),
            ("fact_workspace", "用户上周提过想养猫")],
    execution_packet="【本轮执行】回复 ≤19 字",   # appended to this turn's user message
    trace=trace,                                 # optional: records layer order, per-layer sizes and layers dropped by the budget
)
```

## 📖 The five characters' prompts ship complete

This is not "here is a method, go configure your own cast". **All four layers for all five members ship with the repository**: the long canon profile, the voice manifest, the speech-scale numbers and the scene guidance. Nothing is truncated, nothing is elided, and you need neither an API key nor a corpus to read them.

```bash
# With the package installed (no clone, no key, no corpus needed)
python -m idiolect prompt Rana "你今天又想去哪找猫"              # the complete system prompt for this message
python -m idiolect prompt 乐奈 "你今天又想去哪找猫" --layers canon,voice   # one layer only

# From a clone: the layered audit copy, the exact messages array, and per-layer sizes
py -X utf8 tools/gates/dump_prompt.py --char 乐奈 --msg "你今天又想去哪找猫"
py -X utf8 tools/gates/dump_prompt.py --all --matrix      # 5 characters x 4 messages = 20 dumps
```

Three artifacts per dump: `prompt_<char>_<phase>_<label>.txt` (layered, for reading), `.json` (the messages array as sent to the model), `.layers.json` (per-layer character counts). The table below is the measured comfort cell of `--all --matrix`, with the input 我一直在哭，快撑不住了:

| Character | canon | voice | style_target | turn_logic | Total |
|---|---|---|---|---|---|
| Anon | 16285 | 6656 | 533 | 539 | 24013 |
| Tomori | 8068 | 7008 | 530 | 616 | 16222 |
| Taki | 12618 | 5579 | 533 | 491 | 19221 |
| Soyo | 9087 | 2279 | 532 | 479 | 12377 |
| Rana | 12223 | 1940 | 531 | 509 | 15203 |

The text of every layer is in the repository and readable verbatim: `canon` and `voice` live in `idiolect/characters/*/` (`canon.py` / `voice.py`); the speech-scale numbers come from [`data/style_profiles.json`](data/style_profiles.json) and the 130 character × scene cells in `idiolect/scene_length_targets.py`; the scene guidance comes from `idiolect/general_scenes.py` plus each package's `turn_logic/scenes.py`.

## 🛠️ Run the tooling

The quick-start section above used the installed package; this section covers the toolchain that ships with the repository (requires a clone):

```bash
py -X utf8 -m pip install -r requirements.txt
```

**One-command health check** (no LLM calls, no repository writes; a good pre-commit gate):

```bash
py -X utf8 tools/offline_smoke.py          # assembly + scenes + red lines + data + evaluation contract + same-chain self-test + gates + unit tests + zero-write check
py -X utf8 tools/offline_smoke.py --fast   # skip the self-test, gates and unit tests; results in seconds
```

**Code and comment style** (these are the two commands the CI lint job runs):

```bash
pip install "idiolect[lint]" && ruff check .   # code correctness and mechanical formatting (pinned version)
py -X utf8 tools/gates/style_gate.py           # Chinese docstrings / comment format / traditional characters / English-only comments
```

**Run a probe** (needs `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`):

```bash
py -X utf8 tools/probe/make_fixtures.py                                # generate placeholder fixtures
py -X utf8 tools/probe/probe_runner.py --label dry --dry-run --assemble --registry --runs 1
py -X utf8 tools/probe/probe_runner.py --label run1 --assemble --turn-logic --registry --runs 3 --intervention prompt
py -X utf8 tools/score/probe_report.py --label run1 --scenes crisis,comfort --cat 通用场景
py -X utf8 tools/probe/oob_probe.py --label oob1 --runs 2 --gate       # boundary-refusal probe (fails on a high-severity break)
py -X utf8 tools/probe/multiturn_probe.py --label mt1 --gate           # multi-turn style-drift probe
```

**Real-model batches for grounding evaluation** (explicitly paid: look at the estimate first, then confirm):

```bash
python -m idiolect run --suite spatiotemporal-core --capabilities spatiotemporal --dry-run   # estimate the call volume only, write placeholders
python -m idiolect run --suite spatiotemporal-core --capabilities spatiotemporal --yes --max-calls 12
python -m idiolect eval --suite spatiotemporal-core --responses <responses-from-previous-step> --capabilities spatiotemporal --html
python -m idiolect compare report/experiments/<experiment-A> report/experiments/<experiment-B>
```

Dry-run placeholders can never pass the formal gate; a response set records the fingerprint of the messages it was generated from, so scoring it after the prompt has changed flags it as a stale artifact.

**The evaluation clock**: characters react to the hour, so evaluation uses a clock pinned to daytime (`tools/mock_clock.py`; in-package evaluation reads the same `IDIOLECT_MOCK_NOW`). The command below only *prints* the environment-variable line; paste it into your shell for it to take effect:

```bash
py -X utf8 tools/mock_clock.py --set 2026-09-12T03:00:00+09:00
```

**Recompute every number from your own corpus** — you fetch the corpus yourself, see [`docs/02-corpus.md`](docs/02-corpus.md):

```bash
$env:IDIOLECT_CORPUS_DIR = "D:\corpus\mygo-gold"
py -X utf8 tools/distill/export_targets.py
py -X utf8 tools/distill/scene_char_baseline.py
py -X utf8 tools/distill/export_scene_targets.py     # rebuilds the 130 targets in idiolect/scene_length_targets.py
py -X utf8 tools/distill/export_profiles.py          # scoring profiles
py -X utf8 tools/distill/export_profiles.py --check  # verify shipped profiles against the corpus
```

## 🎭 Switching casts: the skills that chain the pipeline

The numbers above belong to these five. **The method itself is not tied to one work** — to run it on your own characters, the repository ships five skills that chain corpus acquisition → distillation → role packages → evaluation. Claude Code, or any agent that supports skills, loads them automatically, and a human can read them as an operations manual:

| Skill | What it does | What you get |
|---|---|---|
| [`.claude/skills/idiolect-corpus`](.claude/skills/idiolect-corpus/SKILL.md) | Normalise your own line collection into the required corpus format and split; choose character keys and list **every** table that must change with them | `raw/gold/{lang}.jsonl` + `gold_stats.json` |
| [`.claude/skills/idiolect-distill`](.claude/skills/idiolect-distill/SKILL.md) | Derive the five feature classes from the corpus | six `data/` JSON files + `idiolect/scene_length_targets.py` |
| [`.claude/skills/idiolect-cast`](.claude/skills/idiolect-cast/SKILL.md) | Build the role packages (canon / voice / turn_logic / voice_check) and register them in the four layers | `idiolect/characters/<key>/` |
| [`.claude/skills/idiolect-evaluate`](.claude/skills/idiolect-evaluate/SKILL.md) | Run the probe and the four-step scoring, grounding evaluation and the same-chain self-test; leave before/after evidence | `report/probe_*.jsonl`, `report/experiments/` |
| [`.claude/skills/idiolect-pipeline`](.claude/skills/idiolect-pipeline/SKILL.md) | Orchestrates the four: hand-off artifacts, the gate after each step, and what has to be written by hand | one reproducible end-to-end run |

The short version: **everything the corpus can tell you is automatic** — scene system, length targets, style profiles, tics, vocabularies — while **the canon profile, the voice manifest and the scene copy you have to write yourself**. The generic grounding contract and evaluation are not tied to a cast: the opaque `actor_a / scene_02 / evidence_17` and the five characters' names travel the same chain.

## ⚠️ Limits and caveats

> [!CAUTION]
> **No original script text is shipped.** The repository contains aggregate numbers only: length distributions, sentence counts, punctuation rates, tic frequencies, per-scene baselines (130 character-scene cells) and scoring profiles. Example-sentence fields were stripped before publication, and both the health check and the unit tests guard that line. Character and franchise rights belong to Bushiroad, Craft Egg and related rights holders; this project is unaffiliated. See [`NOTICE.md`](NOTICE.md).

> [!NOTE]
> **Scores are relative.** Scene fit, fidelity and composite are only for before/after comparison inside one batch; whether two batches can be compared is decided by the manifest's comparability rules, not by "they look about the same".

**What idiolect is not**: it is not a world simulator, not a memory database, and not a multimodal acquisition-and-fusion engine. It does not advance world state, does not retrieve production history, and does not open the host's database or keys; evidence is handed in explicitly by the caller, modality fields only identify the source, and images, audio and locations must already be text before they come in.

**Known and unsolved:**

- The cost of zero-example wording: after banning copyable example sentences, length agreement fell from 0.512 to 0.461. Both figures come from an older batch whose artifacts are not shipped; the trade was accepted on purpose.
- Taki's sentence openings are over-corrected: 39% of her original turns start with a bare noun, and this probe batch pushes that to 62% (`tools/score/_noun_initial.py <run-label>` prints the original baseline alongside the arm) — the direction overshot.
- Tomori's pause accounting: the reference frame drops silent turns, but her twelve-dot pause is content, not padding, so the metric loses either way.
- Fixture measurability: "what did you mean by that" needs a referable previous sentence, and placeholder fixtures have no history, so those cells are unreadable.
- Taki and Tomori still hold the two lowest scene fit scores of the five (0.386 / 0.365).
- grounding's mechanical matching only recognises the phrasings a task declares: any other rewording gets `needs_review`, and Chinese numeral readings and traditional characters are uncertified; every built-in replay is synthetic, and **no real-model grounding batch** ships with the repository yet.
- The built-in long-context matrix has only 4 families, far below the pre-registered minimum: it validates the chain and the measurement, and supports no conclusion that "the model does better/worse in long context"; token counts default to unknown.

**The corpus is a snapshot.** New official stories keep appearing, so a re-fetch yields different distributions. Every derived statistic records the script that generated it, so it can be rebuilt.

## 🗺️ Roadmap

What is already implemented and tested in this release is described above. The parts **not yet done** (outside the scope of this release, and not to be taken as finished):

- real-model grounding and long-context batches: they need the explicitly paid runner, and will run only once the pre-registered number of families is reached;
- a collection interface for human blind-judgement labels and inter-annotator agreement statistics (for now there is only merging and attribution for `labels/v1`);
- long-context comparisons across models and tokenizers (token counting is currently an optional plugin);
- text adapters for modalities such as images, audio and location (these belong upstream; idiolect only consumes evidence that is already text);
- certification and extension of the uncertified representation operators (Chinese numerals, traditional/simplified characters).

Details and versioning policy: [`docs/11-upgrade-guide.md`](docs/11-upgrade-guide.md).

## 📚 Docs

The methodology documents are written in Chinese, and each file stands alone. If you are not sure where to start, open [`docs/README.md`](docs/README.md) — it splits them into several reading paths by what you want to do, and carries a glossary.

| Document | Content |
|---|---|
| [`docs/00-methodology.md`](docs/00-methodology.md) | The method: the loop, invariants, evidence tiers, known residuals |
| [`docs/01-quickstart.md`](docs/01-quickstart.md) | Install and first five minutes |
| [`docs/02-corpus.md`](docs/02-corpus.md) | Corpus acquisition, cleaning, and the derived statistics inventory |
| [`docs/03-features.md`](docs/03-features.md) | The five feature classes: how they are computed, where they land, trigger discipline |
| [`docs/04-evaluation.md`](docs/04-evaluation.md) | The style axis: three-part metrics, pooling, gates, boundary refusal and multi-turn drift, evidence consistency, common misreadings |
| [`docs/05-tooling.md`](docs/05-tooling.md) | Tool reference, including the unified CLI, prompt / workspace dumps and the style gate |
| [`docs/06-lessons.md`](docs/06-lessons.md) | The pitfall list: what taught each constraint |
| [`docs/07-turn-logic-and-postprocessing.md`](docs/07-turn-logic-and-postprocessing.md) | turn_logic modules and voice_check post-processing |
| [`docs/08-context-workspace.md`](docs/08-context-workspace.md) | The context workspace: what surrounds the four layers and the evidence block in a real system |
| [`docs/09-evidence-grounding.md`](docs/09-evidence-grounding.md) | The evidence contract, the snapshot adapter, grounding tasks, the two axes, manifests and the same-chain self-test |
| [`docs/10-long-context-stress.md`](docs/10-long-context-stress.md) | Optional capability: long-context stress — pre-registered design, generators and measurement |
| [`docs/11-upgrade-guide.md`](docs/11-upgrade-guide.md) | Upgrade and migration, versioning policy, plugin development rules, evaluation boundaries, roadmap |

## ⚖️ Copyright, licence and disclaimer

### Code: MIT

`idiolect/`, `tools/`, `docs/`, `tests/`, `conftest.py` and `pyproject.toml` are released under **MIT** — see [`LICENSE`](LICENSE) (`Copyright (c) 2026 puresky`). Commercial use, modification and redistribution are fine; keep the copyright notice.

### Characters and the work: not ours

The character names, settings, world, story and music of *BanG Dream! It's MyGO!!!!!* belong to **Bushiroad / Craft Egg and the relevant rights holders**. This repository is an **unofficial fan-made technical project**:

- it is **not affiliated** with the rights holders in any way, and has no authorisation, sponsorship or endorsement;
- the character profiles (`idiolect/characters/*/canon.py`) were **compiled by the author from public material** for technical study — they are not official settings;
- the sample illustration ([`assets/readme/hero.png`](assets/readme/hero.png)) is **not official artwork**; it is fan usage, the characters remain the rights holders', and it will be removed on request.

### What is in the repository, and what is not

| In | Not in |
|---|---|
| Assembly and post-processing code; evidence-contract, grounding and long-context evaluation code; acquisition / distillation / scoring scripts; six **aggregate statistics** files under `data/`; synthetic, redacted evaluation tasks and replays; twelve methodology documents | Original game script, dialogue, lyrics, audio or game assets; any fine-tuned model weights; any sentence-level corpus; any real user conversations or production state |

The longest string in `data/` is a 56-character note field; the example-sentence fields of `scene_char_baseline.json` and `scene_stats.json` were stripped by `--no-exemplars` before publishing. Two checks guard that line: `tests/test_tooling_contracts.py::test_shipped_profiles_have_no_text` and the "数据.无原作文本" item in `offline_smoke.py`.

### If you fetch the corpus yourself

`tools/corpus/` is tooling only and **ships no data**. You are responsible for checking the source site's terms of service and the law where you live. This repository does not carry a copy of the HuggingFace dataset (`KomeijiForce/BanG_Dream_Events`), only the script that normalises it.

The complete statement is in [`NOTICE.md`](NOTICE.md).
