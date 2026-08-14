"""RS.ge connector protocol contract tests."""
import xml.etree.ElementTree as ET


def test_waybill_soap_namespace_matches_asmx_tempuri_contract():
    from app.api.connectors import rs_ge_connector as m
    assert m._WB_NS == "http://tempuri.org/"


def test_waybill_history_sends_buyer_tin_and_parses_result_xml(monkeypatch):
    from app.api.connectors import rs_ge_connector as m

    calls = []

    def fake_soap_call(endpoint, method, ns, params, timeout=30):
        calls.append((endpoint, method, ns, params))
        return ET.fromstring(
            """
            <get_waybills_v1Response xmlns="http://tempuri.org/">
              <get_waybills_v1Result>
                &lt;WAYBILLS&gt;
                  &lt;WAYBILL&gt;
                    &lt;ID&gt;42&lt;/ID&gt;
                    &lt;WAYBILL_NUMBER&gt;WB-42&lt;/WAYBILL_NUMBER&gt;
                    &lt;STATUS&gt;1&lt;/STATUS&gt;
                    &lt;BUYER_TIN&gt;204000000&lt;/BUYER_TIN&gt;
                    &lt;FULL_AMOUNT&gt;118.00&lt;/FULL_AMOUNT&gt;
                  &lt;/WAYBILL&gt;
                &lt;/WAYBILLS&gt;
              </get_waybills_v1Result>
            </get_waybills_v1Response>
            """
        )

    monkeypatch.setenv("RS_GE_SU", "test-su")
    monkeypatch.setenv("RS_GE_SP", "test-sp")
    monkeypatch.setattr(m, "_soap_call", fake_soap_call)

    rows = m.RsGeConnector().history("tenant1", limit=10)

    assert calls[0][1] == "get_waybills_v1"
    assert calls[0][2] == "http://tempuri.org/"
    assert "buyer_tin" in calls[0][3]
    assert rows[0]["id"] == "42"
    assert rows[0]["waybill_number"] == "WB-42"


def test_get_waybill_parses_nested_result_xml(monkeypatch):
    from app.api.connectors import rs_ge_connector as m

    def fake_soap_call(endpoint, method, ns, params, timeout=30):
        return ET.fromstring(
            """
            <get_waybillResponse xmlns="http://tempuri.org/">
              <get_waybillResult>
                &lt;WAYBILL&gt;
                  &lt;ID&gt;77&lt;/ID&gt;
                  &lt;WAYBILL_NUMBER&gt;WB-77&lt;/WAYBILL_NUMBER&gt;
                  &lt;STATUS&gt;1&lt;/STATUS&gt;
                  &lt;GOODS_LIST&gt;
                    &lt;GOODS&gt;
                      &lt;ID&gt;5&lt;/ID&gt;
                      &lt;W_NAME&gt;Item&lt;/W_NAME&gt;
                      &lt;QUANTITY&gt;2&lt;/QUANTITY&gt;
                      &lt;PRICE&gt;10&lt;/PRICE&gt;
                    &lt;/GOODS&gt;
                  &lt;/GOODS_LIST&gt;
                &lt;/WAYBILL&gt;
              </get_waybillResult>
            </get_waybillResponse>
            """
        )

    monkeypatch.setenv("RS_GE_SU", "test-su")
    monkeypatch.setenv("RS_GE_SP", "test-sp")
    monkeypatch.setattr(m, "_soap_call", fake_soap_call)

    row = m.RsGeConnector().get_waybill(77)

    assert row["id"] == "77"
    assert row["waybill_number"] == "WB-77"
    assert row["goods_list"][0]["name"] == "Item"


def test_waybill_xml_escapes_free_text_fields():
    from app.api.connectors.rs_ge_connector import _build_waybill_xml

    xml = _build_waybill_xml({
        "buyer_tin": "204000000",
        "buyer_name": "A & B",
        "start_address": "Tbilisi <Start>",
        "end_address": "Batumi > End",
        "goods_list": [{"name": "Oil & Gas", "quantity": 1, "price": 10, "amount": 10}],
    })

    assert "A &amp; B" in xml
    assert "Tbilisi &lt;Start&gt;" in xml
    assert "Oil &amp; Gas" in xml
