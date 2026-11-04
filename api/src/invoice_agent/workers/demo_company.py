import logging
from threading import Event, Thread

from invoice_agent.services.demo_company import DemoCompanies

logger = logging.getLogger(__name__)


class InProcessDemoCompanyCleanup:
    def __init__(self, companies: DemoCompanies, interval_seconds: float = 60) -> None:
        self.companies = companies
        self.interval_seconds = interval_seconds
        self.stopped = Event()
        self.worker = Thread(
            target=self._work, name="demo-company-cleanup", daemon=True
        )

    def start(self) -> None:
        self.companies.cleanup_expired()
        self.worker.start()

    def close(self) -> None:
        self.stopped.set()
        self.worker.join()

    def _work(self) -> None:
        while not self.stopped.wait(self.interval_seconds):
            try:
                self.companies.cleanup_expired()
            except Exception:
                logger.exception("Demo Company cleanup failed")
