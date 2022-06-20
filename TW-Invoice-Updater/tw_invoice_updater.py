import calendar
import os
from datetime import date, datetime, timedelta
from typing import Union

import requests
from loguru import logger
from pydantic import BaseModel
from tw_invoice import AppAPIClient

APP_ID = os.environ["APP_ID"]
API_KEY = os.environ["API_KEY"]

CARD_TYPE = os.environ["CARD_TYPE"]
CARD_NUMBER = os.environ["CARD_NUMBER"]
CARD_ENCRYPT = os.environ["CARD_ENCRYPT"]

UPLOAD_HOST = os.environ["UPLOAD_HOST"]
UPLOAD_USERNAME = os.environ["UPLOAD_USERNAME"]
UPLOAD_PASSWORD = os.environ["UPLOAD_PASSWORD"]


class BearerAuth(requests.auth.AuthBase):
    def __init__(self, username, password):
        response = requests.post(
            f"{UPLOAD_HOST}/token",
            data={
                "username": username,
                "password": password,
                "grant_type": "password",
            },
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]

    def __call__(self, response):
        response.headers["authorization"] = f"Bearer {self.token}"
        return response


#
# API Models
#


class InvoiceDate(BaseModel):
    year: int
    month: int
    date: int
    day: int
    hours: int
    minutes: int
    seconds: int
    time: int
    timezoneOffset: int


class Invoice(BaseModel):
    rowNum: str
    invNum: str
    cardType: str
    cardNo: str
    sellerName: str
    invStatus: str
    invDonatable: bool
    amount: str
    invPeriod: str
    donateMark: bool  # served in 0 or 1, will be cast implicitly to bool
    sellerBan: str
    sellerAddress: Union[str, None] = None
    invoiceTime: str
    buyerBan: Union[str, None] = None
    currency: Union[str, None] = None
    invDate: InvoiceDate


class InvoiceResponse(BaseModel):
    v: str
    code: int
    msg: str
    onlyWinningInv: str
    details: list[Invoice]


class InvoiceDetail(BaseModel):
    rowNum: str
    description: str
    quantity: str
    unitPrice: str
    amount: str


class InvoiceDetailResponse(BaseModel):
    v: str
    code: int
    msg: str
    invNum: str
    invDate: str
    sellerName: str
    amount: str
    invStatus: str
    invPeriod: str
    details: list[InvoiceDetail]
    sellerBan: str
    sellerAddress: str
    invoiceTime: str
    currency: str


#
# Parsed Models
#


class InvoiceParsed(BaseModel):
    number: str
    card_type: str
    card_number: str
    seller_name: str
    status: str
    donatable: bool
    amount: str
    period: str
    donate_mark: int
    seller_tax_id: str
    seller_address: Union[str, None] = None
    buyer_tax_id: Union[str, None] = None
    currency: Union[str, None] = None
    timestamp: datetime


class InvoiceDetailParsed(BaseModel):
    row_number: str
    description: str
    quantity: str
    unit_price: str
    amount: str


def get_invoices(
    client: AppAPIClient, start_date: date, end_date: date
) -> list[Invoice]:
    raw_response = client.get_carrier_invoices_header(
        card_type=CARD_TYPE,
        card_number=CARD_NUMBER,
        start_date=start_date,
        end_date=end_date,
        card_encrypt=CARD_ENCRYPT,
    )
    logger.debug(raw_response)
    invoice_response = InvoiceResponse.parse_obj(raw_response)
    assert invoice_response.code == 200, f"{invoice_response.code}"
    invoices = invoice_response.details
    logger.info(f"Fetched {len(invoices)} invoices")
    logger.debug(invoices)
    return invoices


def convert_invoice(invoice: Invoice) -> InvoiceParsed:
    MAPPING_KEYS = {
        # Custom Name -> API Name
        "number": "invNum",
        "card_type": "cardType",
        "card_number": "cardNo",
        "seller_name": "sellerName",
        "status": "invStatus",
        "donatable": "invDonatable",
        "amount": "amount",
        "period": "invPeriod",
        "donate_mark": "donateMark",
        "seller_tax_id": "sellerBan",
        "seller_address": "sellerAddress",
        "buyer_tax_id": "buyerBan",
        "currency": "currency",
    }

    new_invoice = {}
    for key, spec_key in MAPPING_KEYS.items():
        new_invoice[key] = getattr(invoice, spec_key)
    year = invoice.invDate.year + 1911
    month = invoice.invDate.month
    day = invoice.invDate.date
    time = invoice.invoiceTime
    new_invoice["timestamp"] = datetime.fromisoformat(
        f"{year}-{month:0>2}-{day:0>2}T{time}"
    )
    return InvoiceParsed.parse_obj(new_invoice)


def upload_invoice(invoices: list[InvoiceParsed], session: requests.Session) -> dict:
    # Convert invoices to dicts
    dict_invoices = []
    for invoice in invoices:
        dict_invoice = invoice.dict()
        dict_invoice["timestamp"] = dict_invoice["timestamp"].isoformat()
        dict_invoices.append(dict_invoice)

    # Upload invoices
    response = session.post(f"{UPLOAD_HOST}/tw-invoice", json=dict_invoices)
    response.raise_for_status()
    return response.json()


def convert_invoice_detail(detail: InvoiceDetail) -> InvoiceDetailParsed:
    MAPPING_KEYS = {
        # Custom Name -> API Name
        "row_number": "rowNum",
        "description": "description",
        "quantity": "quantity",
        "unit_price": "unitPrice",
        "amount": "amount",
    }

    new_detail = {}
    for key, spec_key in MAPPING_KEYS.items():
        new_detail[key] = getattr(detail, spec_key)
    return InvoiceDetailParsed.parse_obj(new_detail)


def upload_invoice_details(
    invoice_number: str, details: list[InvoiceDetailParsed], session: requests.Session
) -> dict:
    dict_details = [detail.dict() for detail in details]
    response = session.post(
        f"{UPLOAD_HOST}/tw-invoice/{invoice_number}", json=dict_details
    )
    response.raise_for_status()
    return response.json()


def main():
    # Create API client, upload session and fetch invoices
    client = AppAPIClient(APP_ID, API_KEY, ts_tolerance=180)
    session = requests.Session()
    session.auth = BearerAuth(UPLOAD_USERNAME, UPLOAD_PASSWORD)
    today = date.today()
    start_date = today - timedelta(days=20)
    invoices = get_invoices(client, start_date=start_date, end_date=today)

    # Validate and parse invoices
    parsed_invoices = [convert_invoice(invoice) for invoice in invoices]
    logger.info(f"Parsed {len(parsed_invoices)} invoices")
    logger.debug(parsed_invoices)

    # Upload invoices
    results = upload_invoice(parsed_invoices, session)
    logger.info(f"Created {len(results['created'])} invoices")
    logger.info(f"Updated {len(results['updated'])} invoices")
    logger.debug(results)

    for invoice in results["created"]:
        detail_response = InvoiceDetailResponse.parse_obj(
            client.get_carrier_invoices_detail(
                card_type=CARD_TYPE,
                card_number=CARD_NUMBER,
                invoice_number=invoice["number"],
                invoice_date=datetime.fromisoformat(invoice["timestamp"]).date(),
                card_encrypt=CARD_ENCRYPT,
            )
        )
        assert detail_response.code == 200, f"{detail_response.code}"
        details = detail_response.details
        logger.info(f"Fetched {len(details)} details for {invoice['number']}")
        logger.debug(details)

        parsed_details = [convert_invoice_detail(detail) for detail in details]
        results = upload_invoice_details(invoice["number"], parsed_details, session)
        logger.debug(results)


def lambda_handler(event, context):
    main()


if __name__ == "__main__":
    main()
