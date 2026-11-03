# Decision sample v1

These 14 synthetic cases exercise the application's decision rules through
the public Process an Invoice interface, using real Postgres with pgvector.
The Invoice file is a synthetic placeholder: the reader returns scripted
fields, and wording differences use a scripted choice among real search
candidates. No paid model or external dataset is used.

Each case starts a fresh Demo Company with the normal seeded purchase records.
`base_invoice` supplies the common read fields; `invoice_updates` replaces
the named fields for a case. `received_quantity` changes received quantities,
or removes Goods Receipts when null. `pairing_choices` maps a differently
worded Invoice description to its Purchase Order description.

Cases cover clean Auto-Approval, price above 2% tolerance, lower price,
quantity mismatch, partial delivery, received more than ordered, wording
differences, missing Purchase Order, missing Goods Receipt, Duplicate Invoice,
Possible Duplicate, unknown Supplier, total above the Auto-Approval Limit,
and an unmatched Invoice line.

`manifest.json` holds independent expected statuses and review reasons.
`baseline.json` records the accepted run: **14/14 correct, 100% accuracy,
zero wrong Auto-Approvals**, plus every case's status and reasons. A correct
decision matches both the status and the complete ordered list of reasons.
Wrong Auto-Approvals count whenever a case labelled In Review is Auto-Approved,
regardless of its reasons or the baseline.

```sh
docker compose run --rm api uv run --locked python -m evals.decisions --check
```

Every run saves a dated JSON report with its model, sample version and checksum,
expected and actual outcomes, accuracy, and wrong Auto-Approvals. Reports are
saved before checking the gates, so failed runs remain available for diagnosis.

To change an accepted baseline, first inspect the failed report and confirm the
change against the specification. Update the explicit expected outcomes and
baseline deliberately; increment the sample version when changing cases or
labels. Dates, Invoice IDs, and the sample checksum are not part of baseline
comparison. Case IDs, statuses, reasons, scores, model, and version are compared.
Updating a baseline can never allow a wrong Auto-Approval: that safety gate is
unconditional, including when `--check` is omitted.
