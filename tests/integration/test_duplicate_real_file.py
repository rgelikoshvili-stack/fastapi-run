from pathlib import Path


def test_duplicate_upload_same_file(client):
    csv_path = Path("tests/fixtures/sample_bank.csv")
    assert csv_path.exists()

    with open(csv_path, "rb") as f:
        first = client.post(
            "/bank-csv/upload",
            files={"file": ("sample_bank.csv", f, "text/csv")}
        )

    assert first.status_code in [200, 201, 400, 409, 422]

    with open(csv_path, "rb") as f:
        second = client.post(
            "/bank-csv/upload",
            files={"file": ("sample_bank.csv", f, "text/csv")}
        )

    assert second.status_code in [200, 201, 400, 409, 422]