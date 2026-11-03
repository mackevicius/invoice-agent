# Generated Invoice sample v1

Four fictional Invoices created for this repository on 2026-11-03:

- [invoice-clean.png](invoice-clean.png): a portrait Invoice with two lines.
- [invoice-compact.png](invoice-compact.png): a landscape Invoice with three lines.
- [invoice-single-page.pdf](invoice-single-page.pdf): a text-based, single-page PDF.
- [invoice-multi-page.pdf](invoice-multi-page.pdf): a text-based, two-page PDF;
  three lines appear on each page and totals appear only on the second page.

All Supplier names, Invoice numbers, Purchase Order numbers, and amounts are
fictional. These are original synthetic examples, not Kaggle data. The original
JPEG sample and its ODbL attribution remain unchanged.

[manifest.json](manifest.json) records every image/PDF checksum and the correct
Supplier, Invoice number, Purchase Order number, date, currency, line fields,
subtotal, tax, and total. Line quantities and unit prices add up to the printed
subtotal; subtotal plus tax equals the total. The sample contains 84 labelled
values across four Invoices. Retain this version unchanged when adding samples.

[fake.json](fake.json) stores separate fake responses. The single-page PDF has
one deliberately incorrect fake total (`81.61` instead of `81.60`), so the
expected fake score is **83/84 (98.81%)**. These responses are not generated from
the labels when running the evaluation.

From the repository root, run:

```sh
docker compose run --rm api uv run --locked python -m evals.reading --sample-dir evals/data/generated-v1 --check
```

Results are saved under `api/evals/results/`, separately from the original
JPEG sample. CI runs both samples and retains their result files.

The PNGs were rendered at twice the PDF page dimensions. Both PDFs contain
selectable text, not scanned pages. File dimensions, PDF page counts, text, and
page placement of lines and totals were checked during generation.

The fake run verifies the evaluation workflow and scoring for these file types;
it does not measure a real model's ability to read them. Scanned PDFs, rotated
or low-quality documents, and real-model accuracy remain outside this sample.
