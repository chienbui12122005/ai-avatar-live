"""Teacher avatar profiles.

A profile is a folder holding one source clip per behavior, so a teacher's
clips are uploaded once and reused for every render instead of re-uploading
each time.

    PROFILE_DIR/
      teacher-a/
        profile.json        {name, slug, created_at, clips: {...}}
        idle.mp4
        explain.mp4
        question.mp4
        smile.mp4
"""

import json
import re
import shutil
import time
from pathlib import Path
from typing import Optional

# Supported behaviors (order = display order).
BEHAVIORS = ["idle", "explain", "question", "smile"]

_META = "profile.json"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "teacher"


def avatar_id(slug: str, behavior: str) -> str:
    """Deterministic, filesystem/YAML-safe id used as the MuseTalk avatar cache key."""
    def safe(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return f"{safe(slug)}__{safe(behavior)}"


class ProfileStore:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, slug: str) -> Path:
        return self.root / slug

    def _meta_path(self, slug: str) -> Path:
        return self._dir(slug) / _META

    def exists(self, slug: str) -> bool:
        return self._meta_path(slug).exists()

    def create(self, name: str) -> dict:
        slug = _slugify(name)
        # avoid clobbering an existing profile with the same slug
        base, i = slug, 2
        while self.exists(slug):
            slug = f"{base}-{i}"
            i += 1
        self._dir(slug).mkdir(parents=True, exist_ok=True)
        meta = {"name": name, "slug": slug, "created_at": time.time(), "clips": {}}
        self._write(slug, meta)
        return meta

    def get(self, slug: str) -> Optional[dict]:
        p = self._meta_path(slug)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def all(self) -> list[dict]:
        out = []
        for d in self.root.iterdir():
            if d.is_dir() and (d / _META).exists():
                out.append(json.loads((d / _META).read_text(encoding="utf-8")))
        return sorted(out, key=lambda m: m.get("created_at", 0), reverse=True)

    def _write(self, slug: str, meta: dict) -> None:
        self._meta_path(slug).write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def save_clip(self, slug: str, behavior: str, file_obj, filename: str) -> str:
        """Store an uploaded clip for a behavior; returns its absolute path."""
        if behavior not in BEHAVIORS:
            raise ValueError(f"unknown behavior: {behavior}")
        meta = self.get(slug)
        if meta is None:
            raise ValueError(f"unknown profile: {slug}")
        ext = Path(filename).suffix or ".mp4"
        dest = self._dir(slug) / f"{behavior}{ext}"
        # drop any previous clip for this behavior (possibly different ext)
        for old in self._dir(slug).glob(f"{behavior}.*"):
            old.unlink()
        with dest.open("wb") as f:
            shutil.copyfileobj(file_obj, f)
        meta.setdefault("clips", {})[behavior] = dest.name
        # A new clip invalidates any cached avatar for this behavior.
        meta.get("prepared", {}).pop(behavior, None)
        self._write(slug, meta)
        return str(dest)

    def mark_prepared(self, slug: str, behavior: str, av_id: str) -> None:
        meta = self.get(slug)
        if meta is None:
            return
        meta.setdefault("prepared", {})[behavior] = av_id
        self._write(slug, meta)

    def is_prepared(self, slug: str, behavior: str) -> bool:
        meta = self.get(slug)
        return bool(meta and behavior in meta.get("prepared", {}))

    def clip_path(self, slug: str, behavior: str) -> Optional[str]:
        meta = self.get(slug)
        if not meta:
            return None
        name = meta.get("clips", {}).get(behavior)
        if not name:
            return None
        p = self._dir(slug) / name
        return str(p) if p.exists() else None

    def delete(self, slug: str) -> bool:
        d = self._dir(slug)
        if not d.exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True
