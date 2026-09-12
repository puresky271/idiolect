<p align="right">
  <strong>English</strong> · <a href="./README.md">简体中文</a>
</p>

<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="idiolect: make an AI character speak in character, and prove it got closer. On the right, one real assembled four-layer prompt and the reply it produced.">
</p>

**Make an AI character speak in character, and prove it got closer.**

This repository distills verifiable style features from a character's original lines (length, sentence count, verbal tics, forms of address, scene classification), puts them into the system prompt, and then checks whether the character actually sounds closer with a probe and a set of gates. No fine-tuning. No original script text is shipped, only derived statistics.

Three things you can do as soon as you clone it:

```bash
py -X utf8 tools/gates/dump_prompt.py --char 乐奈 --msg "你今天又想去哪找猫"   # the full prompt this character receives right now
py -X utf8 tools/offline_smoke.py                                            # one-command health check (no writes, no LLM)
py -X utf8 tools/probe/probe_runner.py --label run1 --assemble --turn-logic \
    --registry --cats 通用场景 --runs 3                                       # run a real probe
```

<p align="center">
  <img src="./assets/readme/section-01-what.svg" width="100%" alt="01 What it solves">
</p>

## What it solves

A general model playing a character drifts in the same direction every time: replies get long, empathy templates appear ("I completely understand how you feel"), a summary sentence lands at the end, and now and then the model talks about its own setup. None of this requires the model to fail. It is what the training objective produces. Character differentiation dies right there: if every character returns the same paragraph of comfort, they are the same character.

The method here turns "does it sound right" into measurable quantities, then iterates on those.

- **One reference frame**: the original lines of the same character in the same scene. Not general human speech statistics, not the character's global average. One character says 7 characters in a confession scene, another says 18 in the same scene, so a global median misleads both.
- **Length deviation finds suspects, it does not convict.** One character's replies run 5x the reference, half of it because her twelve-dot pause counts as characters. You have to read the reply.
- **Insufficient sample size means "no conclusion".** With 6 samples per cell, the median swings further than the effect. Measured: same scene, same prompt, one character's score moved from 0.551 to 0.350.
- **No meta-narrative in character-visible text.** Words like "corpus", "measured", "median", "baseline" inside a prompt invite the model to discuss its own construction.

Full method: [`docs/00-methodology.md`](docs/00-methodology.md) (Chinese).

<p align="center">
  <img src="./assets/readme/section-02-proof.svg" width="100%" alt="02 Real output">
</p>

## Real output

These numbers come from one real probe run, not from a design target:

```bash
py -X utf8 tools/probe/probe_runner.py --label repo_standalone \
    --assemble --turn-logic --registry --cats 通用场景 --runs 3
py -X utf8 tools/score/probe_report.py --label repo_standalone --scenes crisis,comfort --cat 通用场景
```

| Character | Replies | fidelity | Hard-rule V | Leak rate | Scene distill |
|---|---|---|---|---|---|
| Anon | 21 | 86.5 | 4.9% | 0% | 0.545 |
| Soyo | 21 | 85.4 | 0.0% | 0% | 0.532 |
| Taki | 21 | 82.4 | 0.0% | 0% | 0.386 |
| Tomori | 21 | 79.9 | 0.0% | 0% | 0.365 |
| Rana | 21 | 79.9 | 0.0% | 0% | 0.504 |

- Conditions: `deepseek-flash`, temperature 0.75, max_tokens 420, mock daytime clock (`2026-09-12T15:00:00+09:00`), 3 samples per cell, 105 replies, zero errors.
- Scene distill measures agreement with the original distribution for the same character and scene (median length, p90, sentence count). 1.0 means agreement; the mean is 0.466 over 35 cells. It is a **relative** score for before/after comparison inside one batch.
- Distinct replies within a cell: 93/105. Verbatim reuse of injected text: 1%, longest common substring 3 characters (that one copies a tic, not an example sentence).
- Leak rate covers think tags, inner monologue, speaker echo, and Chinese stage directions. All zero here.

The same fixtures with an empty system prompt instead of the four layers:

| Scene | Empty system | Four layers |
|---|---|---|
| Rana / comfort | "I completely understand how you feel. When pressure surges like a tide..." (380 chars) | "Mm." "Cat. Under the eaves." (median 10) |
| Rana / low mood | "When pressure surges and even breathing feels like effort..." (718 chars) | "Mm. ... A cat over there." |

This single cell is not evidence; sample sizes on both sides are tiny. What it shows is that **a probe has to assemble its own prompt**: the placeholder fixtures ship with an empty system, so without `--assemble` you are measuring a model with no character prompt at all.

<p align="center">
  <img src="./assets/readme/section-03-layers.svg" width="100%" alt="03 Prompt layers">
</p>

## Four prompt layers

Everything distilled lands in four layers, in a fixed order. Stable prefixes come first so they stay cacheable, dynamic blocks last so they never pollute the prefix:

| Layer | Content | Frequency | Characters for Rana / cat scene |
|---|---|---|---|
| `canon` | Who this character is, the long profile | static | 12223 |
| `voice` | Tone manifest: sentence patterns, tics, relationship differences, anti-template constraints | static | 1972 |
| `style_target` | Speaking scale: verifiable numbers for length, sentence count, sentence ending, first person | per turn (scene values when a scene matches) | 551 |
| `turn_logic` | This turn's scene or topic guidance | per turn (only when it matches) | 846 |

```python
from idiolect.assemble import build_messages
messages = build_messages("乐奈", "你今天又想去哪找猫")
```

These four layers are this repository's complete answer to "how do distilled features reach the prompt". A real system can put memory, world state, and schedules in front of them; those layers are unrelated to the method.

`dump_prompt.py` prints each layer so you can check the result, and `--phase before/after` leaves a diffable pair produced by the same script, the same input, and the same mock clock.

<p align="center">
  <img src="./assets/readme/section-04-start.svg" width="100%" alt="04 Get started">
</p>

## Get started

Python 3.11+. On Windows always call `py -X utf8`; a bare `python` may resolve to an interpreter without the dependencies.

```bash
py -X utf8 -m pip install -r requirements.txt
```

**Inspect a prompt** (no API key, no corpus):

```bash
py -X utf8 tools/gates/dump_prompt.py --all --matrix
py -X utf8 tools/gates/dump_prompt.py --char 灯 --msg "我一直在哭" --layers canon,voice
```

**Health check**:

```bash
py -X utf8 tools/offline_smoke.py          # assembly, scene coverage, trigger matrix, content red lines, data shapes, gates, unit tests, zero-write check
py -X utf8 tools/offline_smoke.py --fast   # skip gates and tests, about one second
```

**Run a probe** (needs `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`):

```bash
py -X utf8 tools/probe/make_fixtures.py
py -X utf8 tools/probe/probe_runner.py --label dry --dry-run --assemble --registry --runs 1
py -X utf8 tools/probe/probe_runner.py --label run1 --assemble --turn-logic --registry --runs 3
py -X utf8 tools/score/probe_report.py --label run1 --scenes crisis,comfort --cat 通用场景
```

**The evaluation clock** is pinned to mock daytime (`tools/mock_clock.py`). Characters react to the hour, so evaluating against the wall clock turns "what time is it" into a hidden variable:

```bash
py -X utf8 tools/mock_clock.py --set 2026-09-12T03:00:00+09:00
```

**Recompute from your own corpus** (you fetch the corpus yourself, see [`docs/02-corpus.md`](docs/02-corpus.md)):

```bash
$env:IDIOLECT_CORPUS_DIR = "D:\corpus\mygo-gold"
py -X utf8 tools/distill/export_targets.py
py -X utf8 tools/distill/scene_char_baseline.py
py -X utf8 tools/distill/export_scene_targets.py     # rebuilds the 130 targets in idiolect/scene_length_targets.py
py -X utf8 tools/distill/export_profiles.py          # scoring profiles
py -X utf8 tools/distill/export_profiles.py --check  # verify shipped profiles against the corpus
```

Probes run without a corpus too: the scoring profile ships with the repository (`data/style_profiles.json`), and the startup log prints which source it used.

<p align="center">
  <img src="./assets/readme/section-05-limits.svg" width="100%" alt="05 Limits and docs">
</p>

## Limits and things you should know

**No original script text is shipped.** The repository contains aggregate quantities only: length distributions, sentence counts, punctuation rates, tic frequencies, per-scene baselines (130 character-scene cells), and scoring profiles. Example-sentence fields were stripped before publication, and both `offline_smoke` and the unit tests guard that line. Character and franchise rights belong to Bushiroad, Craft Egg, and related rights holders; this project is unaffiliated. See [`NOTICE.md`](NOTICE.md).

**The metrics are relative.** Distill and fidelity scores compare before/after inside one batch. They do not travel across batches, models, fixtures, or clocks.

**Known and unsolved:**

- The cost of zero-example wording: after banning copyable example sentences, length agreement fell from 0.512 to 0.461. The trade was accepted on purpose.
- One character's sentence openings are over-corrected: 39% of her original turns start with a bare noun, while the current prompt pushes that to 95%.
- Silent-turn accounting: the reference frame drops silent turns, but one character's twelve-dot pause is content, not padding.
- Fixture measurability: "what did you mean by that" needs a referable previous sentence, and placeholder fixtures have no history, so those cells are unreadable.
- The two lowest scene distill scores are 0.386 and 0.365.

**The corpus is a snapshot.** New story content keeps appearing, so a re-fetch yields different distributions. Every derived statistic records the script that generated it, so it can be rebuilt.

## Docs

The methodology documents are written in Chinese. Each file stands alone.

| Document | Content |
|---|---|
| [`docs/00-methodology.md`](docs/00-methodology.md) | The method: the loop, four invariants, evidence tiers, known residuals |
| [`docs/01-quickstart.md`](docs/01-quickstart.md) | Install and first five minutes |
| [`docs/02-corpus.md`](docs/02-corpus.md) | Corpus acquisition, cleaning, and the derived statistics inventory |
| [`docs/03-features.md`](docs/03-features.md) | The five feature classes: how they are computed, where they land, trigger discipline |
| [`docs/04-evaluation.md`](docs/04-evaluation.md) | Metrics, pooling, gates, fixture design, common misreadings |
| [`docs/05-tooling.md`](docs/05-tooling.md) | Tool reference, including prompt dump, mock clock, and offline smoke |
| [`docs/06-lessons.md`](docs/06-lessons.md) | The pitfall list: what taught each constraint |

## License

Code is MIT, see [`LICENSE`](LICENSE). Character rights and the no-original-text policy are described in [`NOTICE.md`](NOTICE.md).
