# The agent reaches the ERP only through an MCP server

The ERP is a small set of Postgres tables we own, but the agent never queries them directly: every read and write goes through tools on an MCP server. Integrating a real ERP (Odoo, ERPNext) would make the project mostly about that ERP rather than the agent, and direct database access would hide the boundary a real company has. Swapping the MCP server is all it takes to point the agent at a real ERP.
