import os
from datetime import date, datetime, timedelta
from typing import Union

import requests
from loguru import logger
from pushover_complete import PushoverAPI
from pydantic import BaseModel
from tw_invoice import AppAPIClient
from tw_invoice.schema import Invoice, InvoiceDetail

APP_ID = os.environ["APP_ID"]
API_KEY = os.environ["API_KEY"]

CARD_TYPE = os.environ["CARD_TYPE"]
CARD_NUMBER = os.environ["CARD_NUMBER"]
CARD_ENCRYPT = os.environ["CARD_ENCRYPT"]

UPLOAD_HOST = os.environ["UPLOAD_HOST"]
UPLOAD_USERNAME = os.environ["UPLOAD_USERNAME"]
UPLOAD_PASSWORD = os.environ["UPLOAD_PASSWORD"]

PUSHOVER_API_KEY = os.environ["PUSHOVER_API_KEY"]
PUSHOVER_USER_KEY = os.environ["PUSHOVER_USER_KEY"]


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
    invoices = raw_response.details
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


@logger.catch
def lambda_handler(event, context):
    # Create API client, upload session and fetch invoices
    client = AppAPIClient(APP_ID, API_KEY, ts_tolerance=180)
    pushover_client = PushoverAPI(PUSHOVER_API_KEY)
    session = requests.Session()
    session.auth = BearerAuth(UPLOAD_USERNAME, UPLOAD_PASSWORD)

    start_date = event.get("start_date")
    if not start_date:
        start_date = date.today() - timedelta(days=20)
    else:
        start_date = date.fromisoformat(start_date)

    end_date = event.get("end_date")
    if not end_date:
        end_date = date.today()
    else:
        end_date = date.fromisoformat(end_date)

    invoices = get_invoices(client, start_date=start_date, end_date=end_date)

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
        detail_response = client.get_carrier_invoices_detail(
            card_type=CARD_TYPE,
            card_number=CARD_NUMBER,
            invoice_number=invoice["number"],
            invoice_date=datetime.fromisoformat(invoice["timestamp"]).date(),
            card_encrypt=CARD_ENCRYPT,
        )
        details = detail_response.details
        logger.info(f"Fetched {len(details)} details for {invoice['number']}")

        parsed_details = [convert_invoice_detail(detail) for detail in details]
        logger.debug(parsed_details)
        results = upload_invoice_details(invoice["number"], parsed_details, session)
        logger.debug(results)

        title = f"???? {invoice['number']}"
        message = (
            f"???? {invoice['seller_name']}\n"
            f"???? {invoice['timestamp']}\n"
            f"???? {invoice['currency']}${invoice['amount']}\n\n"
        )
        for detail in parsed_details:
            message += (
                f"- {detail.description}: ${detail.unit_price} ?? {detail.quantity}\n"
            )
        pushover_client.send_message(PUSHOVER_USER_KEY, message=message, title=title)


if __name__ == "__main__":
    today = date.today()
    start_date = today.replace(day=today.day - 2).isoformat()
    lambda_handler(event=dict(start_date=start_date), context={})
