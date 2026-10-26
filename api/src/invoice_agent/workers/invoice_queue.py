import logging
from collections.abc import Callable
from dataclasses import dataclass
from queue import Queue
from threading import Thread
from typing import Protocol
from uuid import UUID

from invoice_agent.schemas.invoices import InvoiceDetail
from invoice_agent.services.invoice_processing import InvoiceNotFound

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessInvoiceJob:
    company_id: UUID
    invoice_id: UUID


class InvoiceQueue(Protocol):
    def enqueue(self, job: ProcessInvoiceJob) -> None: ...


class InProcessInvoiceQueue:
    def __init__(self, process: Callable[[UUID, UUID], InvoiceDetail]) -> None:
        self.process = process
        self.jobs: Queue[ProcessInvoiceJob | None] = Queue()
        self.worker = Thread(target=self._work, name="invoice-worker", daemon=True)

    def start(self) -> None:
        self.worker.start()

    def enqueue(self, job: ProcessInvoiceJob) -> None:
        self.jobs.put(job)

    def close(self) -> None:
        self.jobs.put(None)
        self.worker.join()

    def _work(self) -> None:
        while (job := self.jobs.get()) is not None:
            try:
                self.process(job.company_id, job.invoice_id)
            except InvoiceNotFound:
                logger.info("Skipping an expired or deleted Invoice %s", job.invoice_id)
            except Exception:
                logger.exception("Invoice worker failed for %s", job.invoice_id)
