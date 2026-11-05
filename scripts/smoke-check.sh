#!/bin/sh
# Uploads an Invoice on a live deployment and waits until the agent has read it.
set -eu

base_url=${1:?Usage: scripts/smoke-check.sh https://<web-url> [invoice.pdf]}
invoice_file=${2:-docs/sample-invoice-known-supplier.pdf}
cookies=$(mktemp)
trap 'rm -f "$cookies"' EXIT

curl -fsS -c "$cookies" -b "$cookies" -X POST "$base_url/api/demo-company" >/dev/null
invoice_id=$(
  curl -fsS -c "$cookies" -b "$cookies" \
    -F "file=@$invoice_file;type=application/pdf" "$base_url/api/invoices" |
    jq -r .id
)
echo "Uploaded Invoice $invoice_id"

deadline=$(($(date +%s) + 300))
while [ "$(date +%s)" -lt "$deadline" ]; do
  invoice=$(curl -fsS -b "$cookies" "$base_url/api/invoices/$invoice_id")
  if echo "$invoice" | jq -e '
      .status != "Processing"
      and all(.steps[]; .status != "Pending" and .status != "Running")' >/dev/null; then
    echo "$invoice" | jq -r '"Finished \(.status): \(.reasons | join("; "))"'
    # A finished run must have read the file, unless the daily AI limit stopped it.
    echo "$invoice" | jq -e '
      .steps[0].status == "Completed"
      or (.reasons | index("daily AI limit reached"))' >/dev/null
    exit
  fi
  sleep 3
done
echo "Invoice $invoice_id did not finish within 5 minutes." >&2
exit 1
