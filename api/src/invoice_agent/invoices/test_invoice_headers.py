from fastapi.testclient import TestClient


def test_selected_invoice_returns_its_header(client: TestClient) -> None:
    client.post("/api/demo-company")
    listed_invoice = client.get("/api/invoices").json()[0]

    response = client.get(f"/api/invoices/{listed_invoice['id']}")

    assert response.status_code == 200
    assert response.json() == listed_invoice
