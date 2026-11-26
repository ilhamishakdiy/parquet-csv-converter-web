"""Job lifecycle in the API process: one conversion subprocess at a time, polled via status.json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import AppError
from .exporter import read_json, remove_tree, write_json_atomic
from .settings import APP_DIR

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


@dataclass
class Job:
    job_id: str
    job_dir: Path
    staging: Path
    temp_dir: Path
    destination: Path
    created_destination: bool
    process: subprocess.Popen
    created_at: float
    cancelled: bool = False


class JobManager:
    def __init__(self, work_dir: Path):
        self.root = work_dir / "jobs"
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def cleanup_stale(self) -> None:
        remove_tree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def running(self) -> Job | None:
        for job in self.jobs.values():
            if job.process.poll() is None:
                return job
        return None

    def start(self, spec: dict) -> str:
        with self.lock:
            active = self.running()
            if active:
                raise AppError("job_running", "A conversion is already running. Wait for it to finish or cancel it.", 409)
            job_id = uuid.uuid4().hex[:12]
            job_dir = self.root / job_id
            job_dir.mkdir(parents=True)
            spec = {**spec, "job_id": job_id, "temp_dir": str(job_dir / "spill")}
            spec["staging"] = str(Path(spec["destination"]) / f".pqcsv-staging-{job_id}")
            (job_dir / "spec.json").write_text(json.dumps(spec, indent=2, default=str), encoding="utf-8")
            log = open(job_dir / "worker.log", "wb")
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            process = subprocess.Popen(
                [sys.executable, "-m", "backend.worker", str(job_dir)],
                cwd=str(APP_DIR),
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                env=env,
            )
            log.close()
            self.jobs[job_id] = Job(
                job_id=job_id,
                job_dir=job_dir,
                staging=Path(spec["staging"]),
                temp_dir=Path(spec["temp_dir"]),
                destination=Path(spec["destination"]),
                created_destination=bool(spec.get("create_destination")),
                process=process,
                created_at=time.time(),
            )
            return job_id

    def get(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if not job:
            raise AppError("job_not_found", "Unknown job. It may belong to a previous session.", 404)
        return job

    def status(self, job_id: str) -> dict:
        job = self.get(job_id)
        data = read_json(job.job_dir / "status.json") or {
            "state": "running",
            "stage": "starting",
            "progress": 0.0,
            "parts_completed": 0,
            "parts_total": None,
            "started_at": job.created_at,
            "finished_at": None,
            "error": None,
        }
        exit_code = job.process.poll()
        if data["state"] == "running" and exit_code is not None:
            # Worker died without reporting (crash, OOM kill): never treat as success.
            data.update(
                state="failed",
                finished_at=time.time(),
                error={
                    "code": "worker_crashed",
                    "message": f"The conversion process stopped unexpectedly (exit code {exit_code}). "
                    "This is often caused by running out of memory. Nothing was published.",
                },
            )
            write_json_atomic(job.job_dir / "status.json", data)
            self._cleanup(job)
        started = data.get("started_at") or job.created_at
        end = data.get("finished_at") or time.time()
        data["elapsed_seconds"] = round(end - started, 1)
        data["job_id"] = job_id
        data.pop("pid", None)
        return data

    def cancel(self, job_id: str) -> dict:
        job = self.get(job_id)
        with self.lock:
            if job.process.poll() is None:
                job.cancelled = True
                job.process.terminate()
                try:
                    job.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    job.process.kill()
                    job.process.wait(timeout=15)
                data = read_json(job.job_dir / "status.json") or {}
                if data.get("state") in (None, "running"):
                    data.update(
                        state="cancelled",
                        finished_at=time.time(),
                        error={"code": "cancelled", "message": "Cancelled. Incomplete files were removed."},
                    )
                    data.setdefault("started_at", job.created_at)
                    write_json_atomic(job.job_dir / "status.json", data)
                self._cleanup(job)
        return self.status(job_id)

    def result(self, job_id: str) -> dict:
        status = self.status(job_id)
        if status["state"] != "succeeded":
            raise AppError("job_not_succeeded", f"The job is {status['state']}; there is no successful result.", 409)
        return read_json(self.get(job_id).job_dir / "result.json") or {}

    def _cleanup(self, job: Job) -> None:
        remove_tree(job.staging)
        remove_tree(job.temp_dir)
        if job.created_destination:
            try:
                job.destination.rmdir()  # only removes the folder if it is still empty
            except OSError:
                pass

    def shutdown(self) -> None:
        for job in list(self.jobs.values()):
            if job.process.poll() is None:
                self.cancel(job.job_id)
