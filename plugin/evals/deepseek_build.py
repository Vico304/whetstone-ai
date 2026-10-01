#!/usr/bin/env python3
"""Drive the learn skill on a hosted model until the outline pause, under a token cap.

The skill is host-neutral (skills/learn/references/hosts.md): a host model reads SKILL.md, reads the
stage files it points to, writes the course files and runs the scripts. This driver plays that host for
a model behind an HTTP API. It copies the skill and the materials into a sandbox, exposes four tools
(list_dir, read_file, write_file, run_command) confined to that sandbox, answers the model's questions
to the learner with one fixed reply, and stops when a parseable lesson-plan.json with an outline.md beside it
exists and the model hands the turn back (the outline pause), or when a limit is reached. Every request is booked in ledger.json with
input, output, cache-hit and cache-miss tokens kept apart.

The model call sits behind ``ModelClient``; ``DeepSeekClient`` talks to api.deepseek.com and reads the
key only from the ``DEEPSEEK_API_KEY`` environment variable (never printed, never written, no env files).
Another backend (a server in front of the model) implements ``complete`` and plugs in the same way.
``--dry-run`` estimates the usage without any request.

Exit codes: 0 outline reached (or dry-run done), 1 stopped early (cap, limits, model error), 2 bad input.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN_ROOT.parent
SKILL_SOURCE = PLUGIN_ROOT / "skills" / "learn"
API_URL = "https://api.deepseek.com/chat/completions"
KEY_ENV = "DEEPSEEK_API_KEY"
# CNY per million tokens: cache hit, cache miss, output. deepseek-chat list price of 2025-09, kept as a placeholder:
# the V4 models listed by /models in 2026-09 may cost otherwise; pass --price with the current list price.
DEFAULT_PRICE = (0.2, 2.0, 3.0)
DEFAULT_REPLY = "你定，按默认值继续。"
# Output cap per reply, thinking included. 8192 was cut twice in 2026-09-30 by thinking alone; the API took 16384.
DEFAULT_MAX_OUTPUT = 16384
CUT_WITH_OUTPUT = "（宿主提示）上一条回复超出输出上限被截断；请把长文件分几次 write_file，第二次起 append=true。"
# A cut reply with neither text nor a tool call is dropped from the context (only the transcript keeps it): its
# thinking would ride along in every later request, and it wrote nothing to build on.
CUT_THINKING_ONLY = ("（宿主提示）上一条回复的思考占满了输出上限，一个字都没写出来，已丢弃。不要在思考里起草整份文件："
                     "先把节骨架（id、标题、问题、方案）写进文件，再逐节补细节。")
READ_LIMIT = 60000
TOOL_OUTPUT_LIMIT = 20000

TOOLS = [
    {"type": "function", "function": {
        "name": "list_dir", "description": "List a directory (absolute path, or relative to the workspace).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "read_file", "description": f"Read a text file; at most {READ_LIMIT} characters per call, use offset to continue.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "offset": {"type": "integer", "description": "character offset, default 0"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Write a text file (parents are created). append=true adds to the end, for files too long for one reply.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}, "append": {"type": "boolean"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "run_command", "description": "Run a command without a shell, cwd = workspace. Allowed: python3 <skill scripts>/<name>.py args..., or date args...",
        "parameters": {"type": "object", "properties": {"argv": {"type": "array", "items": {"type": "string"}}},
                       "required": ["argv"]}}},
]


class InputError(Exception):
    """Bad case file or arguments (exit 2)."""


class ModelError(Exception):
    """The model backend failed (exit 1). Messages never contain the key."""


# ---------------------------------------------------------------- model backends

class Reply:
    def __init__(self, message: dict, usage: dict, finish_reason: str = "stop"):
        self.message, self.usage, self.finish_reason = message, usage, finish_reason


class ModelClient:
    """One chat-completion call with tools. Implement ``complete`` to add a backend (e.g. a server)."""

    name = "abstract"

    def complete(self, messages: list[dict], tools: list[dict], max_tokens: int) -> Reply:
        raise NotImplementedError


class DeepSeekClient(ModelClient):
    name = "deepseek"

    def __init__(self, model: str = "deepseek-flash", url: str = API_URL, timeout: float = 300.0, retries: int = 2):
        key = os.environ.get(KEY_ENV, "")
        if not key.strip():
            raise ModelError(f"{KEY_ENV} is not set in the environment")
        self._key = key.strip()
        self.model, self.url, self.timeout, self.retries = model, url, timeout, retries
        self.http_attempts = 0

    def __repr__(self) -> str:  # keep the key out of any accidental print
        return f"DeepSeekClient(model={self.model!r})"

    def complete(self, messages, tools, max_tokens):
        body = json.dumps({"model": self.model, "messages": messages, "tools": tools,
                           "max_tokens": max_tokens, "stream": False}).encode("utf-8")
        for attempt in range(self.retries + 1):
            self.http_attempts += 1
            request = urllib.request.Request(self.url, data=body, method="POST", headers={
                "Content-Type": "application/json", "Authorization": f"Bearer {self._key}"})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300].replace(self._key, "***")
                if exc.code in (429, 500, 502, 503) and attempt < self.retries:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise ModelError(f"HTTP {exc.code}: {detail}") from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt < self.retries:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise ModelError(f"network: {type(exc).__name__}: {exc}") from None
        choice = data["choices"][0]
        return Reply(message=choice["message"], usage=data.get("usage") or {}, finish_reason=choice.get("finish_reason") or "")


class ScriptedClient(ModelClient):
    """Replays replies from a JSON list of {message, usage, finish_reason}; for tests and offline runs."""

    name = "scripted"

    def __init__(self, path: Path):
        try:
            self.replies = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"cannot read replies {path}: {exc}") from None
        self.calls: list[list[dict]] = []

    def complete(self, messages, tools, max_tokens):
        self.calls.append(json.loads(json.dumps(messages)))
        if len(self.calls) > len(self.replies):
            raise ModelError("scripted replies exhausted")
        item = self.replies[len(self.calls) - 1]
        return Reply(item["message"], item.get("usage", {}), item.get("finish_reason", "stop"))


# ---------------------------------------------------------------- tokens and cost

_CJK = re.compile(r"[　-〿㐀-䶿一-鿿＀-￯]")


def estimate_tokens(text: str) -> int:
    """DeepSeek's published rule of thumb: about 0.6 token per CJK character, 0.3 per other character."""
    cjk = len(_CJK.findall(text))
    return int(round(cjk * 0.6 + (len(text) - cjk) * 0.3))


def cost_cny(hit: int, miss: int, out: int, price=DEFAULT_PRICE) -> float:
    return round((hit * price[0] + miss * price[1] + out * price[2]) / 1_000_000, 4)


class Ledger:
    # Plain classes, not dataclasses: the tests load this file without registering it in sys.modules.
    def __init__(self, cap: int):
        self.cap, self.rows = cap, []

    @property
    def totals(self) -> dict:
        keys = ("input", "output", "cache_hit", "cache_miss")
        total = {k: sum(r[k] for r in self.rows) for k in keys}
        total["requests"] = len(self.rows)
        total["all"] = total["input"] + total["output"]
        return total

    def book(self, usage: dict, finish_reason: str, tool_calls: int, seconds: float, reasoning_chars: int = 0,
             in_context: bool = True) -> dict:
        prompt = int(usage.get("prompt_tokens") or 0)
        hit = int(usage.get("prompt_cache_hit_tokens") or 0)
        miss = int(usage.get("prompt_cache_miss_tokens") if usage.get("prompt_cache_miss_tokens") is not None else prompt - hit)
        details = usage.get("completion_tokens_details") or {}
        row = {"n": len(self.rows) + 1, "input": prompt, "output": int(usage.get("completion_tokens") or 0),
               "cache_hit": hit, "cache_miss": miss, "finish_reason": finish_reason, "tool_calls": tool_calls,
               "reasoning_chars": reasoning_chars, "reasoning_tokens": details.get("reasoning_tokens"),
               "in_context": in_context, "seconds": round(seconds, 1)}
        self.rows.append(row)
        return row


# ---------------------------------------------------------------- case and sandbox

def load_case(args) -> dict:
    if args.case:
        try:
            case = json.loads(Path(args.case).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"cannot read case {args.case}: {exc}") from None
        if not isinstance(case, dict):
            raise InputError("case root must be an object")
    else:
        try:
            listing = json.loads((PLUGIN_ROOT / "evals" / "materials.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"cannot read materials.json: {exc}") from None
        found = [m for m in listing.get("materials", []) if m.get("id") == args.material_id]
        if not found:
            raise InputError(f"no material {args.material_id!r} in evals/materials.json")
        item = found[0]
        case = {"id": item["id"], "materials_root": str(REPO_ROOT), "materials": item["paths"],
                "request": f"用 learn 技能把 materials/ 下的材料建成课程（build 模式，不进入教学）。学习目标：{item['learning_goal']}"}
    for key in ("id", "materials_root", "materials", "request"):
        if not case.get(key):
            raise InputError(f"case is missing {key!r}")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", str(case["id"])):
        raise InputError("case id may only use letters, digits, '.', '_' and '-'")
    root = Path(case["materials_root"])
    for rel in case["materials"]:
        if not (root / rel).is_file():
            raise InputError(f"material not found: {root / rel}")
    if case.get("profile") and not Path(case["profile"]).is_file():
        raise InputError(f"profile not found: {case['profile']}")
    return case


class Sandbox:
    def __init__(self, root: Path):
        self.root = root

    @property
    def skill(self) -> Path:
        return self.root / "skill" / "learn"

    @property
    def materials(self) -> Path:
        return self.root / "materials"

    @property
    def workspace(self) -> Path:
        return self.root / "workspace"

    def build(self, case: dict) -> None:
        if self.root.exists():
            raise InputError(f"sandbox already exists (runs never overwrite): {self.root}")
        shutil.copytree(SKILL_SOURCE, self.skill, ignore=shutil.ignore_patterns("__pycache__"))
        for rel in case["materials"]:
            target = self.materials / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(case["materials_root"]) / rel, target)
        self.workspace.mkdir(parents=True)
        if case.get("profile"):
            shutil.copy2(case["profile"], self.workspace / "learner-profile.md")

    def resolve(self, raw: str) -> Path:
        path = Path(raw)
        path = (path if path.is_absolute() else self.workspace / path).resolve()
        if path != self.root.resolve() and self.root.resolve() not in path.parents:
            raise PermissionError(f"outside the sandbox: {raw}")
        return path

    def writable(self, path: Path) -> bool:
        protected = (self.skill.resolve(), *(p.resolve() for p in self.materials.rglob("*") if p.is_file()
                                             and "whetstone" not in p.relative_to(self.materials).parts))
        return not any(path == p or p in path.parents for p in protected)

    def lesson_plans(self) -> list[Path]:
        found = []
        for base in (self.workspace, self.materials):
            found += sorted(base.rglob("lesson-plan.json"))
        return found

    def outline_ready(self) -> bool:
        """A parseable lesson-plan.json with an outline.md beside it: the outline stage wrote its two files."""
        for plan in self.lesson_plans():
            try:
                json.loads(plan.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue  # still being written in chunks
            if (plan.parent / "outline.md").is_file():
                return True
        return False


def run_tool(sandbox: Sandbox, name: str, raw_args: str) -> str:
    try:
        args = json.loads(raw_args or "{}")
        if name == "list_dir":
            path = sandbox.resolve(args["path"])
            return "\n".join(p.name + ("/" if p.is_dir() else "") for p in sorted(path.iterdir())) or "(empty)"
        if name == "read_file":
            text = sandbox.resolve(args["path"]).read_text(encoding="utf-8", errors="replace")
            start = int(args.get("offset") or 0)
            chunk = text[start:start + READ_LIMIT]
            rest = len(text) - start - len(chunk)
            return chunk + (f"\n[... {rest} more characters; read again with offset={start + len(chunk)}]" if rest > 0 else "")
        if name == "write_file":
            path = sandbox.resolve(args["path"])
            if not sandbox.writable(path):
                return "ERROR: the skill directory and the materials are read-only"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a" if args.get("append") else "w", encoding="utf-8") as handle:
                handle.write(args["content"])
            return f"wrote {len(args['content'])} characters to {path}"
        if name == "run_command":
            return run_command(sandbox, args["argv"])
        return f"ERROR: unknown tool {name}"
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return f"ERROR: bad arguments for {name}: {exc}"
    except PermissionError as exc:
        return f"ERROR: {exc}"
    except OSError as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def run_command(sandbox: Sandbox, argv: list) -> str:
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return "ERROR: argv must be a non-empty list of strings"
    if argv[0] == "date":
        pass
    elif argv[0] in ("python3", "python") and len(argv) >= 2:
        script = sandbox.resolve(argv[1])
        if script.suffix != ".py" or script.parent.name != "scripts" or sandbox.skill.resolve() not in script.parents:
            return "ERROR: python3 may only run the skill's scripts/*.py"
        argv = [sys.executable, str(script), *argv[2:]]
        for arg in argv[2:]:  # arguments that look like paths must stay in the sandbox
            value = arg.split("=", 1)[-1]
            if value.startswith("/") or ".." in Path(value).parts:
                sandbox.resolve(value)
    else:
        return "ERROR: only 'python3 <skill>/scripts/<name>.py ...' and 'date ...' are allowed"
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(sandbox.root), "LANG": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}  # no key, no inherited secrets
    try:
        done = subprocess.run(argv, cwd=sandbox.workspace, env=env, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out after 120 s"
    out = f"exit {done.returncode}\n{done.stdout}{done.stderr}"
    return out[:TOOL_OUTPUT_LIMIT] + ("\n[output truncated]" if len(out) > TOOL_OUTPUT_LIMIT else "")


# ---------------------------------------------------------------- prompts

def system_prompt(sandbox: Sandbox, max_output_tokens: int = DEFAULT_MAX_OUTPUT) -> str:
    skill_md = (SKILL_SOURCE / "SKILL.md").read_text(encoding="utf-8")
    return (
        "你是运行 whetstone `learn` 技能的宿主模型（宿主类型同 DeepSeek Harness：技能目录即安装目录）。\n"
        f"- 技能目录（SKILL.md 所在目录，只读）：{sandbox.skill}\n"
        f"- 材料（只读）：{sandbox.materials}\n"
        f"- 宿主打开的目录（工作区，当前目录）：{sandbox.workspace}\n"
        "- 工具：list_dir、read_file、write_file、run_command（只能运行 `python3 <技能目录>/scripts/<名>.py …` 与 `date …`）。"
        "路径一律用绝对路径。\n"
        "- 技能脚本按协议文件里的写法运行，用法不清时运行 `python3 <脚本> --help`；不必读 scripts/ 下的源码，"
        "校验规则以协议文件与校验输出为准。\n"
        f"- 你的一次回复（思考加正文）最多约 {max_output_tokens // 1000 * 1000} token：lesson-plan.json 这类大文件一开始就分块写，"
        "每次 write_file 不超过约 12000 字符，第二次起 append=true；不要先试一次写完整个文件。\n"
        "- 不带工具调用的回复就是对学习者说的话，学习者会回答你。\n\n"
        "以下是技能被调用时载入的 SKILL.md 全文：\n\n" + skill_md)


def dry_run_estimate(case: dict, max_output_tokens: int, price=DEFAULT_PRICE) -> dict:
    """Usage estimate for one build to the outline pause, without any request (see evals/README.md)."""
    sandbox = Sandbox(Path("/sandbox"))
    prefix = estimate_tokens(system_prompt(sandbox, max_output_tokens)) + estimate_tokens(json.dumps(TOOLS)) + estimate_tokens(case["request"])
    root = Path(case["materials_root"])
    material_text = "".join((root / rel).read_text(encoding="utf-8", errors="replace") for rel in case["materials"])
    material_bytes = sum((root / rel).stat().st_size for rel in case["materials"])
    needs_plan = len(case["materials"]) > 1 or material_bytes > 30_000
    reads = ["references/stages/_index.md", "references/workspace.md", "references/stages/outline.md",
             "references/build.md", "references/source-handling.md", "references/lesson-contract.md",
             "assets/outline-template.md", "assets/lesson-plan-template.json"]
    if needs_plan:
        reads += ["references/stages/triage.md", "references/stages/plan.md", "assets/learning-plan-template.md"]
    if not case.get("profile"):
        reads += ["references/stages/profile.md", "assets/learner-profile-template.md"]
    read_tokens = sum(estimate_tokens((SKILL_SOURCE / r).read_text(encoding="utf-8")) for r in reads)
    read_tokens += estimate_tokens(material_text)
    if case.get("profile"):
        read_tokens += estimate_tokens(Path(case["profile"]).read_text(encoding="utf-8"))
    result = {"prefix_tokens": prefix, "read_tokens": read_tokens, "material_bytes": material_bytes,
              "planning_stages": needs_plan, "price_cny_per_million": list(price)}
    # Written files: outline + lesson-plan (+ survey and learning plan); the 9-section backtest course is ~83 KB.
    for label, out_tokens, tool_rounds, overhead in (("low", 20_000, 8, 300), ("high", 40_000, 15, 800)):
        writes = -(-out_tokens // (max_output_tokens - 1500))
        rounds = tool_rounds + writes + (2 if needs_plan else 1)  # plus auto replies at stage questions
        growth = read_tokens + out_tokens + rounds * overhead
        input_total = int(rounds * prefix + growth * (rounds - 1) / 2)
        miss = prefix + growth
        result[label] = {"requests": rounds, "input": input_total, "output": out_tokens + rounds * 150,
                         "cache_hit": input_total - miss, "cache_miss": miss}
        r = result[label]
        r["cost_cny"] = cost_cny(r["cache_hit"], r["cache_miss"], r["output"], price)
    return result


# ---------------------------------------------------------------- driver

def drive(case: dict, client: ModelClient, out_dir: Path, cap: int, max_requests: int, max_output_tokens: int,
          price=DEFAULT_PRICE) -> dict:
    run_dir = out_dir / case["id"]
    sandbox = Sandbox(run_dir / "sandbox")
    sandbox.build(case)
    ledger = Ledger(cap)
    reply_text = case.get("auto_reply") or DEFAULT_REPLY
    max_replies = int(case.get("max_auto_replies", 3))
    messages = [{"role": "system", "content": system_prompt(sandbox, max_output_tokens)},
                {"role": "user", "content": case["request"]}]
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    stop, error, replies, booked_messages = "max_requests", None, 0, 0
    transcript = (run_dir / "transcript.jsonl").open("w", encoding="utf-8")
    try:
        while len(ledger.rows) < max_requests:
            last_input = ledger.rows[-1]["input"] + ledger.rows[-1]["output"] if ledger.rows else 0
            next_input = last_input + sum(estimate_tokens(json.dumps(m, ensure_ascii=False)) for m in messages[booked_messages:])
            if not ledger.rows:
                next_input += estimate_tokens(json.dumps(TOOLS))
            if ledger.totals["all"] + next_input + max_output_tokens > cap:
                stop = "token_cap"
                break
            began = time.monotonic()
            try:
                reply = client.complete(messages, TOOLS, max_output_tokens)
            except ModelError as exc:
                stop, error = "model_error", str(exc)
                break
            message = {"role": "assistant", "content": reply.message.get("content") or ""}
            reasoning = reply.message.get("reasoning_content") or ""
            if reasoning:  # thinking models want it back inside a tool loop
                message["reasoning_content"] = reasoning
            calls = reply.message.get("tool_calls") or []
            if calls:
                message["tool_calls"] = calls
            thinking_only = reply.finish_reason == "length" and not calls and not message["content"].strip()
            row = ledger.book(reply.usage, reply.finish_reason, len(calls), time.monotonic() - began,
                              reasoning_chars=len(reasoning), in_context=not thinking_only)
            if thinking_only:
                transcript.write(json.dumps({"row": row, "message": message, "tool_results": []}, ensure_ascii=False) + "\n")
                transcript.flush()
                if messages[-1]["role"] == "user":  # keep roles alternating: fold the note into the last user turn
                    messages[-1] = {**messages[-1], "content": messages[-1]["content"] + "\n\n" + CUT_THINKING_ONLY}
                else:
                    messages.append({"role": "user", "content": CUT_THINKING_ONLY})
                booked_messages = len(messages) - 1  # over-counts the dropped reply once, which only errs early
                continue
            messages.append(message)
            booked_messages = len(messages)  # everything up to here is inside the last input + output
            results = []
            for call in calls:
                output = run_tool(sandbox, call["function"]["name"], call["function"].get("arguments", ""))
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
                results.append({"name": call["function"]["name"], "output": output[:2000]})
            transcript.write(json.dumps({"row": row, "message": message, "tool_results": results}, ensure_ascii=False) + "\n")
            transcript.flush()
            if calls:
                continue
            if reply.finish_reason == "length":
                messages.append({"role": "user", "content": CUT_WITH_OUTPUT})
                continue
            if sandbox.outline_ready():
                stop = "outline"
                break
            if replies >= max_replies:
                stop = "learner_turns"
                break
            replies += 1
            messages.append({"role": "user", "content": reply_text})
    finally:
        transcript.close()
    totals = ledger.totals
    summary = {
        "case": case["id"], "backend": client.name, "model": getattr(client, "model", None),
        "started": started, "ended": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "stop_reason": stop, "error": error, "token_cap": cap, "max_requests": max_requests,
        "http_attempts": getattr(client, "http_attempts", None), "auto_replies": replies,
        "lesson_plans": [str(p.relative_to(run_dir)) for p in sandbox.lesson_plans()],
        "totals": totals, "cost_cny": cost_cny(totals["cache_hit"], totals["cache_miss"], totals["output"], price),
        "price_cny_per_million": list(price), "requests": ledger.rows,
    }
    (run_dir / "messages.json").write_text(json.dumps(messages, ensure_ascii=False, indent=1), encoding="utf-8")
    (run_dir / "ledger.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--case", help="case JSON: id, materials_root, materials[], request, profile?, auto_reply?, max_auto_replies?")
    source.add_argument("--material-id", help="build one entry of evals/materials.json")
    parser.add_argument("--out-dir", required=True, help="run output directory (outside the repository)")
    parser.add_argument("--dry-run", action="store_true", help="estimate usage only; no request, no key needed")
    parser.add_argument("--max-total-tokens", type=int, default=700_000, help="stop before a request would pass this input+output total")
    parser.add_argument("--max-requests", type=int, default=40)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT,
                        help="per-reply output cap, thinking included (default %(default)s)")
    parser.add_argument("--model", default="deepseek-flash", help="model id as listed by the API's /models")
    parser.add_argument("--price", help="CNY per million tokens as HIT,MISS,OUTPUT (default %s)" % ",".join(map(str, DEFAULT_PRICE)))
    parser.add_argument("--replies", help="replay scripted replies from this JSON file instead of calling a model")
    args = parser.parse_args(argv)
    try:
        price = DEFAULT_PRICE
        if args.price:
            try:
                price = tuple(float(x) for x in args.price.split(","))
            except ValueError:
                price = ()
            if len(price) != 3:
                raise InputError("--price must be three numbers: HIT,MISS,OUTPUT")
        case = load_case(args)
        out_dir = Path(args.out_dir)
        if args.dry_run:
            estimate = dry_run_estimate(case, args.max_output_tokens, price)
            estimate["token_cap"] = args.max_total_tokens
            estimate["within_cap"] = estimate["high"]["input"] + estimate["high"]["output"] <= args.max_total_tokens
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"dry-run-{case['id']}.json").write_text(json.dumps(estimate, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(estimate, ensure_ascii=False, indent=2))
            return 0
        client = ScriptedClient(Path(args.replies)) if args.replies else DeepSeekClient(model=args.model)
        summary = drive(case, client, out_dir, args.max_total_tokens, args.max_requests, args.max_output_tokens, price)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except ModelError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    t = summary["totals"]
    print(f"{summary['case']}: {summary['stop_reason']}; {t['requests']} requests, input {t['input']} "
          f"(cache hit {t['cache_hit']}, miss {t['cache_miss']}), output {t['output']}, about {summary['cost_cny']} CNY")
    if summary["error"]:
        print(f"ERROR: {summary['error']}", file=sys.stderr)
    return 0 if summary["stop_reason"] == "outline" else 1


if __name__ == "__main__":
    sys.exit(main())
