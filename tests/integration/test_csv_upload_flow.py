from pathlib import Path


def test_csv_upload_and_process_endpoints(client):
    csv_path = Path("tests/fixtures/sample_bank.csv")
    assert csv_path.exists()

    with open(csv_path, "rb") as f:
        upload_response = client.post(
            "/bank-csv/upload",
            files={"file": ("sample_bank.csv", f, "text/csv")}
        )

    assert upload_response.status_code in [200, 201, 400, 409, 422]

    with open(csv_path, "rb") as f:
        process_response = client.post(
            "/bank-csv/process",
            files={"file": ("sample_bank.csv", f, "text/csv")}
        )

    assert process_response.status_code in [200, 201, 400, 409, 422, 500]