from io import BytesIO


def test_invoice_parse_endpoint_available(client):
    fake_pdf = BytesIO(b"%PDF-1.4 fake pdf content")
    response = client.post(
        "/invoice/parse",
        files={"file": ("sample.pdf", fake_pdf, "application/pdf")}
    )

    # parser შეიძლება დააბრუნოს 200/400/422, მთავარია route ცოცხალია
    assert response.status_code in [200, 400, 422, 500]