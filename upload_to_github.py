#!/usr/bin/env python3
"""
Upload the vCon corpus + dashboard to a GitHub repo via the Contents API.

No `git` required — uses the GitHub REST API directly with a personal
access token. Handles both first-time creation and updates (it looks up
each file's existing SHA so re-running the script overwrites cleanly).

USAGE
    python upload_to_github.py

You'll be prompted for:
  - GitHub username (default: dredgie-vibe)
  - Repo name      (default: vcon-explorer)
  - Branch         (default: main)
  - Personal Access Token (PAT) — input is hidden when you paste it
  - Local folder containing the files (default: current directory)

CREATING A PAT
    https://github.com/settings/tokens
    Generate new token (classic) -> tick the "repo" scope -> Generate
    Copy the token immediately; GitHub only shows it once.

The script uploads every .json, .html, and .py file in the folder to
the root of the repo on the chosen branch.
"""

import os, sys, json, base64, getpass
import urllib.request, urllib.error

DEFAULT_USER   = "dredgie-vibe"
DEFAULT_REPO   = "vcon-explorer"
DEFAULT_BRANCH = "main"

API = "https://api.github.com"

def http(method, url, token, body=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read() or b"{}"
        try:    body = json.loads(raw)
        except: body = {"message": raw.decode(errors="replace")}
        return e.code, body

def get_existing_sha(owner, repo, path, branch, token):
    code, data = http("GET",
        f"{API}/repos/{owner}/{repo}/contents/{path}?ref={branch}", token)
    if code == 200 and isinstance(data, dict):
        return data.get("sha")
    return None

def upload_file(owner, repo, branch, token, local_path, remote_path):
    with open(local_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    sha = get_existing_sha(owner, repo, remote_path, branch, token)
    body = {
        "message": ("Update " if sha else "Add ") + remote_path,
        "content": content,
        "branch":  branch,
    }
    if sha: body["sha"] = sha
    return http("PUT",
        f"{API}/repos/{owner}/{repo}/contents/{remote_path}", token, body=body)

def main():
    print("=== vCon corpus -> GitHub uploader ===\n")
    owner  = input(f"GitHub username [{DEFAULT_USER}]: ").strip()  or DEFAULT_USER
    repo   = input(f"Repo name       [{DEFAULT_REPO}]: ").strip()  or DEFAULT_REPO
    branch = input(f"Branch          [{DEFAULT_BRANCH}]: ").strip() or DEFAULT_BRANCH
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        print(f"Using GH_TOKEN env var (length {len(token)})")
    else:
        token = getpass.getpass("Personal access token (input hidden): ").strip()
    if not token:
        print("! No token provided; aborting."); sys.exit(1)
    print(f"Token sanity: starts {token[:4]!r}, ends {token[-4:]!r}, length {len(token)}")
    folder = input("Local folder containing the files [.]: ").strip() or "."
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        print(f"! Not a folder: {folder}"); sys.exit(1)

    targets = sorted(
        f for f in os.listdir(folder)
        if f.endswith((".json", ".html", ".py")) and not f.startswith(".")
    )
    if not targets:
        print(f"! No .json/.html/.py files found in {folder}"); sys.exit(1)

    print(f"\nUploading {len(targets)} files to {owner}/{repo}@{branch} ...\n")
    fail = 0
    for i, fname in enumerate(targets, 1):
        local = os.path.join(folder, fname)
        code, data = upload_file(owner, repo, branch, token, local, fname)
        ok = code in (200, 201)
        flag = "OK  " if ok else "FAIL"
        print(f"  [{i:2d}/{len(targets)}] {flag}  {fname}   (HTTP {code})")
        if not ok:
            fail += 1
            print(f"          ! {data.get('message','')}")
            if isinstance(data.get("errors"), list):
                for e in data["errors"]: print(f"            - {e}")

    print()
    if fail == 0:
        print(f"All {len(targets)} files uploaded.")
        print(f"View the repo:    https://github.com/{owner}/{repo}")
        print(f"Enable Pages at:  https://github.com/{owner}/{repo}/settings/pages")
    else:
        print(f"{fail} of {len(targets)} files failed. Check errors above.")
        sys.exit(2)

if __name__ == "__main__":
    main()
