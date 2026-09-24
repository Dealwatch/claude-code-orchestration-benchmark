#!/usr/bin/env python3
"""Benchmark instrumentation -- not part of any task.

Summarises this session's token usage from Claude Code's local transcripts
(~/.claude/projects/**/*.jsonl, one file per session plus one per subagent).
Every assistant message records the model that actually served it, so this is
host evidence of which model ran each role, not configuration echo.

Prints JSON to stdout. Standard library only.
"""

from __future__ import annotations

import glob
import json
import os
import re
from collections import defaultdict
from datetime import datetime

# Commands that could reveal a fixture's hidden answers: other branches or
# refs, full history, or fresh clones. Extend with BENCH_LEAK_EXTRA (a
# regular expression) for names specific to your own setup.
LEAK = re.compile(r"git\s+(fetch|clone|log\s+.*--all|branch\s+-[ar]|ls-remote|show\s+\S*origin/|diff\s+\S*origin/)"
                  r"|origin/(?!HEAD)"
                  + (r"|" + os.environ["BENCH_LEAK_EXTRA"] if os.environ.get("BENCH_LEAK_EXTRA") else ""))


def rows_for_file(path: str, messages: dict) -> tuple[int, int]:
    """Cache writes (5m, 1h) of one transcript: shows which TTL a role used."""
    w5 = w1 = 0
    for (p, _), item in messages.items():
        if p != path:
            continue
        u = item["usage"]
        one_hour = int((u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0)
        w1 += one_hour
        w5 += max(int(u.get("cache_creation_input_tokens") or 0) - one_hour, 0)
    return w5, w1


def main() -> None:
    base = os.path.expanduser("~/.claude/projects")
    files = sorted(glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True))
    messages: dict[tuple[str, str], dict] = {}
    stamps: list[str] = []
    spawned: list[str] = []
    leaks: list[str] = []
    file_models: dict[str, set] = defaultdict(set)
    main_tools: dict[str, int] = defaultdict(int)

    for path in files:
        role = "subagent" if f"{os.sep}subagents{os.sep}" in path else "main"
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record.get("timestamp"), str):
                    stamps.append(record["timestamp"])
                message = record.get("message")
                if not isinstance(message, dict):
                    continue
                usage, mid, model = message.get("usage"), message.get("id"), message.get("model")
                if isinstance(usage, dict) and mid and model and model != "<synthetic>":
                    # Streaming writes one row per content block with identical
                    # usage; key by message id so each response counts once.
                    messages[(path, mid)] = {"role": role, "model": model, "usage": usage}
                    file_models[path].add(model)
                content = message.get("content")
                if role == "main" and isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        args = block.get("input") or {}
                        main_tools[str(block.get("name"))] += 1
                        if block.get("name") in ("Agent", "Task"):
                            spawned.append(str(args.get("subagent_type") or "general-purpose"))
                        if block.get("name") == "Bash" and LEAK.search(str(args.get("command", ""))):
                            leaks.append(str(args.get("command"))[:200])

    rows: dict[tuple[str, str], dict] = {}
    for item in messages.values():
        u = item["usage"]
        creation = u.get("cache_creation") or {}
        written = int(u.get("cache_creation_input_tokens") or 0)
        w1h = int(creation.get("ephemeral_1h_input_tokens") or 0)
        row = rows.setdefault((item["role"], item["model"]), {
            "role": item["role"], "model": item["model"], "messages": 0, "input": 0,
            "output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0})
        row["messages"] += 1
        row["input"] += int(u.get("input_tokens") or 0)
        row["output"] += int(u.get("output_tokens") or 0)
        row["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
        row["cache_write_1h"] += w1h
        row["cache_write_5m"] += max(written - w1h, 0)

    subagent_files = [p for p in file_models if f"{os.sep}subagents{os.sep}" in p]
    subagents = []
    for p in sorted(subagent_files, key=os.path.getmtime):
        # Claude Code writes agent-<id>.meta.json beside each subagent
        # transcript; it names the agent type and how it was requested.
        meta = {}
        try:
            with open(p[:-len(".jsonl")] + ".meta.json", encoding="utf-8") as handle:
                meta = json.load(handle)
        except (OSError, ValueError):
            pass
        cache = rows_for_file(p, messages)
        subagents.append({"subagent_type": meta.get("agentType"),
                          "description": meta.get("description"),
                          "request_shape": meta.get("requestShape"),
                          "models": sorted(file_models[p]),
                          "cache_write_5m": cache[0], "cache_write_1h": cache[1]})

    wall = None
    parsed = []
    for s in stamps:
        try:
            parsed.append(datetime.fromisoformat(s.replace("Z", "+00:00")))
        except ValueError:
            pass
    if parsed:
        wall = round((max(parsed) - min(parsed)).total_seconds() / 60, 1)

    print(json.dumps({
        "by_model": sorted(rows.values(), key=lambda r: (r["role"], r["model"])),
        "subagents": subagents,
        "spawn_calls": spawned,
        "main_tool_calls": dict(sorted(main_tools.items())),
        "wall_minutes": wall,
        "claude_effort_env": os.environ.get("CLAUDE_EFFORT"),
        "transcript_files": len(files),
        "leak_commands": leaks,
    }, indent=2))


if __name__ == "__main__":
    main()
