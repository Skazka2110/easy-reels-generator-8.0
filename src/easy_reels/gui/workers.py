from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from ..control import StopToken


class BatchWorker(QObject):
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, pipeline, *, seed: int | None = None):
        super().__init__()
        self.pipeline = pipeline
        self.seed = seed
        self.stop_token = StopToken()

    @Slot()
    def run(self) -> None:
        try:
            result = self.pipeline.run_batch(
                seed=self.seed,
                progress=self.progress.emit,
                stop_token=self.stop_token,
            )
        except Exception as exc:  # boundary between worker and GUI
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)

    @Slot()
    def request_stop(self) -> None:
        self.stop_token.request_stop()


class PreviewWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, pipeline, *, seed: int | None = None):
        super().__init__()
        self.pipeline = pipeline
        self.seed = seed

    @Slot()
    def run(self) -> None:
        try:
            result = self.pipeline.render_preview(seed=self.seed)
        except Exception as exc:  # boundary between worker and GUI
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)

