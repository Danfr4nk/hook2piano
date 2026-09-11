#!/usr/bin/env python3
"""Push the local hook2piano tree to GitHub via the Git Data API.

Usage: push.py [--repo Danfr4nk/hook2piano] [--workdir ~/workspace/hook2piano]
Creates blobs -> tree -> initial commit -> refs/heads/main.
"""
import argparse
import base64
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/workspace/skills/github/bin"))

GH_API = os.path.expanduser("~/workspace/skills/github/bin/gh-api")

SKIP_DIRS = {".git", "__pycache__", ".shotvenv", ".venv", "node_modules",
             ".pytest_cache"}
SKIP_FILES = {".DS_Store"}


def gh(method, path, body=None):
    cmd = [GH_API, method, path]
    inp = json.dumps(body).encode() if body is not None else None
    r = subprocess.run(cmd, input=inp, capture_output=True)
    if r.returncode != 0:
        print(f"gh-api {method} {path} failed:\n{r.stderr.decode()}", file=sys.stderr)
        sys.exit(1)
    return json.loads(r.stdout.decode() or "{}")


def collect(workdir):
    files = []
    for root, dirs, names in os.walk(workdir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            if n in SKIP_FILES:
                continue
            full = os.path.join(root, n)
            rel = os.path.relpath(full, workdir)
            files.append((rel, full))
    return sorted(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="Danfr4nk/hook2piano")
    ap.add_argument("--workdir", default=os.path.expanduser("~/workspace/hook2piano"))
    ap.add_argument("--message", default="Initial commit: TheoryTab to one-page piano sheet")
    ap.add_argument("--parent", default=None,
                    help="parent commit sha (for bootstrapping a repo whose blob API needs history)")
    args = ap.parse_args()

    files = collect(args.workdir)
    print(f"packing {len(files)} files…")
    tree = []
    for rel, full in files:
        with open(full, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        blob = gh("POST", f"/repos/{args.repo}/git/blobs",
                  {"content": content, "encoding": "base64"})
        tree.append({"path": rel, "mode": "100644", "type": "blob",
                     "sha": blob["sha"]})
        print(f"  blob {rel}")
    tree_resp = gh("POST", f"/repos/{args.repo}/git/trees",
                   {"tree": tree})
    commit_body = {"message": args.message, "tree": tree_resp["sha"]}
    if args.parent:
        commit_body["parents"] = [args.parent]
    commit = gh("POST", f"/repos/{args.repo}/git/commits", commit_body)
    # fast-forward main if it exists, else create it
    r = subprocess.run(
        [GH_API, "PATCH", f"/repos/{args.repo}/git/refs/heads/main"],
        input=json.dumps({"sha": commit["sha"], "force": False}).encode(),
        capture_output=True)
    if r.returncode != 0:
        gh("POST", f"/repos/{args.repo}/git/refs",
           {"ref": "refs/heads/main", "sha": commit["sha"]})
    print(f"pushed {args.repo}@main {commit['sha'][:7]}")


if __name__ == "__main__":
    main()
