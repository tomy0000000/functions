# TW Invoice Updater

Fetching invoices data from MOF E-invoice platform and saving to my database.

## Usage

Default is fetching invoices in this month (`relative-month=0`).

Use `relative-month` to change the fetching month. e.g. On 2/5, `relative-month=-1` means fetching invoices range from 1/1 to 1/31. Possible values are `-7` to `0`

|            | AWS Lambda event JSON    | Local                                              |
| ---------- | ------------------------ | -------------------------------------------------- |
| Default    | `{}`                     | `python tw_invoice_updater.py`                     |
| Last Month | `{"relative-month": -1}` | `python tw_invoice_updater.py --relative-month=-1` |

## Deploy

see [`deploy-tw-invoice-updater.yml`](../.github/workflows/deploy-tw-invoice-updater.yml)
