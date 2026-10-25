# Invoice Agent

An agent that checks incoming supplier invoices against the company's purchase records, then approves them or sends them to a person for review.

## Language

**Invoice**:
A request for payment that a Supplier sends to the company.
_Avoid_: Bill, receipt

**Supplier**:
A business the company buys from and pays.
_Avoid_: Vendor, seller

**Purchase Order**:
The company's own record of what it agreed to buy from a Supplier, at what price and quantity.
_Avoid_: PO (in prose), order

**Goods Receipt**:
The company's record that ordered goods actually arrived, and how many.
_Avoid_: Delivery note, GRN

**Three-Way Match**:
The check that an Invoice agrees with its Purchase Order and its Goods Receipt on items, quantities and prices.
_Avoid_: Reconciliation, matching (alone)

**Price Tolerance**:
How far an Invoice line's unit price may differ from its Purchase Order line and still pass: 2%. Quantities have no tolerance.
_Avoid_: Variance, margin

**Duplicate Invoice**:
An Invoice the company has already received from the same Supplier for the same charge.
_Avoid_: Resubmission

**Auto-Approval**:
The agent approving an Invoice without a Reviewer. Allowed only for a known Supplier, a passing Three-Way Match, no Duplicate Invoice, and a total under the Auto-Approval Limit.
_Avoid_: Straight-through processing

**Auto-Approval Limit**:
The highest Invoice total the agent may approve on its own.
_Avoid_: Threshold, cap

**ERP**:
The company's system of record for Suppliers, Purchase Orders and payments. The agent reaches it only through tools.
_Avoid_: Backend, database

**Review Queue**:
The list of Invoices the agent did not approve on its own, waiting for a Reviewer.
_Avoid_: Inbox, backlog

## People

**Submitter**:
The person who uploads Invoices.
_Avoid_: Uploader, user

**Reviewer**:
The person who approves or rejects Invoices in the Review Queue. Never one they submitted.
_Avoid_: Agent (reserved for the AI), approver, user

**Admin**:
The person who sets the Auto-Approval Limit.
_Avoid_: Owner, manager

## Demo

**Demo Company**:
A private, temporary copy of the ERP data given to one visitor for 24 hours.
_Avoid_: Sandbox, tenant, workspace
