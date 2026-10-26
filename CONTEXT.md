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
The check that an Invoice agrees with its Purchase Order and its Goods Receipt on items, quantities and prices. A line passes when the invoiced quantity equals the received quantity, the received quantity does not exceed the ordered quantity, and the price is within the Price Tolerance.
_Avoid_: Reconciliation, matching (alone)

**Price Tolerance**:
How much higher an Invoice line's unit price may be than its Purchase Order line and still pass: 2%. A lower price always passes.
_Avoid_: Variance, margin

**Duplicate Invoice**:
An Invoice with the same Supplier and Invoice number as one already received.
_Avoid_: Resubmission

**Possible Duplicate**:
An Invoice with a different number but the same Supplier and total as another received within 30 days. Always goes to the Review Queue.
_Avoid_: Suspected duplicate, near-duplicate

**Auto-Approval**:
The agent approving an Invoice without a Reviewer. Allowed only for a known Supplier, a passing Three-Way Match, no Duplicate Invoice or Possible Duplicate, and a total under the Auto-Approval Limit.
_Avoid_: Straight-through processing

**Auto-Approval Limit**:
The highest Invoice total the agent may approve on its own. A change applies only to Invoices not yet decided.
_Avoid_: Threshold, cap

**Invoice Status**:
Where an Invoice is in its life: Processing, In Review, Auto-Approved, Approved or Rejected. The last three are final.
_Avoid_: State, stage

**Rejection Reason**:
The Reviewer's required explanation for rejecting an Invoice.
_Avoid_: Comment, note

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
