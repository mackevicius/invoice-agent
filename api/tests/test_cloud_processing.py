import os
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

import invoice_agent.clients
from invoice_agent.app import create_app, create_invoice_worker, load_cloud_parameters

INVOICE_PDF = b"%PDF-1.4\nCloud Invoice"
READABLE_RESPONSE = (
    Path(invoice_agent.clients.__file__).parent / "fixtures/readable.json"
)


@pytest.fixture
def queue_url(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Iterator[str]:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        url = boto3.client("sqs").create_queue(QueueName="invoices")["QueueUrl"]
        boto3.client("s3").create_bucket(
            Bucket="invoice-files",
            CreateBucketConfiguration={"LocationConstraint": "eu-central-1"},
        )
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setenv("COOKIE_SECURE", "false")
        monkeypatch.setenv("INVOICE_FAKE_RESPONSE", str(READABLE_RESPONSE))
        monkeypatch.setenv("INVOICE_QUEUE_URL", url)
        monkeypatch.setenv("INVOICE_FILES_BUCKET", "invoice-files")
        yield url


def test_uploaded_invoice_is_processed_from_sqs_with_its_file_in_s3(
    queue_url: str,
) -> None:
    sqs = boto3.client("sqs")
    with TestClient(create_app()) as client:
        client.post("/api/demo-company")
        uploaded = client.post(
            "/api/invoices",
            files={"file": ("invoice.pdf", INVOICE_PDF, "application/pdf")},
        )
        assert uploaded.status_code == 202
        invoice_id = uploaded.json()["id"]

        messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)[
            "Messages"
        ]
        assert len(messages) == 1
        assert client.get(f"/api/invoices/{invoice_id}").json()["status"] == (
            "Processing"
        )
        assert (
            boto3.client("s3").list_objects_v2(Bucket="invoice-files")["KeyCount"] == 1
        )

        create_invoice_worker()(
            {
                "Records": [
                    {"messageId": message["MessageId"], "body": message["Body"]}
                    for message in messages
                ]
            },
            None,
        )

        invoice = client.get(f"/api/invoices/{invoice_id}").json()
        assert invoice["status"] != "Processing"
        assert invoice["steps"][0]["status"] == "Completed"
        assert all(
            step["status"] not in {"Pending", "Running"} for step in invoice["steps"]
        )
        assert client.get(f"/api/invoices/{invoice_id}/file").content == INVOICE_PDF


def test_a_job_for_a_missing_invoice_is_dropped(queue_url: str) -> None:
    with TestClient(create_app()):
        create_invoice_worker()(
            {
                "Records": [
                    {
                        "messageId": "1",
                        "body": '{"company_id": "00000000-0000-0000-0000-000000000001",'
                        ' "invoice_id": "00000000-0000-0000-0000-000000000002"}',
                    }
                ]
            },
            None,
        )


def test_secrets_stored_in_aws_become_settings(
    queue_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ssm = boto3.client("ssm")
    secrets = {"OPENAI_API_KEY": "sk-cloud", "DATABASE_URL": "postgres://x"}
    for name, value in secrets.items():
        ssm.put_parameter(
            Name=f"/invoice-agent/{name}", Value=value, Type="SecureString"
        )
    monkeypatch.setenv("INVOICE_PARAMETER_PATH", "/invoice-agent")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "")

    load_cloud_parameters()

    assert os.environ["OPENAI_API_KEY"] == "sk-cloud"
    assert os.environ["DATABASE_URL"] == "postgres://x"
