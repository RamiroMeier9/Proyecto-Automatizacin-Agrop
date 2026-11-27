import unittest

from inta_forrajes.connectors.a3 import A3Connector, classify_cfi
from inta_forrajes.connectors.a3_marketdata import (
    A3AgroMarketDataConnector,
    A3OfficialAPIKeyConnector,
    contract_month_proxy,
)
from inta_forrajes.connectors.bcra import BCRAConnector
from inta_forrajes.connectors.sio_granos import SIOGranosConnector
from inta_forrajes.http import JSONResponse


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


class ConnectorTests(unittest.TestCase):
    def test_bcra_parser(self):
        client = FakeClient(
            [
                JSONResponse(
                    data={
                        "results": {
                            "fecha": "2026-11-26",
                            "detalle": [
                                {"codigoMoneda": "USD", "descripcion": "DOLAR", "tipoCotizacion": 1400.5, "tipoPase": 1},
                                {"codigoMoneda": "BRL", "descripcion": "REAL", "tipoCotizacion": 250, "tipoPase": 1},
                            ],
                        }
                    },
                    headers={},
                    status=200,
                )
            ]
        )
        rows = BCRAConnector(client).fetch_latest(("USD",))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].series_id, "FX_BCRA_USD_ARS")
        self.assertEqual(rows[0].value, 1400.5)

    def test_sio_volume_weighted_average(self):
        connector = SIOGranosConnector("20123456789", "token", client=FakeClient([]))
        rows = connector.aggregate_vwap(
            [
                {"fechaOperacion": "2026-11-26T10:00:00", "grano": "TRIGO", "lugarEntrega": "Bahía Blanca", "simboloPrecioPorTN": "$", "precioTN": "100", "volumenTN": "10"},
                {"fechaOperacion": "2026-11-26T11:00:00", "grano": "TRIGO", "lugarEntrega": "Bahía Blanca", "simboloPrecioPorTN": "$", "precioTN": "200", "volumenTN": "30"},
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].value, 175)
        self.assertEqual(rows[0].metadata["total_volume_tn"], 40)

    def test_a3_auth_and_marketdata_parser(self):
        client = FakeClient(
            [
                JSONResponse(data={}, headers={"x-auth-token": "abc"}, status=200),
                JSONResponse(
                    data={
                        "status": "OK",
                        "marketData": {
                            "SE": {"price": 250.5, "size": None, "date": 1795737600000},
                            "LA": {"price": 251, "size": 2, "date": 1795737600000},
                            "BI": [{"price": 250, "size": 10}],
                            "OF": [{"price": 252, "size": 12}],
                            "OI": {"price": None, "size": 300, "date": 1795737600000},
                            "TV": {"price": None, "size": 40, "date": 1795737600000},
                        },
                    },
                    headers={},
                    status=200,
                ),
            ]
        )
        connector = A3Connector("user", "pass", client=client)
        quote = connector.fetch_quote(
            "DEMO/ENE27",
            {"instrument_type": "future", "underlying": "DEMO", "maturity_date": "20270131"},
        )
        self.assertEqual(quote.settlement, 250.5)
        self.assertEqual(quote.open_interest, 300)
        self.assertEqual(quote.volume, 40)
        self.assertEqual(client.calls[0][2]["headers"]["X-Username"], "user")

    def test_cfi_classification(self):
        self.assertEqual(classify_cfi("FXXXXX"), "future")
        self.assertEqual(classify_cfi("OXXXXX"), "option")
        self.assertEqual(classify_cfi("EXXXXX"), "unknown")

    def test_a3_agro_futures_and_options_parser(self):
        connector = A3AgroMarketDataConnector(client=FakeClient([]))
        futures = connector.parse_futures(
            [
                {
                    "fecha": "2026-11-26T00:00:00",
                    "posicion": "MAI.ROS/ABR27",
                    "precioUltimo": 183.5,
                    "precioAjuste": 183.5,
                    "volumen": 430,
                    "interesAbierto": 7969,
                }
            ]
        )
        options = connector.parse_options(
            [
                {
                    "fecha": "2026-11-26T00:00:00",
                    "posicion": "MAI.ROS/ABR27 200 C",
                    "tipo": "Call",
                    "ejercicio": "200",
                    "precioUltimo": 2.2,
                    "precioAjuste": 1.823544,
                    "volumen": 35,
                }
            ]
        )
        self.assertEqual(futures[0].currency, "USD")
        self.assertEqual(futures[0].unit, "USD/t")
        self.assertEqual(options[0].underlying, "MAI.ROS/ABR27")
        self.assertEqual(options[0].strike, 200)
        self.assertEqual(options[0].option_type, "call")
        self.assertEqual(contract_month_proxy("MAI.ROS/ABR27"), "2027-04-30")

    def test_a3_official_key_uses_header_without_exposing_it_in_url(self):
        client = FakeClient([JSONResponse(data=[{"ok": True}], headers={}, status=200)])
        connector = A3OfficialAPIKeyConnector("secret", environment="uat", client=client)
        from datetime import date

        connector.fetch_final_report(date(2026, 11, 26))
        method, url, kwargs = client.calls[0]
        self.assertEqual(method, "GET")
        self.assertNotIn("secret", url)
        self.assertEqual(kwargs["headers"]["x-api-key"], "secret")


if __name__ == "__main__":
    unittest.main()
