from typing import TYPE_CHECKING, Protocol
from uuid import UUID

import boto3

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class InvoiceFileStore(Protocol):
    def save(self, company_id: UUID, invoice_id: UUID, content: bytes) -> None: ...

    def load(self, company_id: UUID, invoice_id: UUID) -> bytes | None: ...


class S3InvoiceFiles:
    def __init__(self, bucket: str, client: "S3Client | None" = None) -> None:
        self.bucket = bucket
        self.client = client or boto3.client("s3")

    def save(self, company_id: UUID, invoice_id: UUID, content: bytes) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=f"{company_id}/{invoice_id}", Body=content
        )

    def load(self, company_id: UUID, invoice_id: UUID) -> bytes | None:
        try:
            stored = self.client.get_object(
                Bucket=self.bucket, Key=f"{company_id}/{invoice_id}"
            )
        except self.client.exceptions.NoSuchKey:
            return None
        return stored["Body"].read()
