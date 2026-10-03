"""horizon_model_store.py - Independent versioning for 3day/weekly/monthly."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json, shutil, os, stat, time
import joblib

HORIZONS = ("3day", "weekly", "monthly")
DEFAULT_MODELS_ROOT = Path("processed/models")

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _force_rmtree(path: Path) -> None:
    """Robust deletion on Windows (read-only files / transient file locks)."""
    last_error = None
    def _onerror(func, failed_path, exc_info):
        try:
            os.chmod(failed_path, stat.S_IWRITE | stat.S_IREAD)
            func(failed_path)
        except Exception:
            raise exc_info[1]
    for _ in range(3):
        try:
            if path.exists():
                shutil.rmtree(path, onerror=_onerror)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.25)
    if last_error:
        raise PermissionError(
            f"Access denied while deleting {path}. Close any Explorer window, model viewer, "
            f"or process using the model files, then try again. Original error: {last_error}"
        ) from last_error

class HorizonModelStore:
    def __init__(self, horizon: str, models_root: str | Path = DEFAULT_MODELS_ROOT, project_root: str | Path | None = None):
        if horizon not in HORIZONS:
            raise ValueError(f"Unknown horizon {horizon!r}")
        self.horizon = horizon
        self.models_root = Path(models_root)
        self.project_root = Path(project_root) if project_root else self.models_root.parent.parent
        self.horizon_dir = self.models_root / horizon
        self.candidates_dir = self.horizon_dir / "candidates"
        self.production_json = self.horizon_dir / "production.json"
        self.legacy_production_json = self.models_root / "production.json"

    def ensure_dirs(self) -> None:
        self.horizon_dir.mkdir(parents=True, exist_ok=True)
        self.candidates_dir.mkdir(parents=True, exist_ok=True)

    def version_dir(self, version: str, *, candidate: bool = False) -> Path:
        return (self.candidates_dir if candidate else self.horizon_dir) / version

    def model_filename(self, algorithm: str) -> str:
        return f"electricity_model_{algorithm}.joblib"

    def metadata_filename(self, algorithm: str) -> str:
        return f"electricity_model_{algorithm}.json"

    def pointer_path_str(self, path: Path) -> str:
        resolved = Path(path).resolve()
        try:
            return str(resolved.relative_to(self.project_root.resolve()))
        except ValueError:
            return str(resolved)

    def read_production_pointer(self) -> dict[str, Any] | None:
        for path in (self.production_json,):
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data.get("model_path"):
                        return data
                except Exception:
                    pass
        if self.horizon == "3day" and self.legacy_production_json.exists():
            try:
                data = json.loads(self.legacy_production_json.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("model_path"):
                    return data
            except Exception:
                pass
        return None

    def write_production_pointer(self, version: str, model_path: Path, versioned_model_path: Path | None = None, extra: dict | None = None) -> dict:
        self.ensure_dirs()
        pointer = {
            "horizon": self.horizon,
            "production_version": version,
            "model_path": self.pointer_path_str(model_path),
            "versioned_model_path": self.pointer_path_str(versioned_model_path) if versioned_model_path else None,
            "promoted_at": _utc_now_iso(),
        }
        if extra:
            pointer.update(extra)
        self.production_json.write_text(json.dumps(pointer, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.horizon == "3day":
            legacy = {
                k: pointer[k]
                for k in ("production_version", "model_path", "versioned_model_path", "promoted_at")
            }
            self.legacy_production_json.write_text(
                json.dumps(legacy, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return pointer

    def production_version(self) -> str | None:
        p = self.read_production_pointer()
        return p.get("production_version") if p else None

    def resolve_model_path(self, pointer: dict | None = None) -> Path | None:
        """Resolve the active production model file on disk.

        Order of attempts:
        1. ``model_path`` from production.json (absolute or relative)
        2. ``versioned_model_path`` from production.json
        3. ``{horizon}/{production_version}/electricity_model_*.joblib``
           so predictors keep working after flat copies are removed
        """
        pointer = pointer or self.read_production_pointer()
        if not pointer:
            return None

        def _normalize(raw: str) -> Path:
            # Windows-style separators in JSON must not break on Linux.
            return Path(str(raw).replace("\\", "/"))

        candidates: list[Path] = []
        for key in ("model_path", "versioned_model_path"):
            raw = pointer.get(key)
            if not raw:
                continue
            p = _normalize(raw)
            if p.is_absolute():
                candidates.append(p)
            else:
                for base in (
                    self.project_root,
                    self.models_root,
                    self.horizon_dir,
                    self.production_json.parent,
                    self.legacy_production_json.parent,
                ):
                    candidates.append((base / p).resolve())

        version = pointer.get("production_version")
        algo = pointer.get("algorithm")
        if version:
            # Prefer candidates/{version}/ — production lives there only.
            for as_candidate in (True, False):
                vdir = self.version_dir(str(version), candidate=as_candidate)
                if algo:
                    candidates.append(vdir / self.model_filename(str(algo)))
                if vdir.exists():
                    candidates.extend(sorted(vdir.glob("electricity_model_*.joblib")))

        seen: set[str] = set()
        for cand in candidates:
            key = str(cand)
            if key in seen:
                continue
            seen.add(key)
            try:
                if cand.exists() and cand.is_file():
                    return cand
            except OSError:
                continue
        return None

    def list_versions(self) -> list[str]:
        """All known version ids under candidates/ (and legacy outer folders)."""
        self.ensure_dirs()
        versions: set[str] = set()
        for root in (self.candidates_dir, self.horizon_dir):
            if not root.exists():
                continue
            for child in root.iterdir():
                if not child.is_dir() or child.name == "candidates":
                    continue
                parts = child.name.split(".")
                if len(parts) == 3 and all(x.isdigit() for x in parts):
                    versions.add(child.name)
        return sorted(versions, key=lambda v: tuple(int(x) for x in v.split(".")))

    def next_version(self, current: str | None = None) -> str:
        if current is None:
            current = self.production_version()
        existing = self.list_versions()
        if current is None and not existing:
            return "1.0.0"
        cands = ([current] if current else []) + existing
        if self.candidates_dir.exists():
            for child in self.candidates_dir.iterdir():
                if child.is_dir():
                    parts = child.name.split(".")
                    if len(parts) == 3 and all(x.isdigit() for x in parts):
                        cands.append(child.name)
        best = max(cands, key=lambda v: tuple(int(x) for x in v.split(".")))
        maj, mino, patch = (int(x) for x in best.split("."))
        return f"{maj}.{mino}.{patch + 1}"

    def store_candidate(self, version: str, algorithm: str, model_obj: Any, metadata: dict) -> dict:
        self.ensure_dirs()
        vdir = self.version_dir(version, candidate=True)
        if vdir.exists():
            _force_rmtree(vdir)
        vdir.mkdir(parents=True)
        joblib_path = vdir / self.model_filename(algorithm)
        meta_path = vdir / self.metadata_filename(algorithm)
        try:
            if hasattr(model_obj, "save"):
                model_obj.save(joblib_path)
            else:
                joblib.dump(model_obj, joblib_path)
            meta = {"horizon": self.horizon, "version": version, "algorithm": algorithm, "created_at": _utc_now_iso(), "status": "candidate", **metadata}
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        except Exception:
            # Never leave an empty/half-written version folder behind.
            try:
                _force_rmtree(vdir)
            except Exception:
                pass
            raise
        return {"version": version, "algorithm": algorithm, "model_path": str(joblib_path), "metadata_path": str(meta_path), "metadata": meta}

    def load_candidate_metadata(self, version: str) -> dict | None:
        vdir = self.version_dir(version, candidate=True)
        if not vdir.exists():
            return None
        for meta_file in vdir.glob("electricity_model_*.json"):
            try:
                return json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                continue
        return None

    def list_candidates(self) -> list[dict]:
        self.ensure_dirs()
        out = []
        for child in sorted(self.candidates_dir.iterdir(), reverse=True):
            if child.is_dir():
                meta = self.load_candidate_metadata(child.name)
                out.append(meta or {"version": child.name, "horizon": self.horizon})
        return out

    def promote_candidate(self, version: str, algorithm: str, *, refit_model: Any = None, extra_metadata: dict | None = None) -> dict:
        """Promote in place under ``candidates/{version}/``.

        No copy is made outside ``candidates/``. production.json points at
        the joblib inside the candidate folder. Optional ``refit_model``
        overwrites the joblib in that same folder.
        """
        self.ensure_dirs()
        cand_dir = self.version_dir(version, candidate=True)
        if not cand_dir.exists():
            raise FileNotFoundError(f"Candidate not found: {cand_dir}")

        joblib_name = self.model_filename(algorithm)
        meta_name = self.metadata_filename(algorithm)
        dest_joblib = cand_dir / joblib_name
        dest_meta = cand_dir / meta_name

        if refit_model is not None:
            if hasattr(refit_model, "save"):
                refit_model.save(dest_joblib)
            else:
                joblib.dump(refit_model, dest_joblib)
        elif not dest_joblib.exists():
            # Algorithm filename mismatch — use any joblib in the folder
            found = sorted(cand_dir.glob("electricity_model_*.joblib"))
            if not found:
                raise FileNotFoundError(f"Candidate model not found in {cand_dir}")
            dest_joblib = found[0]
            algorithm = dest_joblib.stem.replace("electricity_model_", "")
            dest_meta = dest_joblib.with_suffix(".json")

        meta: dict[str, Any] = {}
        if dest_meta.exists():
            try:
                meta = json.loads(dest_meta.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        meta.update({
            "horizon": self.horizon,
            "version": version,
            "algorithm": algorithm,
            "status": "production",
            "promoted_at": _utc_now_iso(),
        })
        if extra_metadata:
            meta.update(extra_metadata)
        dest_meta.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        for leftover in (
            self.horizon_dir / joblib_name,
            self.horizon_dir / meta_name,
        ):
            try:
                if leftover.is_file():
                    leftover.unlink()
            except OSError:
                pass
        outer_ver = self.version_dir(version, candidate=False)
        if outer_ver.exists() and outer_ver.is_dir():
            try:
                shutil.rmtree(outer_ver)
            except OSError:
                pass

        pointer = self.write_production_pointer(
            version,
            dest_joblib,
            dest_joblib,
            extra={"algorithm": algorithm, "horizon": self.horizon},
        )
        return {
            "version": version,
            "algorithm": algorithm,
            "model_path": str(dest_joblib),
            "versioned_model_path": str(dest_joblib),
            "pointer": pointer,
            "metadata": meta,
        }

    def get_production_metadata(self) -> dict | None:
        pointer = self.read_production_pointer()
        if not pointer:
            return None
        model_path = self.resolve_model_path(pointer)
        if model_path is None:
            return {"pointer": pointer, "available": False}
        meta_path = model_path.with_suffix(".json")
        meta = None
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "available": True, "pointer": pointer, "metadata": meta, "model_path": str(model_path),
            "production_version": pointer.get("production_version"),
            "algorithm": (meta or {}).get("model_type") or (meta or {}).get("algorithm") or pointer.get("algorithm"),
            "promoted_at": pointer.get("promoted_at"),
        }

    def load_version_metadata(self, version: str, *, candidate: bool = True) -> dict | None:
        """Load metadata; prefer ``candidates/{version}``, then legacy outer folder."""
        for as_cand in ((True, False) if candidate else (False, True)):
            vdir = self.version_dir(version, candidate=as_cand)
            if not vdir.exists():
                continue
            for meta_file in vdir.glob("electricity_model_*.json"):
                try:
                    return json.loads(meta_file.read_text(encoding="utf-8"))
                except Exception:
                    continue
        return None

    def list_promoted_versions(self) -> list[dict]:
        """Versions under candidates/ that are current production or previously promoted.

        Everything lives in ``candidates/``; nothing is listed from outer folders
        except as a migration fallback when candidates is empty for that version.
        """
        self.ensure_dirs()
        out: list[dict] = []
        current = self.production_version()
        seen: set[str] = set()
        # Primary: all candidates folders (production + history + pending)
        if self.candidates_dir.exists():
            for child in sorted(self.candidates_dir.iterdir(), reverse=True):
                if not child.is_dir():
                    continue
                ver = child.name
                parts = ver.split(".")
                if not (len(parts) == 3 and all(x.isdigit() for x in parts)):
                    continue
                meta = self.load_candidate_metadata(ver) or {
                    "version": ver,
                    "horizon": self.horizon,
                }
                meta = dict(meta)
                is_current = ver == current
                status = meta.get("status") or "candidate"
                if is_current:
                    status = "production"
                meta["status"] = status
                meta["is_current"] = is_current
                # Treat non-current with status production as history
                meta["is_candidate"] = status == "candidate" and not is_current
                if is_current or status in ("production", "candidate"):
                    out.append(meta)
                    seen.add(ver)
        for ver in reversed(self.list_versions()):
            if ver in seen:
                continue
            outer = self.version_dir(ver, candidate=False)
            if not outer.exists():
                continue
            meta = self.load_version_metadata(ver, candidate=False) or {
                "version": ver,
                "horizon": self.horizon,
            }
            meta = dict(meta)
            meta["is_current"] = ver == current
            meta["is_candidate"] = False
            meta["status"] = "production" if meta["is_current"] else "history"
            out.append(meta)
        return out

    def delete_version(self, version: str, *, candidate: bool = True) -> None:
        """Delete a version under candidates/ (default). Blocks current production."""
        current = self.production_version()
        if current and version == current:
            raise ValueError(
                f"Cannot delete current production version {version!r} for horizon {self.horizon}"
            )
        removed = False
        for as_cand in (True, False):
            vdir = self.version_dir(version, candidate=as_cand)
            if vdir.exists():
                _force_rmtree(vdir)
                removed = True
        if not removed:
            raise FileNotFoundError(f"Version directory not found: {version}")

    def activate_version(
        self,
        version: str,
        algorithm: str | None = None,
        *,
        from_candidate: bool = True,
    ) -> dict:
        """Make a candidates/{version} folder the production model in place."""
        # Prefer candidates always
        cand_dir = self.version_dir(version, candidate=True)
        if cand_dir.exists():
            meta = self.load_candidate_metadata(version) or {}
            algo = algorithm or meta.get("algorithm") or meta.get("model_type") or "ridge"
            return self.promote_candidate(version, str(algo))

        vdir = self.version_dir(version, candidate=False)
        if not vdir.exists():
            raise FileNotFoundError(f"Version directory not found: {version}")

        meta = self.load_version_metadata(version, candidate=False) or {}
        algo = algorithm or meta.get("algorithm") or meta.get("model_type")
        joblib_path: Path | None = None
        if algo:
            p = vdir / self.model_filename(str(algo))
            if p.exists():
                joblib_path = p
        if joblib_path is None:
            found = sorted(vdir.glob("electricity_model_*.joblib"))
            if not found:
                raise FileNotFoundError(f"No model joblib in {vdir}")
            joblib_path = found[0]
            algo = joblib_path.stem.replace("electricity_model_", "")

        # Migrate into candidates so nothing stays "outside"
        dest_dir = self.version_dir(version, candidate=True)
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(vdir, dest_dir)
        try:
            shutil.rmtree(vdir)
        except OSError:
            pass
        return self.promote_candidate(version, str(algo))
