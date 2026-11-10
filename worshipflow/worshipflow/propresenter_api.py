"""Client for ProPresenter's official local HTTP API (read-mostly).

Endpoints used here were checked against the official spec at
https://openapi.propresenter.com/ (snapshot in docs/propresenter-openapi-snapshot.js).
The API can NOT create or edit presentations, groups, arrangements or apply
themes, so this client is used only to *discover* and *verify*.

Safety: this client deliberately has no methods that trigger slides, clear
layers, or change looks/screens. Nothing here can put anything on the LED wall.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

DEFAULT_HOST = os.environ.get("PROPRESENTER_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("PROPRESENTER_PORT", "50001"))


class ProPresenterError(RuntimeError):
    pass


class ProPresenterClient:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 5.0):
        self.base = f"http://{host}:{port}"
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Any = None, raw: bool = False) -> Any:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
        except urllib.error.HTTPError as e:
            raise ProPresenterError(f"{method} {path} -> HTTP {e.code}: {e.read()[:200]!r}") from e
        except (urllib.error.URLError, OSError) as e:
            raise ProPresenterError(
                f"cannot reach ProPresenter at {self.base} ({e}). Is ProPresenter open, and is "
                "Settings > Network > Enable Network turned on with this port?"
            ) from e
        if raw:
            return payload
        return json.loads(payload) if payload else None

    # --- discovery (all GET, confirmed in the official spec) ---
    def version(self) -> dict:
        return self._request("GET", "/version")

    def libraries(self) -> list[dict]:
        return self._request("GET", "/v1/libraries")

    def library(self, library_id: str) -> dict:
        return self._request("GET", f"/v1/library/{urllib.parse.quote(library_id)}")

    def presentation(self, uuid: str) -> dict:
        data = self._request("GET", f"/v1/presentation/{urllib.parse.quote(uuid)}")
        return data.get("presentation", data) if isinstance(data, dict) else data

    def thumbnail(self, uuid: str, index: int, quality: int = 400, kind: str = "png") -> bytes:
        q = urllib.parse.urlencode({"quality": quality, "thumbnail_type": kind})
        return self._request("GET", f"/v1/presentation/{urllib.parse.quote(uuid)}/thumbnail/{index}?{q}", raw=True)

    def themes(self) -> list[dict]:
        return self._request("GET", "/v1/themes")

    def theme(self, theme_id: str) -> dict:
        return self._request("GET", f"/v1/theme/{urllib.parse.quote(theme_id)}")

    def playlists(self) -> list[dict]:
        return self._request("GET", "/v1/playlists")

    def playlist(self, playlist_id: str) -> dict:
        return self._request("GET", f"/v1/playlist/{urllib.parse.quote(playlist_id)}")

    # --- the only write used: replace a playlist's items. Callers must hold an approval. ---
    def replace_playlist_items(self, playlist_id: str, items: list[dict]) -> Any:
        return self._request("PUT", f"/v1/playlist/{urllib.parse.quote(playlist_id)}", items)

    # --- helpers ---
    def find_presentations(self, name: str) -> list[dict]:
        hits = []
        for lib in self.libraries():
            lib_id = lib["id"]["uuid"]
            for item in self.library(lib_id).get("items", []):
                if item.get("name", "").strip().lower() == name.strip().lower():
                    hits.append({"library": lib["id"]["name"], "library_uuid": lib_id, **item})
        return hits


def api_presentation_texts(pres: dict) -> list[tuple[str, str]]:
    """[(group name, slide text)] from GET /v1/presentation/{uuid} (group order, not arrangement)."""
    return [(g.get("name", ""), s.get("text", "")) for g in pres.get("groups", []) for s in g.get("slides", [])]


def verify_live(plan, client: ProPresenterClient, *, presentation_uuid: Optional[str] = None,
                thumbnails_dir: Optional[str] = None) -> dict[str, Any]:
    """Evidence for the QA checks that need ProPresenter itself."""
    from .native.reader import read_pro
    from .qa import _norm

    evidence: dict[str, Any] = {}
    if presentation_uuid is None:
        hits = client.find_presentations(plan.song.title)
        if not hits:
            evidence["native_import"] = {"ok": False, "detail": f"no presentation named {plan.song.title!r} in any library"}
            return evidence
        if len(hits) > 1:
            evidence["native_import"] = {"ok": False, "detail": f"{len(hits)} presentations share this title: {hits}"}
            return evidence
        presentation_uuid = hits[0]["uuid"]
    pres = client.presentation(presentation_uuid)
    got = [(g, _norm(t).casefold()) for g, t in api_presentation_texts(pres)]
    want = [(c.section, _norm(c.text).casefold()) for s in plan.song.sections for c in plan.cues_for(s.name)]
    ok = got == want
    evidence["native_import"] = {"ok": ok, "detail": f"ProPresenter reports {len(got)} slides in {len(pres.get('groups', []))} groups"
                                 + ("" if ok else f"; first difference: {next(((a, b) for a, b in zip(got, want) if a != b), 'slide count differs')}")}
    path = pres.get("presentation_path")
    if path and os.path.exists(path):
        disk = read_pro(path)
        disk_seq = [(g["name"], _norm(s["texts"][0] if s.get("texts") else "").casefold()) for g in disk["groups"] for s in g["slides"]]
        evidence["persistence"] = {"ok": disk_seq == want, "detail": f"re-read saved file {path}"}
    else:
        evidence["persistence"] = {"ok": False, "detail": "ProPresenter did not report a readable presentation_path"}
    count = len(got)
    saved = 0
    for i in range(count):
        try:
            png = client.thumbnail(presentation_uuid, i)
        except ProPresenterError:
            break
        if png and thumbnails_dir:
            os.makedirs(thumbnails_dir, exist_ok=True)
            with open(os.path.join(thumbnails_dir, f"slide-{i + 1:02d}.png"), "wb") as fh:
                fh.write(png)
        saved += 1 if png else 0
    evidence["thumbnails"] = {"ok": saved == count and count > 0, "detail": f"{saved}/{count} thumbnails rendered"}
    evidence["presentation_uuid"] = presentation_uuid
    return evidence
