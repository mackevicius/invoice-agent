from fastapi.testclient import TestClient


def test_selected_invoice_includes_its_listed_header(client: TestClient) -> None:
    client.post("/api/demo-company")
    listed_invoice = client.get("/api/invoices").json()[0]

    response = client.get(f"/api/invoices/{listed_invoice['id']}")

    assert response.status_code == 200
    detail = response.json()
    assert {key: detail[key] for key in listed_invoice} == listed_invoice
    assert detail["fields"] is None
    assert detail["steps"] == []
