"""Worker composition root — gerçek subprocess ile `--run-once` (crash-safe path).

`python -m flowpilot.worker --run-once --tenant <uuid>` gerçekten çalışır,
flowpilot_app (RLS'e tabi) rolüyle bağlanır, bir dispatch turu yürütür ve ASILI
KALMADAN exit 0 döner. Bu, worker wiring'inin production yolunu doğrular.
"""

from __future__ import annotations

import os
import subprocess
import sys
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from tests.integration.conftest import DatabaseHandle
from tests.integration.workflow_support import (
    AMOUNT_LOW,
    decide,
    publish,
    scoped_count,
    start_and_submit,
)
from tests.integration.workflow_support import build_service as _build


def test_worker_run_once_processes_pending_events(
    database: DatabaseHandle,
    app_sessionmaker: sessionmaker[Session],
    tenant_a: UUID,
) -> None:
    service = _build(app_sessionmaker)
    v1, _ = publish(service, tenant_a)
    flow = start_and_submit(service, app_sessionmaker, tenant_a, v1, AMOUNT_LOW)
    decide(service, flow, 0)  # notification.requested outbox'ta

    env = {**os.environ, "DATABASE_URL": database.app_url}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "flowpilot.worker",
            "--run-once",
            "--tenant",
            str(tenant_a),
            "--worker-id",
            "cli-worker",
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert (
        scoped_count(
            app_sessionmaker,
            tenant_a,
            "workflow_runtime_events",
            instance_id=str(flow.instance_id),
            event_type="notification.dispatched",
        )
        == 1
    )


def test_worker_bounded_loop_runs_and_exits(
    database: DatabaseHandle,
    tenant_a: UUID,
) -> None:
    """Kontrollü döngü (--run --max-passes) çalışır ve ASILI KALMADAN exit 0 döner."""
    env = {**os.environ, "DATABASE_URL": database.app_url}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "flowpilot.worker",
            "--run",
            "--tenant",
            str(tenant_a),
            "--max-passes",
            "3",
            "--interval",
            "0.05",
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
