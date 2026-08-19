"""Scenario runner: drives scripted conversations against a live backend and
prints INPUT / EXPECTED BEHAVIOUR / ACTUAL OUTPUT for each turn.

    python backend/tests/runner.py                 # run all scenarios
    python backend/tests/runner.py hinglish_hot    # run one
    python backend/tests/runner.py --md            # markdown, for TEST_CASES.md

Assumes the server is running:  uvicorn main:app --port 8123  (from backend/)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

BASE = os.getenv("BOT_URL", "http://127.0.0.1:8000")


def _client(base: str) -> httpx.Client:
    """Talk to a running server, or to the app in-process.

    In-process (the default) is what CI and the scripted benchmark use: it needs
    no port, no uvicorn lifecycle, and no cleanup. Pass --base http://... to run
    the same scenarios against a real server instead.
    """
    if base == "inproc":
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from fastapi.testclient import TestClient  # noqa: E402
        from main import app  # noqa: E402
        return TestClient(app)
    return httpx.Client(base_url=base, timeout=180)


def run_scenario(scn: dict, base: str = BASE) -> dict:
    """Play one scenario. Returns the transcript plus the analytics payload."""
    session_id = None
    turns = []
    with _client(base) as client:
        for step in scn["turns"]:
            r = client.post("/api/chat", json={"message": step["user"],
                                               "session_id": session_id})
            r.raise_for_status()
            data = r.json()
            session_id = data["session_id"]
            turns.append({
                "user": step["user"],
                "expect": step["expect"],
                "reply": data["reply"],
                "events": data["events"],
                "ended": data["ended"],
            })
            if data["ended"]:
                break
        a = client.post("/api/analytics", json={"session_id": session_id})
        analytics = a.json().get("analytics", {}) if a.status_code == 200 else {
            "error": a.text[:200]
        }
    return {"name": scn["name"], "title": scn["title"], "session_id": session_id,
            "turns": turns, "analytics": analytics,
            "expect_analytics": scn.get("expect_analytics", {})}


def check_analytics(result: dict) -> list[str]:
    """Compare analytics against the scenario's expectations. Returns failures."""
    failures = []
    for dotted, expected in result["expect_analytics"].items():
        node = result["analytics"]
        for key in dotted.split("."):
            node = (node or {}).get(key) if isinstance(node, dict) else None
        ok = (node in expected) if isinstance(expected, list) else (node == expected)
        if not ok:
            failures.append(f"{dotted}: expected {expected!r}, got {node!r}")
    return failures


def print_text(result: dict) -> bool:
    print("=" * 78)
    print(f"SCENARIO: {result['name']} — {result['title']}")
    print("=" * 78)
    for i, t in enumerate(result["turns"], 1):
        print(f"\n[Turn {i}]")
        print(f"  INPUT    : {t['user']}")
        print(f"  EXPECTED : {t['expect']}")
        print(f"  ACTUAL   : {t['reply']}")
        for e in t["events"]:
            print(f"  EVENT    : {e['type']} -> "
                  f"{json.dumps(e['result'], ensure_ascii=False)[:180]}")
    print("\n[ANALYTICS]")
    print(json.dumps(result["analytics"], indent=2, ensure_ascii=False))
    failures = check_analytics(result)
    print("\n[ANALYTICS CHECK] " + ("PASS" if not failures else "FAIL"))
    for f in failures:
        print(f"   - {f}")
    return not failures


def print_md(result: dict) -> bool:
    print(f"\n## {result['title']}\n")
    print("| # | Input | Expected behaviour | Actual output |")
    print("|---|---|---|---|")
    for i, t in enumerate(result["turns"], 1):
        ev = " ".join(f"`{e['type']}:{e['result'].get('status', '')}"
                      f"{'/' + e['result'].get('reason', '') if e['result'].get('reason') else ''}`"
                      for e in t["events"])
        actual = t["reply"].replace("|", "\\|").replace("\n", " ")
        print(f"| {i} | {t['user'].replace('|', '\\|')} | {t['expect']} | "
              f"{actual} {ev} |")
    failures = check_analytics(result)
    print(f"\n**Analytics check: {'PASS' if not failures else 'FAIL — ' + '; '.join(failures)}**\n")
    print("```json")
    print(json.dumps(result["analytics"], indent=2, ensure_ascii=False))
    print("```")
    return not failures


def main() -> int:
    sys.path.insert(0, os.path.dirname(__file__))
    from scenarios import SCENARIOS  # noqa: E402

    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", help="scenario names to run (default: all)")
    ap.add_argument("--md", action="store_true", help="markdown output")
    ap.add_argument("--base", default="inproc",
                    help="'inproc' (default) or a server URL like http://127.0.0.1:8000")
    args = ap.parse_args()

    chosen = ([s for s in SCENARIOS if s["name"] in args.names] if args.names
              else [s for s in SCENARIOS if not s.get("manual")])
    if not chosen:
        print(f"No scenario matched. Available: {[s['name'] for s in SCENARIOS]}")
        return 2

    passed = 0
    for scn in chosen:
        result = run_scenario(scn, args.base)
        ok = print_md(result) if args.md else print_text(result)
        passed += ok
    print(f"\n{'-' * 78}\n{passed}/{len(chosen)} scenarios passed analytics checks.")
    return 0 if passed == len(chosen) else 1


if __name__ == "__main__":
    raise SystemExit(main())
