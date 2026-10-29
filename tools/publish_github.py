#!/usr/bin/env python3
"""Publish this repository to GitHub (create repo, push, tag, create Release).

Requires a GitHub token in the environment (never pass it on the command line):

  PowerShell:  $env:GITHUB_TOKEN = "<token>"
  bash:        export GITHUB_TOKEN="<token>"

Token scopes:
  - classic token: `repo` (create repo + push + releases)
  - fine-grained token: repository creation on the account/org + Contents: read/write
    + Metadata: read (and Administration: write if you want topics/description changes)

Examples:
  python tools/publish_github.py --dry-run
  python tools/publish_github.py
  python tools/publish_github.py --owner my-org --repo why-exist-graph --description "..."
  python tools/publish_github.py --no-release

Why not `gh`: this project intentionally uses only the Python standard library; the
script talks to the GitHub REST API via urllib and shells out to `git` for the push
(with OpenSSL TLS backend, which works in restricted Windows sandboxes).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
DEFAULT_REPO = "why-exist-graph"
TOPICS = ["dsh", "deepseek-harness", "skill", "design-graph", "delivery-gate", "sqlite", "python"]


def fatal(message: str) -> "NoReturn":  # noqa: F821
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_version() -> str:
    return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def token_from_env() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token.strip():
        fatal("missing GITHUB_TOKEN/GH_TOKEN environment variable (see tools/publish_github.py header)")
    return token.strip()


class GitHub:
    def __init__(self, token: str):
        self.token = token

    def request(self, method: str, path: str, body: dict | None = None, *, raw: bool = False,
                accept: str = "application/vnd.github+json", url: str | None = None):
        target = url or (API + path)
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "why-exist-graph-publish",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(target, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = resp.read()
                if raw:
                    return resp.status, payload
                return resp.status, (json.loads(payload.decode("utf-8")) if payload else None)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            try:
                message = json.loads(detail).get("message", detail)
            except json.JSONDecodeError:
                message = detail
            if exc.code == 404:
                return 404, None
            fatal(f"GitHub API {method} {path} -> HTTP {exc.code}: {message}")


def git(args: list[str], *, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    merged = dict(os.environ)
    merged["GIT_TERMINAL_PROMPT"] = "0"
    if env:
        merged.update(env)
    proc = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                          encoding="utf-8", env=merged)
    if check and proc.returncode != 0:
        fatal(f"git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc


def git_auth_env(token: str) -> dict:
    basic = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
    # GIT_CONFIG_COUNT style avoids persisting the token in .git/config or argv.
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraheader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
    }


def ensure_clean_tree(allow_dirty: bool) -> None:
    status = git(["status", "--porcelain"]).stdout.strip()
    if status and not allow_dirty:
        fatal("working tree is dirty; commit/stash changes first (or pass --allow-dirty):\n" + status)


def release_body(version: str) -> str:
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    pattern = re.compile(rf"^## {re.escape(version)}.*$", re.MULTILINE)
    match = pattern.search(changelog)
    if not match:
        return f"why-exist-graph v{version}"
    start = match.start()
    next_match = re.compile(r"^## ", re.MULTILINE).search(changelog, match.end())
    end = next_match.start() if next_match else len(changelog)
    section = changelog[start:end].strip()
    return f"# why-exist-graph v{version}\n\n" + section.split("\n", 1)[1].strip()


def ensure_release_asset(version: str) -> Path:
    asset = REPO_ROOT / "dist" / f"v{version}" / f"why-exist-graph-{version}.zip"
    if not asset.is_file():
        print("building release zip ...")
        subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "build_release.py"),
                        "--out", str(REPO_ROOT / "dist")], cwd=REPO_ROOT, check=True)
    if not asset.is_file():
        fatal(f"release asset not found: {asset}")
    return asset


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Publish why-exist-graph to GitHub")
    parser.add_argument("--owner", default=None, help="GitHub user/org (default: authenticated user)")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="repository name (default why-exist-graph)")
    parser.add_argument("--description", default="DSH-native design graph + delivery gate skill: mechanically check design/code necessity and delivery evidence.",
                        help="GitHub repository description")
    parser.add_argument("--private", action="store_true", help="create a private repo (open source should stay public)")
    parser.add_argument("--version", default=None, help="release version (default: VERSION)")
    parser.add_argument("--tag", default=None, help="git tag (default: v<version>)")
    parser.add_argument("--branch", default="main", help="branch to push (default main)")
    parser.add_argument("--no-topics", action="store_true", help="do not set repository topics")
    parser.add_argument("--no-release", action="store_true", help="push only; do not create GitHub Release")
    parser.add_argument("--allow-dirty", action="store_true", help="allow pushing with uncommitted changes (not recommended)")
    parser.add_argument("--dry-run", action="store_true", help="print planned actions; no network/git writes")
    args = parser.parse_args(argv)

    version = args.version or read_version()
    tag = args.tag or f"v{version}"
    if not (REPO_ROOT / ".git").exists():
        fatal(f"{REPO_ROOT} is not a git repository")
    ensure_clean_tree(args.allow_dirty)

    if args.dry_run:
        print(json.dumps({
            "dry_run": True,
            "repo_root": str(REPO_ROOT),
            "version": version,
            "tag": tag,
            "branch": args.branch,
            "repo": {"owner": args.owner or "<authenticated-user>", "name": args.repo, "private": args.private},
            "planned": [
                "GitHub API: GET /user",
                "GitHub API: GET /repos/<owner>/<repo>; create it if missing",
                "git remote add/set-url origin https://github.com/<owner>/<repo>.git",
                "git tag -a " + tag + " (if missing)",
                "git -c http.sslBackend=openssl push -u origin " + args.branch,
                "git -c http.sslBackend=openssl push origin " + tag,
                "GitHub API: PUT topics" + ("" if not args.no_topics else " (disabled)"),
                "GitHub API: create Release " + tag + " + upload why-exist-graph-" + version + ".zip"
                + ("" if not args.no_release else " (disabled)"),
            ],
        }, ensure_ascii=False, indent=2))
        return 0

    token = token_from_env()
    gh = GitHub(token)
    status, user = gh.request("GET", "/user")
    if status != 200 or not isinstance(user, dict):
        fatal("could not read authenticated GitHub user (token invalid?)")
    owner = args.owner or user["login"]
    repo = args.repo

    status, existing = gh.request("GET", f"/repos/{owner}/{repo}")
    if status == 404:
        create_body = {
            "name": repo,
            "description": args.description,
            "private": bool(args.private),
            "has_issues": True,
            "has_projects": False,
            "has_wiki": False,
            "auto_init": False,
        }
        path = "/user/repos" if owner == user["login"] else f"/orgs/{owner}/repos"
        status, created = gh.request("POST", path, create_body)
        if status not in (200, 201):
            fatal(f"failed to create repository {owner}/{repo}")
        repo_url = created["html_url"]
        print(f"created repository: {repo_url}")
    else:
        repo_url = existing["html_url"]
        print(f"repository exists: {repo_url}")

    remote_url = f"https://github.com/{owner}/{repo}.git"
    current = git(["remote", "get-url", "origin"], check=False)
    if current.returncode == 0 and current.stdout.strip():
        if current.stdout.strip() != remote_url:
            git(["remote", "set-url", "origin", remote_url])
    else:
        git(["remote", "add", "origin", remote_url])

    tags = git(["tag", "--list", tag]).stdout.strip()
    if not tags:
        git(["tag", "-a", tag, "-m", f"why-exist-graph {tag}"])
        print(f"created tag: {tag}")

    auth_env = git_auth_env(token)
    print(f"pushing {args.branch} ...")
    git(["-c", "http.sslBackend=openssl", "push", "-u", "origin", args.branch], env=auth_env)
    print(f"pushing tag {tag} ...")
    git(["-c", "http.sslBackend=openssl", "push", "origin", tag], env=auth_env)

    if not args.no_topics:
        try:
            gh.request("PUT", f"/repos/{owner}/{repo}/topics", {"names": TOPICS},
                       accept="application/vnd.github+json")
        except SystemExit:
            print("warning: failed to update topics (non-fatal)")

    release_url = None
    if not args.no_release:
        status, existing_release = gh.request("GET", f"/repos/{owner}/{repo}/releases/tags/{tag}")
        body = release_body(version)
        if status == 200 and existing_release:
            release = existing_release
            print(f"release exists: {release['html_url']}")
        else:
            status, release = gh.request("POST", f"/repos/{owner}/{repo}/releases", {
                "tag_name": tag,
                "name": f"why-exist-graph {tag}",
                "body": body,
                "draft": False,
                "prerelease": False,
            })
            if status not in (200, 201):
                fatal("failed to create GitHub Release")
            print(f"created release: {release['html_url']}")
        release_url = release["html_url"]
        asset = ensure_release_asset(version)
        assets = gh.request("GET", f"/repos/{owner}/{repo}/releases/{release['id']}/assets")[1] or []
        if not any(item.get("name") == asset.name for item in assets):
            upload_url = release["upload_url"].split("{", 1)[0]
            query = urllib.parse.urlencode({"name": asset.name})
            with asset.open("rb") as handle:
                data = handle.read()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/zip",
                "User-Agent": "why-exist-graph-publish",
            }
            req = urllib.request.Request(f"{upload_url}?{query}", data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    uploaded = json.loads(resp.read().decode("utf-8"))
                print(f"uploaded asset: {uploaded['name']} ({uploaded.get('size')} bytes)")
            except urllib.error.HTTPError as exc:
                fatal(f"asset upload failed: HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}")
        else:
            print(f"asset already present: {asset.name}")

    commit = git(["rev-parse", "--short", "HEAD"]).stdout.strip()
    print(json.dumps({
        "repo": repo_url,
        "commit": commit,
        "tag": tag,
        "release": release_url,
        "next": "git push future commits with: git push origin " + args.branch,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
