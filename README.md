# zqxbase

Claude Code plugin marketplace — structured workflows, meeting intelligence, and productivity tools.

## Install

```bash
# Add the marketplace
/plugin marketplace add zhuqingxun/zqxbase

# Install plugins (pick what you need)
/plugin install rpiv-loop@zqxbase
/plugin install mint@zqxbase
/plugin install toolbox@zqxbase
```

## Plugins

### rpiv-loop

Structured development workflow: **Requirements → Plan → Implementation → Validation**.

Provides a complete set of commands for managing the full development lifecycle, including brainstorming, PRD creation, feature planning, execution, and multi-dimensional validation (code review, audit, delivery reports).

**Key commands**: `/rpiv_loop:brainstorm`, `/rpiv_loop:plan-feature`, `/rpiv_loop:execute`, `/rpiv_loop:validation:code-review`

### mint

**MINT (Meeting Intelligence)** — audio-to-insights pipeline.

Transforms meeting recordings into structured outputs through 4 stages:
1. **Transcribe** — ASR with speaker diarization
2. **Refine** — cross-validated proofreading
3. **Polish** — editorial documents, structured analysis, key quotes
4. **Extract** — summaries, speaker analysis, action items, decisions

**Key commands**: `/mint`, `/mint:transcribe`, `/mint:refine`, `/mint:polish`, `/mint:extract`

### toolbox

Standalone productivity skills:

| Skill | Description |
|-------|-------------|
| `/toolbox:reflect` | Session retrospective — extract reusable lessons from the current conversation |
| `/toolbox:challenge` | Red-Blue adversarial review — structured attack/defense on plans and decisions |
| `/toolbox:whatsnew` | Claude Code changelog viewer — check release notes by version |

## License

MIT
