import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from queue import Queue
from threading import Thread
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

import boto3

from invoice_agent.schemas.invoices import InvoiceDetail
from invoice_agent.services.invoices import InvoiceNotFound

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessInvoiceJob:
    company_id: UUID
    invoice_id: UUID

    def to_message(self) -> str:
        return json.dumps(
            {"company_id": str(self.company_id), "invoice_id": str(self.invoice_id)}
        )

    @classmethod
    def from_message(cls, body: str) -> "ProcessInvoiceJob":
        message = json.loads(body)
        return cls(UUID(message["company_id"]), UUID(message["invoice_id"]))


class InvoiceQueue(Protocol):
    def enqueue(self, job: ProcessInvoiceJob) -> None: ...


def run_invoice_job(
    process: Callable[[UUID, UUID], InvoiceDetail], job: ProcessInvoiceJob
) -> None:
    try:
        process(job.company_id, job.invoice_id)
    except InvoiceNotFound:
        logger.info("Skipping an expired or deleted Invoice %s", job.invoice_id)
    except Exception:
        logger.exception("Invoice worker failed for %s", job.invoice_id)


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
            run_invoice_job(self.process, job)


class SqsInvoiceQueue:
    def __init__(self, queue_url: str, client: "SQSClient | None" = None) -> None:
        self.queue_url = queue_url
        self.client = client or boto3.client("sqs")

    def enqueue(self, job: ProcessInvoiceJob) -> None:
        self.client.send_message(QueueUrl=self.queue_url, MessageBody=job.to_message())


def process_sqs_messages(
    process: Callable[[UUID, UUID], InvoiceDetail], event: dict[str, Any]
) -> None:
    for record in event["Records"]:
        run_invoice_job(process, ProcessInvoiceJob.from_message(record["body"]))
