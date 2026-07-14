"""FlowPilot backend — tek Python distribution (`flowpilot-backend`).

Import kökü: `flowpilot` (ADR-009).

Alt paketler:
    modules/        13 bounded context — iş mantığı BURADA
    api/            FastAPI composition root  (iş mantığı YOK)
    worker/         worker composition root   (iş mantığı YOK)
    shared/         primitive'ler, ClockPort, IdGeneratorPort
    config/         ayar yükleme
    observability/  log, metric, trace
"""

__version__ = "0.1.0"
