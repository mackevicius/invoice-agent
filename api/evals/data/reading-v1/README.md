# Reading sample v1

This is the first three labelled images, sorted by filename, from
`batch_1/batch_1/batch1_1` in version **3** of
[High-Quality Invoice Images for OCR](https://www.kaggle.com/datasets/osamahosamabdellatif/high-quality-invoice-images-for-ocr),
created by **osama hosam Abdellatif**. Downloaded on 2026-11-03.

The database and this derived label sample are made available under the
[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Individual contents are covered by the
[Database Contents License (DbCL) 1.0](https://opendatacommons.org/licenses/dbcl/1-0/).
These licenses apply to this sample, not to the application code.

The three JPEGs are unchanged. Their SHA-256 checksums, original paths, source
CSV checksum, and sample version are recorded in [manifest.json](manifest.json).
The loader checks every image before processing any Invoice. Change the version
when changing the sample or labels; retain old versions for comparisons.

Labels come from the matching `File Name` rows of `batch1_1.csv`, parsed as CSV
and then JSON. `invoice.seller_name`, `invoice.invoice_number`,
`invoice.invoice_date`, item descriptions and quantities, `subtotal.tax`, and
`subtotal.total` map to the application's fields. Dates use month/day/year and
are stored as ISO dates. Decimal commas become decimal points and thousands
spaces are removed. Upstream descriptions are preserved, including their
spelling and accent inconsistencies. Gross item totals are not unit prices.

Only labelled fields are scored. Currency, net subtotal, unit prices, item
codes, and Purchase Order numbers are not labelled here and are not scored.
Each labelled header or line value counts once; overall accuracy is correct
values divided by all scored values. Strings match exactly, numbers compare as
Decimals, dates compare as dates, and lines are compared in their printed order.
Missing and extra lines count as errors for the labelled line fields.

[fake.json](fake.json) contains separate scripted responses and an explicit
score baseline: one wrong total, one wrong quantity, and one unreadable Invoice.
That gives **32/45 (71.11%)**, not a real model's accuracy. The runner never
copies labels into its fake responses. CI checks every field and the overall
score, including failures, against this baseline.

This is a tiny repeatable check, not a representative quality estimate. Some
images in the source dataset may be synthetic. Real-model runs and cost/time
reporting belong to the separate cost/time ticket.
