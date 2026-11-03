import logging
from datetime import UTC, datetime, timedelta
from typing import Literal, NotRequired, TypedDict
from uuid import UUID, uuid4

import psycopg
from langgraph.graph import END, START, StateGraph
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import JsonValue

from invoice_agent.clients.invoice_reader import InvoiceReader
from invoice_agent.clients.line_pairing import LinePairer
from invoice_agent.clients.tracing import RunTracing
from invoice_agent.schemas.erp_tools import GoodsReceipt, PurchaseOrder, Supplier
from invoice_agent.schemas.invoices import InvoiceDetail, InvoiceFile
from invoice_agent.schemas.three_way_match import LineComparison, PairedLine
from invoice_agent.services.daily_ai_limit import DailyAILimit
from invoice_agent.services.erp_tools import ERPTools
from invoice_agent.services.invoices import (
    InvoiceNotFound,
    Invoices,
    skip_pending_steps,
)
from invoice_agent.services.three_way_match import compare_lines, pair_lines

logger = logging.getLogger(__name__)

INVOICE_STEPS = (
    "Read Invoice",
    "Find Supplier",
    "Find Purchase Order",
    "Find Goods Receipt",
    "Pair Lines",
    "Three-Way Match",
    "Check Duplicates",
    "Decide",
)


class InvoiceRun(TypedDict):
    company_id: UUID
    invoice_id: UUID
    supplier: NotRequired[Supplier]
    purchase_order: NotRequired[PurchaseOrder]
    goods_receipt: NotRequired[GoodsReceipt | None]
    record_reasons: NotRequired[list[str]]
    paired_lines: NotRequired[list[PairedLine]]
    comparison: NotRequired[list[LineComparison]]
    duplicate_reasons: NotRequired[list[str]]


class InvoiceProcessing(Invoices):
    def __init__(
        self,
        database_url: str,
        reader: InvoiceReader,
        erp_tools: ERPTools,
        daily_ai_limit: DailyAILimit,
        line_pairer: LinePairer | None = None,
        tracing: RunTracing | None = None,
    ) -> None:
        super().__init__(database_url)
        self.reader = reader
        self.erp_tools = erp_tools
        self.daily_ai_limit = daily_ai_limit
        self.line_pairer = line_pairer
        self.tracing = tracing or RunTracing()
        graph = StateGraph(InvoiceRun)
        graph.add_sequence(
            [
                ("read_invoice", self._read_invoice),
                ("find_supplier", self._find_supplier),
                ("find_purchase_order", self._find_purchase_order),
                ("find_goods_receipt", self._find_goods_receipt),
                ("pair_lines", self._pair_lines),
                ("three_way_match", self._three_way_match),
                ("check_duplicates", self._check_duplicates),
                ("decide", self._decide),
            ]
        )
        graph.add_edge(START, "read_invoice")
        graph.add_edge("decide", END)
        self.graph = graph.compile()

    def upload(
        self,
        company_id: UUID,
        document: InvoiceFile,
        *,
        submitted_by: str = "submitter",
    ) -> InvoiceDetail:
        invoice_id = uuid4()
        now = datetime.now(UTC)
        with psycopg.connect(self.database_url) as connection:
            inserted = connection.execute(
                """INSERT INTO invoices
                   (id, company_id, status, created_at,
                    file_name, content_type, file_content, submitted_by)
                   SELECT %s, id, 'Processing', %s, %s, %s, %s, %s
                   FROM demo_companies WHERE id = %s AND expires_at > %s
                   RETURNING id""",
                (
                    invoice_id,
                    now,
                    document.filename,
                    document.content_type,
                    document.content,
                    submitted_by,
                    company_id,
                    now,
                ),
            ).fetchone()
            if inserted is None:
                raise InvoiceNotFound("Demo Company not found.")
            for position, name in enumerate(INVOICE_STEPS):
                connection.execute(
                    """INSERT INTO invoice_steps
                       (company_id, invoice_id, name, position, status, inputs)
                       VALUES (%s, %s, %s, %s, 'Pending', %s)""",
                    (
                        company_id,
                        invoice_id,
                        name,
                        position,
                        Jsonb(
                            {
                                "filename": document.filename,
                                "content_type": document.content_type,
                            }
                            if position == 0
                            else {}
                        ),
                    ),
                )
        return self._require(company_id, invoice_id)

    def process(self, company_id: UUID, invoice_id: UUID) -> InvoiceDetail:
        with self.tracing.run(company_id, invoice_id) as trace:
            if trace.url is not None:
                with psycopg.connect(self.database_url) as connection:
                    connection.execute(
                        """UPDATE invoices SET trace_url = %s
                           WHERE company_id = %s AND id = %s""",
                        (trace.url, company_id, invoice_id),
                    )
            self.graph.invoke(
                {"company_id": company_id, "invoice_id": invoice_id},
                config={"callbacks": trace.callbacks},
            )
            result = self._require(company_id, invoice_id)
            trace.complete(result)
        return result

    def _read_invoice(self, state: InvoiceRun) -> InvoiceRun:
        company_id, invoice_id = state["company_id"], state["invoice_id"]
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            claimed = connection.execute(
                """UPDATE invoice_steps SET status = 'Running', started_at = %s
                   WHERE company_id = %s AND invoice_id = %s AND status = 'Pending'
                     AND name = 'Read Invoice'
                     AND EXISTS (SELECT 1 FROM demo_companies
                                 WHERE id = %s AND expires_at > %s)
                   RETURNING invoice_id""",
                (
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                    company_id,
                    datetime.now(UTC),
                ),
            ).fetchone()
            if claimed is None:
                return state
            stored = connection.execute(
                """SELECT file_name, content_type, file_content FROM invoices
                   WHERE company_id = %s AND id = %s""",
                (company_id, invoice_id),
            ).fetchone()
        if stored is None:
            raise InvoiceNotFound("Invoice not found.")
        try:
            if self.reader.uses_live_model and not self.daily_ai_limit.reserve(
                company_id
            ):
                self._fail_read(company_id, invoice_id, "daily AI limit reached")
                return state
            fields = self.reader.read(
                InvoiceFile(
                    filename=stored["file_name"],
                    content_type=stored["content_type"],
                    content=bytes(stored["file_content"]),
                )
            )
        except Exception:
            logger.exception("Invoice reading failed for %s", invoice_id)
            self._fail_read(
                company_id,
                invoice_id,
                "Invoice reading is unavailable. "
                "A Reviewer needs to check this Invoice.",
            )
            return state
        if fields is None:
            self._fail_read(
                company_id, invoice_id, "This file could not be read as an Invoice."
            )
            return state
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """UPDATE invoices SET supplier_name = %s, invoice_number = %s,
                          total = %s, currency = %s, issued_on = %s,
                          read_fields = %s
                   WHERE company_id = %s AND id = %s""",
                (
                    fields.supplier_name,
                    fields.invoice_number,
                    fields.total,
                    fields.currency,
                    fields.issued_on,
                    Jsonb(fields.model_dump(mode="json")),
                    company_id,
                    invoice_id,
                ),
            )
            for line in fields.lines:
                connection.execute(
                    """INSERT INTO invoice_lines
                       (id, company_id, invoice_id, item_code,
                        description, quantity, unit_price)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (
                        uuid4(),
                        company_id,
                        invoice_id,
                        line.item_code,
                        line.description,
                        line.quantity,
                        line.unit_price,
                    ),
                )
            connection.execute(
                """UPDATE invoice_steps SET status = 'Completed', outputs = %s,
                          completed_at = %s
                                     WHERE company_id = %s AND invoice_id = %s
                                         AND name = 'Read Invoice'""",
                (
                    Jsonb(fields.model_dump(mode="json")),
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                ),
            )
        return state

    def _find_supplier(self, state: InvoiceRun) -> InvoiceRun:
        company_id, invoice_id = state["company_id"], state["invoice_id"]
        invoice = self._require(company_id, invoice_id)
        if invoice.fields is None:
            return state
        name = invoice.fields.supplier_name
        with psycopg.connect(self.database_url) as connection:
            claimed = connection.execute(
                """UPDATE invoice_steps SET status = 'Running', inputs = %s,
                          started_at = %s
                   WHERE company_id = %s AND invoice_id = %s
                     AND name = 'Find Supplier' AND status = 'Pending'
                   RETURNING invoice_id""",
                (
                    Jsonb({"name": name}),
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                ),
            ).fetchone()
        if claimed is None:
            return state
        outputs: dict[str, JsonValue]
        reason: str | None
        try:
            supplier = self.tracing.tool(
                "find_supplier", self.erp_tools.find_supplier, company_id, name
            )
        except Exception:
            logger.exception("Supplier lookup failed for %s", invoice_id)
            supplier = None
            reason = (
                "Supplier lookup is unavailable. "
                "A Reviewer needs to check this Invoice."
            )
            step_status = "Failed"
            outputs = {"reason": reason}
        else:
            reason = None if supplier is not None else "Unknown Supplier"
            step_status = "Completed"
            outputs = {
                "supplier": supplier.model_dump(mode="json")
                if supplier is not None
                else None
            }
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """UPDATE invoices SET supplier_id = %s,
                          status = 'In Review', reasons = %s
                   WHERE company_id = %s AND id = %s""",
                (
                    supplier.id if supplier is not None else None,
                    Jsonb([reason] if reason is not None else []),
                    company_id,
                    invoice_id,
                ),
            )
            connection.execute(
                """UPDATE invoice_steps SET status = %s, outputs = %s,
                          completed_at = %s
                   WHERE company_id = %s AND invoice_id = %s
                     AND name = 'Find Supplier'""",
                (
                    step_status,
                    Jsonb(outputs),
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                ),
            )
            if reason is not None:
                skip_pending_steps(connection, company_id, invoice_id, reason)
            else:
                connection.execute(
                    """UPDATE invoices SET status = 'Processing'
                       WHERE company_id = %s AND id = %s""",
                    (company_id, invoice_id),
                )
        if supplier is not None:
            return {**state, "supplier": supplier}
        return state

    def _find_purchase_order(self, state: InvoiceRun) -> InvoiceRun:
        supplier = state.get("supplier")
        if supplier is None:
            return state
        company_id, invoice_id = state["company_id"], state["invoice_id"]
        invoice = self._require(company_id, invoice_id)
        if invoice.fields is None:
            return state
        number = invoice.fields.purchase_order_number
        if not self._start_step(
            company_id, invoice_id, "Find Purchase Order", {"number": number}
        ):
            return state
        try:
            purchase_order = (
                self.tracing.tool(
                    "get_purchase_order",
                    self.erp_tools.get_purchase_order,
                    company_id,
                    supplier.id,
                    number.strip(),
                )
                if number is not None and number.strip()
                else None
            )
        except Exception:
            logger.exception("Purchase Order lookup failed for %s", invoice_id)
            reason = (
                "Purchase Order lookup is unavailable. "
                "A Reviewer needs to check this Invoice."
            )
            self._complete_step(
                company_id,
                invoice_id,
                "Find Purchase Order",
                {"reason": reason},
                status="Failed",
            )
            return {**state, "record_reasons": [reason]}
        self._complete_step(
            company_id,
            invoice_id,
            "Find Purchase Order",
            {
                "purchase_order": purchase_order.model_dump(mode="json")
                if purchase_order is not None
                else None
            },
        )
        if purchase_order is None:
            reason = (
                f"Purchase Order {number} was not found for this Supplier."
                if number is not None and number.strip()
                else "No Purchase Order is named on this Invoice."
            )
            return {**state, "record_reasons": [reason]}
        return {**state, "purchase_order": purchase_order}

    def _find_goods_receipt(self, state: InvoiceRun) -> InvoiceRun:
        purchase_order = state.get("purchase_order")
        if purchase_order is None:
            return state
        company_id, invoice_id = state["company_id"], state["invoice_id"]
        if not self._start_step(
            company_id,
            invoice_id,
            "Find Goods Receipt",
            {"purchase_order_id": str(purchase_order.id)},
        ):
            return state
        try:
            goods_receipt = self.tracing.tool(
                "get_goods_receipt",
                self.erp_tools.get_goods_receipt,
                company_id,
                purchase_order.id,
            )
        except Exception:
            logger.exception("Goods Receipt lookup failed for %s", invoice_id)
            reason = (
                "Goods Receipt lookup is unavailable. "
                "A Reviewer needs to check this Invoice."
            )
            self._complete_step(
                company_id,
                invoice_id,
                "Find Goods Receipt",
                {"reason": reason},
                status="Failed",
            )
            return {**state, "goods_receipt": None, "record_reasons": [reason]}
        self._complete_step(
            company_id,
            invoice_id,
            "Find Goods Receipt",
            {
                "goods_receipt": goods_receipt.model_dump(mode="json")
                if goods_receipt is not None
                else None
            },
        )
        if goods_receipt is None:
            reason = (
                "No Goods Receipt was found for Purchase Order "
                f"{purchase_order.number}."
            )
            return {**state, "goods_receipt": None, "record_reasons": [reason]}
        return {**state, "goods_receipt": goods_receipt}

    def _pair_lines(self, state: InvoiceRun) -> InvoiceRun:
        purchase_order = state.get("purchase_order")
        if purchase_order is None:
            return state
        company_id, invoice_id = state["company_id"], state["invoice_id"]
        invoice = self._require(company_id, invoice_id)
        if invoice.fields is None or not self._start_step(
            company_id,
            invoice_id,
            "Pair Lines",
            {
                "invoice_lines": [
                    line.model_dump(mode="json") for line in invoice.fields.lines
                ],
                "purchase_order_id": str(purchase_order.id),
            },
        ):
            return state
        pairs = pair_lines(invoice.fields.lines, purchase_order)
        used = {pair.purchase_order.id for pair in pairs if pair.purchase_order}
        searches: list[JsonValue] = []
        pairing_reasons: list[str] = []
        failed = False
        for pair in pairs:
            if pair.purchase_order is not None or self.line_pairer is None:
                continue
            try:
                candidates = self.tracing.tool(
                    "search_purchase_order_lines",
                    self.erp_tools.search_purchase_order_lines,
                    company_id,
                    purchase_order.id,
                    pair.invoice.description,
                    item_code=pair.invoice.item_code,
                    excluded_ids=tuple(used),
                )
                if (
                    candidates
                    and self.line_pairer.uses_live_model
                    and not self.daily_ai_limit.reserve(company_id)
                ):
                    pairing_reasons.append("daily AI limit reached")
                    failed = True
                    break
                selected_id = (
                    self.line_pairer.choose(pair.invoice, candidates)
                    if candidates
                    else None
                )
                searches.append(
                    {
                        "line_number": pair.line_number,
                        "candidates": [
                            candidate.model_dump(mode="json")
                            for candidate in candidates
                        ],
                    }
                )
                selected = next(
                    (
                        candidate
                        for candidate in candidates
                        if candidate.id == selected_id
                    ),
                    None,
                )
                if selected is not None:
                    pair.purchase_order = selected
                    pair.paired_by = "meaning"
                    used.add(selected.id)
            except Exception:
                logger.exception("Line pairing failed for %s", invoice_id)
                pair.pairing_reason = (
                    f"Line {pair.line_number} ({pair.invoice.description}): "
                    "line pairing is unavailable. A Reviewer needs to check this line."
                )
                failed = True
        self._complete_step(
            company_id,
            invoice_id,
            "Pair Lines",
            {
                "pairs": [pair.model_dump(mode="json") for pair in pairs],
                "candidate_searches": searches,
                "reasons": [reason for reason in pairing_reasons],
            },
            status="Failed" if failed else "Completed",
        )
        return {
            **state,
            "paired_lines": pairs,
            "record_reasons": state.get("record_reasons", []) + pairing_reasons,
        }

    def _three_way_match(self, state: InvoiceRun) -> InvoiceRun:
        pairs, goods_receipt = state.get("paired_lines"), state.get("goods_receipt")
        if pairs is None:
            return state
        company_id, invoice_id = state["company_id"], state["invoice_id"]
        if not self._start_step(
            company_id,
            invoice_id,
            "Three-Way Match",
            {
                "pairs": [pair.model_dump(mode="json") for pair in pairs],
                "goods_receipt": goods_receipt.model_dump(mode="json")
                if goods_receipt is not None
                else None,
            },
        ):
            return state
        comparison = compare_lines(pairs, goods_receipt)
        serialized: list[JsonValue] = [
            line.model_dump(mode="json") for line in comparison
        ]
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """UPDATE invoices SET comparison = %s
                   WHERE company_id = %s AND id = %s""",
                (Jsonb(serialized), company_id, invoice_id),
            )
        self._complete_step(
            company_id,
            invoice_id,
            "Three-Way Match",
            {
                "passed": all(
                    line.price_passed and line.quantity_passed for line in comparison
                ),
                "comparison": serialized,
            },
        )
        return {**state, "comparison": comparison}

    def _check_duplicates(self, state: InvoiceRun) -> InvoiceRun:
        supplier = state.get("supplier")
        if supplier is None:
            return state
        company_id, invoice_id = state["company_id"], state["invoice_id"]
        invoice = self._require(company_id, invoice_id)
        if invoice.fields is None or not self._start_step(
            company_id,
            invoice_id,
            "Check Duplicates",
            {"supplier_id": str(supplier.id)},
        ):
            return state
        try:
            earlier_invoices = self.tracing.tool(
                "find_earlier_invoices",
                self.erp_tools.find_earlier_invoices,
                company_id,
                supplier.id,
                invoice_id,
            )
        except Exception:
            logger.exception("Duplicate Invoice check failed for %s", invoice_id)
            reason = (
                "Duplicate Invoice check is unavailable. "
                "A Reviewer needs to check this Invoice."
            )
            self._complete_step(
                company_id,
                invoice_id,
                "Check Duplicates",
                {"reason": reason},
                status="Failed",
            )
            return {**state, "duplicate_reasons": [reason]}
        duplicates: list[JsonValue] = []
        reasons: list[str] = []
        for earlier in earlier_invoices:
            if earlier.invoice_number == invoice.fields.invoice_number:
                reason = (
                    f"Duplicate Invoice: {earlier.invoice_number} was already received."
                )
            elif (
                earlier.total == invoice.fields.total
                and invoice.received_at - earlier.received_at <= timedelta(days=30)
            ):
                reason = (
                    f"Possible Duplicate: {earlier.invoice_number} has the same total "
                    "and was received within 30 days."
                )
            else:
                continue
            reasons.append(reason)
            duplicates.append(
                {
                    "invoice_id": str(earlier.id),
                    "invoice_number": earlier.invoice_number,
                    "reason": reason,
                }
            )
        self._complete_step(
            company_id, invoice_id, "Check Duplicates", {"duplicates": duplicates}
        )
        return {**state, "duplicate_reasons": reasons}

    def _decide(self, state: InvoiceRun) -> InvoiceRun:
        duplicate_reasons = state.get("duplicate_reasons")
        if duplicate_reasons is None:
            return state
        comparison = state.get("comparison")
        company_id, invoice_id = state["company_id"], state["invoice_id"]
        invoice = self._require(company_id, invoice_id)
        matching_reasons = state.get("record_reasons", []) + [
            reason for line in comparison or [] for reason in line.reasons
        ]
        three_way_match_passed = comparison is not None and not matching_reasons
        with psycopg.connect(self.database_url) as connection:
            company = connection.execute(
                """SELECT auto_approval_limit, currency FROM demo_companies
                   WHERE id = %s AND expires_at > %s FOR SHARE""",
                (company_id, datetime.now(UTC)),
            ).fetchone()
            if company is None:
                raise InvoiceNotFound("Demo Company not found.")
            limit, currency = company
            claimed = connection.execute(
                """UPDATE invoice_steps SET status = 'Running', inputs = %s,
                          started_at = %s
                   WHERE company_id = %s AND invoice_id = %s
                     AND name = 'Decide' AND status = 'Pending'
                   RETURNING invoice_id""",
                (
                    Jsonb(
                        {
                            "three_way_match_passed": three_way_match_passed,
                            "duplicate_check_passed": not duplicate_reasons,
                            "total": str(invoice.total),
                            "currency": invoice.currency,
                            "auto_approval_limit": str(limit),
                            "auto_approval_currency": currency,
                        }
                    ),
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                ),
            ).fetchone()
            if claimed is None:
                return state
            reasons = matching_reasons + duplicate_reasons
            if invoice.currency != currency:
                reasons.append(
                    f"Invoice currency {invoice.currency} does not match "
                    f"the Demo Company currency {currency}."
                )
            elif invoice.total is None or invoice.total >= limit:
                reasons.append(
                    "Invoice total is at or above the Auto-Approval Limit of "
                    f"{currency} {limit:,.2f}."
                )
            status = (
                "Auto-Approved"
                if three_way_match_passed and not reasons
                else "In Review"
            )
            connection.execute(
                """UPDATE invoices SET status = %s, reasons = %s,
                          auto_approval_limit = %s
                   WHERE company_id = %s AND id = %s""",
                (status, Jsonb(reasons), limit, company_id, invoice_id),
            )
            connection.execute(
                """UPDATE invoice_steps SET status = 'Completed', outputs = %s,
                          completed_at = %s
                   WHERE company_id = %s AND invoice_id = %s AND name = 'Decide'""",
                (
                    Jsonb({"status": status, "reasons": reasons}),
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                ),
            )
            if reasons:
                skip_pending_steps(connection, company_id, invoice_id, reasons[0])
        return state

    def _start_step(
        self,
        company_id: UUID,
        invoice_id: UUID,
        name: str,
        inputs: dict[str, JsonValue],
    ) -> bool:
        with psycopg.connect(self.database_url) as connection:
            claimed = connection.execute(
                """UPDATE invoice_steps SET status = 'Running', inputs = %s,
                          started_at = %s
                   WHERE company_id = %s AND invoice_id = %s
                     AND name = %s AND status = 'Pending' RETURNING invoice_id""",
                (Jsonb(inputs), datetime.now(UTC), company_id, invoice_id, name),
            ).fetchone()
        return claimed is not None

    def _complete_step(
        self,
        company_id: UUID,
        invoice_id: UUID,
        name: str,
        outputs: dict[str, JsonValue],
        status: Literal["Completed", "Failed"] = "Completed",
    ) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """UPDATE invoice_steps SET status = %s, outputs = %s,
                          completed_at = %s
                   WHERE company_id = %s AND invoice_id = %s AND name = %s""",
                (
                    status,
                    Jsonb(outputs),
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                    name,
                ),
            )

    def _send_to_review(
        self,
        company_id: UUID,
        invoice_id: UUID,
        reasons: list[str],
        skip_reason: str | None = None,
    ) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """UPDATE invoices SET status = 'In Review', reasons = %s
                   WHERE company_id = %s AND id = %s""",
                (Jsonb(reasons), company_id, invoice_id),
            )
            skip_pending_steps(
                connection, company_id, invoice_id, skip_reason or reasons[0]
            )

    def _fail_read(self, company_id: UUID, invoice_id: UUID, reason: str) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """UPDATE invoices SET status = 'In Review', reasons = %s
                   WHERE company_id = %s AND id = %s""",
                (Jsonb([reason]), company_id, invoice_id),
            )
            connection.execute(
                """UPDATE invoice_steps SET status = 'Failed', outputs = %s,
                          completed_at = %s
                                     WHERE company_id = %s AND invoice_id = %s
                                         AND name = 'Read Invoice'""",
                (
                    Jsonb({"reason": reason}),
                    datetime.now(UTC),
                    company_id,
                    invoice_id,
                ),
            )
            skip_pending_steps(connection, company_id, invoice_id, reason)
