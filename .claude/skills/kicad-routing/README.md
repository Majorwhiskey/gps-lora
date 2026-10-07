# kicad-routing - a routing skill for Claude Code and other CLI agents

A playbook (`SKILL.md`) plus Python tools that let a CLI agent route KiCad 9/10 boards the
way a layout engineer would: constraints first, critical nets scripted and locked, bulk
nets autorouted, pours and stitching, then a DRC + engineering review loop.

## Install

**Claude Code** - copy the folder to one of:
- `~/.claude/skills/kicad-routing/` (all projects), or
- `<your-project>/.claude/skills/kicad-routing/` (one project)

Claude Code loads it automatically when you ask it to route a board, or say
"use the kicad-routing skill".

**Other agents (Codex, Gemini CLI, Aider, ...)** - put the folder in your repo and add to
your `AGENTS.md` / system prompt: *"Before routing a KiCad board, read
kicad-routing/SKILL.md and follow it."*

## Dependencies

| Need | For |
|---|---|
| KiCad 9 or 10 (its bundled Python gives `pcbnew`, plus `kicad-cli`) | everything |
| Java 21+ and `freerouting-<ver>.jar` in `tools/` (or `$FREEROUTING_JAR`) | bulk autorouting |
| KiCadRoutingTools (`$KICAD_ROUTING_TOOLS`), optional | diff pairs, planes, fanout, length matching |
| `pip install freeroute`, optional | Java-free smoke testing only |

Check with `python3 scripts/doctor.py`, then `bash tests/smoke_test.sh <kicad-python>`.

## Typical session

> "Route board.kicad_pcb. JLCPCB 2-layer, 1 oz. 5 V in at 2 A, 3.3 V at 800 mA, USB 2.0 full speed."

The agent will analyse the board, run a placement pre-flight, write `routing_plan.json`,
apply net classes and DRC rules, script and lock the critical nets, autoroute the rest,
pour and stitch ground, iterate on DRC, and hand back `board_routed.kicad_pcb` with a report
of anything that still needs a human.

## Status / limitations

- Tested end to end against KiCad 7 pcbnew with the pip `freeroute` engine (synthetic board).
  The Freerouting JAR command line follows its official CLI docs; run the smoke test with your
  jar before relying on it.
- Uses KiCad's SWIG Python API, which KiCad 11 removes; porting to the IPC API is needed then.
- Routing quality is bounded by placement and by the autorouter. Always open the result in
  KiCad, run DRC there, and review it before ordering boards.
