# TW Invoice Updater

Fetching invoices data from MOF E-invoice platform and saving to my database.

## Usage

Find the usage by running the script with the `--help` flag.

```shell
❯ python tw_invoice_updater.py --help
usage: tw_invoice_updater.py [-h] [--relative-month RELATIVE_MONTH] [--all] [--debug]

options:
  -h, --help            show this help message and exit
  --relative-month RELATIVE_MONTH
                        Relative month to fetch. Possible values are -7 (7 months ago) to 0 (this month). (default: 0)
  --all                 Fetch all invoices available. Equivalent to executing from relative-month=-7 to relative-month=0 at once. When this option is enabled, relative-month is ignored.
                        (default: False)
  --debug               Enable debug logging (default: False)
```

Default is fetching invoices in this month (`relative-month=0`).

Configure the option with event JSON on AWS Lambda. The key is exactly the same as the CLI flag. Here's a quick index:

|                      | AWS Lambda event JSON    | Local                                              |
| -------------------- | ------------------------ | -------------------------------------------------- |
| Default (This Month) | `{}`                     | `python tw_invoice_updater.py`                     |
| Last Month           | `{"relative-month": -1}` | `python tw_invoice_updater.py --relative-month=-1` |
| All                  | `{"all": true}`          | `python tw_invoice_updater.py --all`               |
| Debug Mode           | `{"debug": true}`        | `python tw_invoice_updater.py --debug`             |

## Deploy

see [`deploy-tw-invoice-updater.yml`](../.github/workflows/deploy-tw-invoice-updater.yml)
