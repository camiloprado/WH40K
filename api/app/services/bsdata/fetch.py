"""Download dos catálogos BSData do GitHub, só quando o usuário pede."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.errors import err

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
REPO_RE = re.compile(r"^wh40k-\d{1,2}e$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NAME_RE = re.compile(r"^[\w ,.'()&\-]{1,120}\.json$")
MAX_FILE = 15 * 1024 * 1024
MAX_TOTAL = 60 * 1024 * 1024
MAX_FILES = 10


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=False,
        headers={"User-Agent": "list-companion", "Accept": "application/vnd.github+json"},
    )


def check_repo(repo: str) -> str:
    if not REPO_RE.match(repo or ""):
        err(422, "validation_error", "Repositório inválido")
    return repo


def check_sha(sha: str) -> str:
    if not SHA_RE.match(sha or ""):
        err(422, "validation_error", "Commit inválido")
    return sha


_TREES: dict[tuple[str, str], list[dict]] = {}


def latest(repo: str) -> dict:
    check_repo(repo)
    try:
        with _client() as client:
            head = client.get(f"{API}/repos/BSData/{repo}/commits/HEAD")
            if head.status_code == 404:
                err(404, "not_found", "Repositório não encontrado na BSData")
            head.raise_for_status()
            commit = head.json()
    except httpx.HTTPError as exc:
        err(502, "bsdata_unavailable", f"GitHub indisponível: {exc.__class__.__name__}")
    sha = check_sha(str(commit.get("sha") or ""))
    details = commit.get("commit") or {}
    return {
        "repo": repo,
        "sha": sha,
        "date": (details.get("committer") or {}).get("date"),
        "message": (str(details.get("message") or "").splitlines() or [""])[0][:200],
        "files": tree(repo, sha),
    }


def tree(repo: str, sha: str) -> list[dict]:
    key = (check_repo(repo), check_sha(sha))
    if key in _TREES:
        return _TREES[key]
    try:
        with _client() as client:
            response = client.get(f"{API}/repos/BSData/{repo}/git/trees/{sha}")
            if response.status_code == 404:
                err(404, "not_found", "Commit não encontrado na BSData")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        err(502, "bsdata_unavailable", f"GitHub indisponível: {exc.__class__.__name__}")
    files = [
        {
            "name": item["path"],
            "size": item.get("size") or 0,
            "library": "library" in item["path"].lower(),
            "system": item["path"].lower().startswith("warhammer 40,000"),
        }
        for item in response.json().get("tree", [])
        if item.get("type") == "blob" and NAME_RE.match(str(item.get("path") or ""))
    ]
    if not files:
        err(422, "bsdata_format", "Este repositório não publica catálogos em JSON")
    files.sort(key=lambda item: item["name"])
    if len(_TREES) > 20:
        _TREES.clear()
    _TREES[key] = files
    return files


class Loader:
    def __init__(self, repo: str, sha: str, files: list[dict]):
        self.repo = check_repo(repo)
        self.sha = check_sha(sha)
        self.files = {item["name"]: item for item in files}
        self.total = 0
        self.cache = Path(get_settings().bsdata_cache_dir) / repo / sha

    def load(self, name: str) -> dict:
        if name not in self.files or not NAME_RE.match(name):
            err(422, "validation_error", "Arquivo fora do catálogo")
        if self.files[name].get("size", 0) > MAX_FILE:
            err(413, "payload_too_large", f"{name} é grande demais")
        path = self.cache / name
        if path.is_file():
            raw = path.read_bytes()
        else:
            raw = self._download(name)
            self.cache.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.total += len(raw)
        if self.total > MAX_TOTAL:
            err(413, "payload_too_large", "Catálogos grandes demais no total")
        try:
            data = json.loads(raw)
        except ValueError:
            err(422, "bsdata_format", f"{name} não é JSON válido")
        catalogue = data.get("catalogue") if isinstance(data, dict) else None
        if not isinstance(catalogue, dict):
            err(422, "bsdata_format", f"{name} não é um catálogo BattleScribe")
        return catalogue

    def _download(self, name: str) -> bytes:
        url = f"{RAW}/BSData/{self.repo}/{self.sha}/{quote(name)}"
        try:
            with _client() as client, client.stream("GET", url) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_FILE:
                        err(413, "payload_too_large", f"{name} é grande demais")
                    chunks.append(chunk)
                return b"".join(chunks)
        except httpx.HTTPError as exc:
            err(502, "bsdata_unavailable", f"Falha ao baixar {name}: {exc.__class__.__name__}")

    def load_with_links(self, main: str) -> dict[str, dict]:
        catalogues = {main: self.load(main)}
        queue = [main]
        while queue:
            current = queue.pop(0)
            for link in catalogues[current].get("catalogueLinks") or []:
                if any(cat.get("id") == link.get("targetId") for cat in catalogues.values()):
                    continue
                if len(catalogues) >= MAX_FILES:
                    break
                for candidate in self._candidates(str(link.get("name") or ""), set(catalogues)):
                    catalogue = self.load(candidate)
                    if catalogue.get("id") == link.get("targetId"):
                        catalogues[candidate] = catalogue
                        queue.append(candidate)
                        break
        return catalogues

    def _candidates(self, name: str, taken: set[str]) -> list[str]:
        exact = f"{name}.json"
        wanted = _tokens(name)
        scored = []
        for file in self.files:
            if file in taken:
                continue
            if file == exact:
                return [file]
            tokens = _tokens(file[:-5])
            score = len(wanted & tokens) / max(1, len(wanted | tokens))
            if score > 0.3:
                scored.append((score, file))
        return [file for _, file in sorted(scored, reverse=True)[:3]]


def _tokens(text: str) -> set[str]:
    return {item for item in re.split(r"[^a-z0-9']+", text.lower()) if item}
