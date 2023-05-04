#!/bin/bash
set -e

# Install dependencies
pip install \
    --requirement 'requirements.txt' \
    --target './dist'

# Zip the package
cd dist
zip -r '../packing.zip' '.'
cd ..
zip -g packing.zip tw_invoice_updater.py
