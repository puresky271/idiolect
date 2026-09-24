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

## 📦 What you actually get

| You get | Concretely |
|---|---|
| **A drop-in assembly library** | `pip install .` then `from idiolect.assemble import build_messages` returns the four-layer prompt. **Zero third-party runtime dependencies** — openai / numpy / jieba are only needed for probing and distillation |
| **An evaluation loop that proves "closer"** | Probe → (distribution fit / within-cell repetition / verbatim-copy audit) → multi-arm pooling → power estimate. Two dedicated probes cover boundary refusal and multi-turn drift, and an evidence gate checks fact consistency. The table below is one real run of 105 replies |
| **Six mechanical gates plus a prompt-diff gate** | Prompt edits should not rest on vibes: one `offline_smoke.py` run covers assembly, scene coverage, trigger matrix, content red lines, data shape, the gates and a zero-write check |
| **Tooling that transfers to another work** | 67 scripts: acquisition and cleaning, corpus splitting, scene discovery, tic distillation, length-target export, probing and scoring. The method is not tied to one show — point it at another cast and re-run |
| **Ready-made character data (aggregates only)** | 26 scenes (13 general + 13 character-specific), 130 character × scene length targets, 114 per-scene tic cells, style profiles for five characters |
| **Nine methodology documents** | Where the corpus comes from, how each feature class is computed and landed, how to evaluate, and the pitfalls already paid for |

### A portable roleplay Skill

Copy the complete [mygo-five-roleplay folder](skills/mygo-five-roleplay/SKILL.md) into your agent's skills directory. Claude/Codex can then read the bundled character materials and reply directly, without Python or an API key. Select a member, or name her together with your topic; say "exit roleplay" to return to the assistant. Character directories are optional and loaded on selection.

These static materials share the library's sources but do not execute its dynamic routing, session state or post-processing. A good experience does not certify quality — evaluation and methodology remain central. See the [installation and export guide](docs/01-quickstart.md#先体验五人-skill).

Suggested path: try the Skill first to feel how the five differ on the same question; run `py -X utf8 tools/gates/dump_prompt.py --all --matrix` to see which layer the difference comes from; then return to checkable evidence with `py -X utf8 tools/score/probe_report.py --label <label> --scenes crisis,comfort`.

### Watch the demo, then inspect the evidence

[![Native-color Claude Code terminal recording: Rana](assets/readme/roleplay-demo.gif)](assets/readme/roleplay-demo.mp4)

**[Play / download the clip](assets/readme/roleplay-demo.mp4)** · [Static preview](assets/readme/roleplay-poster.png) · [Transcript and provenance](assets/readme/roleplay-transcript.json)

This **25-second** clip records **Claude Code** directly in Windows Terminal, preserving its native colors and showing a real reply from Rana on **DeepSeek-v4-pro[1m]**. Only the idle stretches at both ends were trimmed; generation was not sped up. The Skill and Rana's materials were explicitly loaded, and the input was supplied as the initial message. This does not test automatic Skill discovery or multi-turn stability. The other four members remain available in the Skill.

![Offline evaluation overview: filters, missing conditions and character metrics](assets/readme/evaluation-overview.png)

The overview keeps the warnings about missing conditions in historical batches. Below, Rana's comfort scene opens into the original and the cleaned replies; inputs absent from old records stay unknown.

![Rana comfort scene: diagnostics and original versus cleaned replies](assets/readme/evaluation-evidence.png)

Run `py -X utf8 tools/score/report_html.py --labels <label>` on your own batch and open `report/evaluation.html` to filter and inspect the evidence. These screenshots come from the historical `repo_standalone` batch, a separate experiment from the host demo above. See the [evaluation guide](docs/04-evaluation.md).

## 🚀 Quick start

**First, get it — pick one of four routes:**

| Route | One command | Notes |
|---|---|---|
| **Let an agent do it** | paste the prompt below into your coding agent | least work: it clones, installs and runs the self-check itself |
| **uv (one line, nothing left behind)** | `uvx --from git+https://github.com/puresky271/idiolect idiolect prompt Rana "你今天又想去哪找猫"` | see a prompt immediately; no clone, no environment to set up |
| **pip as a library** | `pip install git+https://github.com/puresky271/idiolect` | use it as a dependency; zero third-party runtime deps |
| **Files only** | `npx degit puresky271/idiolect idiolect` or `git clone --depth 1 https://github.com/puresky271/idiolect` | you want the toolchain or the source |

Prompt for your agent (Claude Code, Codex, anything similar):

> Set up https://github.com/puresky271/idiolect for me: clone it, read `AGENTS.md`, run `python bootstrap.py`, then show me the self-check result and the five characters' complete prompts (`py -X utf8 tools/gates/dump_prompt.py --all --matrix`). After that I want to switch to my own characters, following `.claude/skills/idiolect-pipeline/`.

**Then run this from the repository root** (Python 3.11+):

```bash
pip install .                                        # zero third-party runtime dependencies
python -m idiolect list                              # the five built-in characters
python -m idiolect prompt 乐奈 "你今天又想去哪找猫"     # the full system prompt for this message
python -m idiolect showcase "我今天有点撑不住了"        # side-by-side five-character view (no model call)
python -m idiolect chat 乐奈 "你今天又想去哪找猫"       # one real chat turn (env vars below)
```

To set up the toolchain as well, one command is enough — it creates `.venv`, installs the requirements, runs the `offline_smoke` self-check and prints one character's per-layer sizes:

```bash
python bootstrap.py
```

On Windows, prefer `py -X utf8` over a bare `python`, which may resolve to an interpreter without the dependencies. `chat` talks to any OpenAI-compatible endpoint: set `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` and `pip install "idiolect[llm]"`.

From code:

```python
from idiolect.assemble import build_messages
messages = build_messages("乐奈", "你今天又想去哪找猫")   # ready to send to the model
```

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

If every character answers with the same paragraph of comfort, there is no character left. So the whole method fits in one sentence: **turn "does it sound right" into a few measurable numbers, then iterate on the numbers**.

- **Compare only against the same character in the same scene.** Not against general human speech, and not against the character's global average.
- **Numbers raise suspects; they don't convict.** One character's output runs 5x the reference length, half of it because her ellipses count as characters — you have to read the reply to judge.
- **Small samples mean "no conclusion".** With 6 replies per cell, the same scene and prompt can swing one character's score from 0.551 to 0.350 — more than the effect being measured.
- **No meta vocabulary in character-visible text.** Words like "corpus", "median" or "baseline" inside a prompt invite the model to discuss its own construction.

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
- **Scene fit** measures how closely a reply's length and sentence count match the original same-character-same-scene distribution; 1.0 is full agreement, and this batch averages 0.466 over 35 cells. It is a **relative** score for before/after comparison inside one batch — not comparable across models, fixtures or clocks.
- Distinct replies within a cell: 93/105. Verbatim reuse of prompt text: 1%, and the 3 copied characters were a verbal tic, not an example sentence.
- Leak rate covers thinking tags, inner monologue, speaker echo and Chinese stage directions — all 0 here.

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

`tools/gates/dump_prompt.py` prints each layer for inspection. Use `--phase current` both before and after a code change, keeping inputs, clock and flags identical and saving to separate output directories; the before/after modes are switch ablations.

**What surrounds the four layers in a real system?** In a complete chat system the model also needs to know what time it is, where the character is, what was just being discussed, and what the user mentioned last week. That context is organised as a **workspace**: a dozen candidate sources are collected, scored, ranked, trimmed to a budget, then assembled in a fixed layer order — and the four layers sit in the `persona` slot. The repository distils that skeleton (`idiolect/workspace.py`, zero dependencies); see [`docs/08-context-workspace.md`](docs/08-context-workspace.md):

```python
from idiolect.workspace import build_workspace_messages
messages = build_workspace_messages(
    "乐奈", "你今天又想去哪找猫",
    blocks=[("current_state", "乐奈在 RiNG 排练室，下午没课"),
            ("fact_workspace", "用户上周提过想养猫")],
    execution_packet="【本轮执行】回复 ≤19 字",   # appended to this turn's user message
)
```

## 📖 The five characters' prompts ship complete

This is not "here is a method, go configure your own cast". **All four layers for all five members ship with the repository**: the long canon profile, the voice manifest, the speech-scale numbers and the scene guidance. Nothing is truncated, nothing is elided, and you need neither an API key nor a corpus to read them.

```bash
# With the package installed (no clone, no key, no corpus needed)
python -m idiolect prompt Rana "你今天又想去哪找猫"                     # the complete system prompt for this message
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

The text of every layer is in the repository and readable verbatim: `canon` and `voice` live in `idiolect/characters/*/` (`canon.py` / `voice.py`); the speech-scale numbers come from [`data/style_profiles.json`](data/style_profiles.json) and the 130 character × scene cells in `idiolect/scene_length_targets.py`; the scene guidance comes from `idiolect/general_scenes.py` plus each package's `turn_logic/scenes.py`. To see what a prompt edit changed, dump with `--phase current` before and after, save to separate directories, and inspect the diff.

## 🛠️ Run the tooling

The quick-start section above used the installed package; this section covers the toolchain that ships with the repository (requires a clone):

```bash
py -X utf8 -m pip install -r requirements.txt
```

**Inspect prompts** (no API key, no corpus):

```bash
py -X utf8 tools/gates/dump_prompt.py --all --matrix        # five characters x four messages that hit different layers
py -X utf8 tools/gates/dump_prompt.py --char 灯 --msg "我一直在哭" --layers canon,voice
```

**One-command health check** (no LLM calls, no repository writes; a good pre-commit gate):

```bash
py -X utf8 tools/offline_smoke.py          # assembly, scene coverage, trigger matrix, content red lines, data shapes, gates, unit tests, zero-write check
py -X utf8 tools/offline_smoke.py --fast   # skip gates and tests, about one second
```

**Run a probe** (needs `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`):

```bash
py -X utf8 tools/probe/make_fixtures.py                                # generate placeholder fixtures
py -X utf8 tools/probe/probe_runner.py --label dry --dry-run --assemble --registry --runs 1
py -X utf8 tools/probe/probe_runner.py --label run1 --assemble --turn-logic --registry --runs 3
py -X utf8 tools/score/probe_report.py --label run1 --scenes crisis,comfort --cat 通用场景
py -X utf8 tools/probe/oob_probe.py --label oob1 --runs 2 --gate       # boundary-refusal probe (fails on a high-severity break)
py -X utf8 tools/probe/multiturn_probe.py --label mt1 --gate           # multi-turn style-drift probe
```

**The evaluation clock**: characters react to the hour — 3 AM answers differ from afternoon answers — so evaluation uses a clock pinned to daytime (`tools/mock_clock.py`) instead of letting "what time is it" become a hidden variable. The command below only *prints* the environment-variable line; a child process cannot change your shell, so paste it into your shell for it to take effect:

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

Probes also run without a corpus: the scoring profile ships with the repository (`data/style_profiles.json`), and the startup log prints which source it used.

## 🎭 Switching casts: the skills that chain the pipeline

The numbers above belong to these five. **The method itself is not tied to one work** — to run it on your own characters, the repository ships five skills that chain corpus acquisition → distillation → role packages → evaluation. An agent that understands Claude Code skills loads them automatically, and a human can read them as an operations manual:

| Skill | What it does | What you get |
|---|---|---|
| [`.claude/skills/idiolect-corpus`](.claude/skills/idiolect-corpus/SKILL.md) | Normalise your own line collection into the required corpus format and split; choose character keys and list **every** table that must change with them | `raw/gold/{lang}.jsonl` + `gold_stats.json` |
| [`.claude/skills/idiolect-distill`](.claude/skills/idiolect-distill/SKILL.md) | Derive the five feature classes from the corpus | six `data/` JSON files + `idiolect/scene_length_targets.py` |
| [`.claude/skills/idiolect-cast`](.claude/skills/idiolect-cast/SKILL.md) | Build the role packages (canon / voice / turn_logic / voice_check) and register them | `idiolect/characters/<key>/` |
| [`.claude/skills/idiolect-evaluate`](.claude/skills/idiolect-evaluate/SKILL.md) | Run the probe and the four-step scoring, leave before/after evidence | `report/probe_*.jsonl` + reports |
| [`.claude/skills/idiolect-pipeline`](.claude/skills/idiolect-pipeline/SKILL.md) | Orchestrates the four: hand-off artifacts, the gate after each stage, and what has to be written by hand | one reproducible end-to-end run |

The short version: **everything the corpus can tell you is automatic** — scene system, length targets, style profiles, tics, vocabularies — while **the canon profile, the voice manifest and the scene copy you have to write yourself**. The corpus is a snapshot of event stories; everyday props are simply absent from it, and no amount of statistics will tell you who the character is. `idiolect-pipeline` carries the automatic-versus-authored table.

## ⚠️ Limits and caveats

> [!CAUTION]
> **No original script text is shipped.** The repository contains aggregate numbers only: length distributions, sentence counts, punctuation rates, tic frequencies, per-scene baselines (130 character-scene cells) and scoring profiles. Example-sentence fields were stripped before publication, and both the health check and the unit tests guard that line. Character and franchise rights belong to Bushiroad, Craft Egg and related rights holders; this project is unaffiliated. See [`NOTICE.md`](NOTICE.md).

> [!NOTE]
> **Scores are relative.** Scene fit, fidelity and composite compare before/after inside one batch. They do not travel across batches, models, fixtures or clocks.

**Known and unsolved:**

- The cost of zero-example wording: after banning copyable example sentences, length agreement fell from 0.512 to 0.461. Both figures come from an older batch whose artifacts are not shipped; the trade was accepted on purpose.
- Taki's sentence openings are over-corrected: 39% of her original turns start with a bare noun, and the current arm pushes that to 62% (`tools/score/_noun_initial.py <run-label>` prints the original baseline alongside the arm) — the direction overshot.
- Tomori's pause accounting: the reference frame drops silent turns, but her twelve-dot pause is content, not padding, so the metric loses either way.
- Fixture measurability: "what did you mean by that" needs a referable previous sentence, and placeholder fixtures have no history, so those cells are unreadable.
- Taki and Tomori still hold the two lowest scene fit scores (0.386 / 0.365).

**The corpus is a snapshot.** New official stories keep appearing, so a re-fetch yields different distributions. Every derived statistic records the script that generated it, so it can be rebuilt.

## 📚 Docs

The methodology documents are written in Chinese, and each file stands alone. If you are not sure where to start, open [`docs/README.md`](docs/README.md) — it splits the nine documents into three reading paths by intent and carries a short glossary (turn / scene / the four layers / probe / fixture / arm / gate).

| Document | Content |
|---|---|
| [`docs/00-methodology.md`](docs/00-methodology.md) | The method: the loop, four invariants, evidence tiers, known residuals |
| [`docs/01-quickstart.md`](docs/01-quickstart.md) | Install and first five minutes |
| [`docs/02-corpus.md`](docs/02-corpus.md) | Corpus acquisition, cleaning, and the derived statistics inventory |
| [`docs/03-features.md`](docs/03-features.md) | The five feature classes: how they are computed, where they land, trigger discipline |
| [`docs/04-evaluation.md`](docs/04-evaluation.md) | Metrics, pooling, gates, boundary refusal and multi-turn drift, evidence consistency, fixture design, common misreadings |
| [`docs/05-tooling.md`](docs/05-tooling.md) | Tool reference, including prompt dump, mock clock and offline smoke |
| [`docs/06-lessons.md`](docs/06-lessons.md) | The pitfall list: what taught each constraint |
| [`docs/07-turn-logic-and-postprocessing.md`](docs/07-turn-logic-and-postprocessing.md) | Building turn_logic modules and voice_check post-processing: wiring, gates, acceptance |
| [`docs/08-context-workspace.md`](docs/08-context-workspace.md) | The context workspace: what surrounds the four layers in a real chat system |

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
| Assembly and post-processing code; corpus, distillation and scoring scripts; six **aggregate statistics** files under `data/` (length quantiles, sentence counts, punctuation rates, tic frequencies, per-scene baselines, scoring profiles); nine methodology documents | Original game script, dialogue, lyrics, audio or game assets; any fine-tuned model weights; any sentence-level corpus |

The longest string in `data/` is a 56-character note field; the example-sentence fields of `scene_char_baseline.json` and `scene_stats.json` were stripped by `--no-exemplars` before publishing. Two checks guard that line: `tests/test_tooling_contracts.py::test_shipped_profiles_have_no_text` and the "数据.无原作文本" item in `offline_smoke.py`.

### If you fetch the corpus yourself

`tools/corpus/` is tooling only and **ships no data**. You are responsible for checking the source site's terms of service and the law where you live. This repository does not carry a copy of the HuggingFace dataset (`KomeijiForce/BanG_Dream_Events`), only the script that normalises it.

The complete statement is in [`NOTICE.md`](NOTICE.md).
