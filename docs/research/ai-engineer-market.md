# AI Engineer job market: what to build next

Research date: 2026-10-25. Every number below comes from a linked source. Lines marked **Inference** are my own reading of the numbers. They are not measured facts.

## 1. TL;DR

- **Must-have stack:** Python, calling LLM APIs with tool calling (also called function calling), RAG (search your own data, then give the results to the model), evals (tests that score model output), one cloud, Postgres/SQL and Docker. These show up again and again in postings and surveys.
- **Your TypeScript/React skills count.** In 249 Hacker News job posts that mention LLMs, Python appears in 45%, TypeScript in 35% and React in 36%. Many startup "AI application engineer" jobs are full-stack TypeScript jobs.
- **In Lithuania, Python and Microsoft/Azure lead.** Postings mention Python 7 times in 8 and Azure or other Microsoft tools 6 times in 8. Only 1 in 8 mentions TypeScript.
- **Nice to have:** LangGraph, MCP (Model Context Protocol, a standard way to plug tools into an agent), tracing tools such as Langfuse or LangSmith, FastAPI and Kubernetes.
- **Overrated for getting hired:** named multi-agent frameworks (CrewAI, AutoGen, Mastra), dedicated vector databases (Pinecone, Qdrant, Weaviate), A2A, and fine-tuning. Each shows up in very few postings.
- **Postings rarely name a framework.** Across 6 months of Hacker News hiring threads, "evals" appears 70 times, "MCP" 46 times, "LangChain" 21 times and "LangGraph" 16 times. Employers ask for skills, not libraries.
- **Top 3 business use cases you can build for:** (1) customer support agents, (2) internal knowledge search and research/data analysis, (3) back-office workflow automation in finance, HR, ops and billing. Document extraction is a close fourth.
- **Coding tools get the most money, but companies buy them.** Coding takes $4.0B, or 55% of departmental AI spend. But 76% of AI use cases are bought, not built. **Inference:** a coding-agent project will not show employers much.

## 2. Technology demand table

Columns:
- **Sample** is my hand-read sample of 34 AI-building job posts: 8 Lithuanian posts and 26 Hacker News posts (see section 6).
- **HN-6mo** is a keyword count over 2,609 Hacker News "Who is hiring" comments from May to October 2026. "/249" means the count among the 249 comments that also say "LLM".
- **Surveys** are SO 2026 (Stack Overflow Developer Survey 2026, people who build agents) and LC (LangChain State of Agent Engineering).
- **Downloads** are for the last month, from the official PyPI and npm registries.

| Tech | Sample (n/34) | HN-6mo | Surveys | Downloads (last month) | Verdict |
|---|---|---|---|---|---|
| Python | 16 | 111/249 | — | fastapi 381.6M (PyPI) | **Must-have** |
| TypeScript / JS | 10 | 86/249 | — | `ai` (Vercel) 112.0M (npm) | **Strong plus** (must-have for full-stack AI roles) |
| React / Next.js | 9 | react 90/249 | — | — | **Strong plus** (you already have it) |
| Node.js | 4 | 38/249 | — | — | Strong plus |
| Agents / tool calling (as a skill) | 19 | "agentic" 175 | 57.3% have agents in production (LC) | — | **Must-have** |
| RAG / retrieval / embeddings | 13 | "RAG" 57 | Prompting + RAG is the most common setup (Menlo) | — | **Must-have** |
| Evals / output testing | 10 | "evals" 70 | Offline evals 52.4%, LLM-as-judge 53.3% (LC) | — | **Must-have** |
| Observability / tracing (as a skill) | 2 | — | 89% have some observability (LC) | — | **Must-have skill**. The tool brand does not matter. |
| MCP | 6 | 46 | MCP servers 34.4% (SO 2025) | `@modelcontextprotocol/sdk` 240.1M npm; `mcp` 235.2M PyPI | **Strong plus** |
| Postgres / SQL | 7 PG (+2 SQL) | postgres 40/249 (undercount) | pgvector 17.9% (SO 2025) | — | **Must-have** |
| Docker | 4 | 28/249 | — | — | **Must-have** (cheap to show) |
| Kubernetes | 4 | 17/249 | — | — | Strong plus |
| Terraform | 0 | 14/249 | — | — | Niche |
| AWS | 9 | 60/249 | Bedrock Agents 14.5% (SO 2025) | — | **Must-have: pick one cloud** (AWS globally) |
| Azure (incl. Azure OpenAI, Foundry, Fabric) | 8 (6 of 8 in LT) | 20/249 | — | — | **Must-have in Lithuania**, plus elsewhere |
| GCP / Vertex | 4 | 23/249; "vertex" 1 | Vertex 15.1% (SO 2025) | — | Niche to plus |
| Bedrock (named) | 0 | 4 | 14.5% (SO 2025) | — | Niche |
| LangGraph | 2 | 16 | 18.8% (SO 2026) | 44.8M PyPI; 13.9M npm | **Strong plus** (the framework to pick if you pick one) |
| LangChain | 3 | 21 | 30.2% (SO 2026) | 170.5M PyPI; 11.6M npm | Strong plus (people know the name) |
| OpenAI Agents SDK | 0 | "openai agents" 0 | 23.8% (SO 2026) | 12.4M PyPI; 7.8M npm | Plus (popular with devs, not named by employers) |
| LlamaIndex | 1 | 7 | 13.3% (SO 2025) | llama-index-core 6.6M PyPI; npm 0.53M | Niche |
| CrewAI | 1 | 5 | 5.5% (SO 2026) | 2.4M PyPI | Niche / overrated |
| Pydantic AI | 0 | "pydantic" 7 | 8.9% (SO 2026) | 5.4M PyPI | Niche |
| Vercel AI SDK | 0 | 0 | 9.0% (SO 2026) | 112.0M npm | Plus for the TypeScript lane |
| Mastra | 0 | 2 | 3.0% (SO 2026) | 7.7M npm | Niche |
| FastAPI | 2 | 16/249 | — | 381.6M PyPI | Strong plus (the default Python API layer) |
| Langfuse | 0 | 3 | 15.2% (SO 2026) | 23.6M PyPI; 7.2M npm | Strong plus as a way to show tracing |
| LangSmith | 0 | 2 | 17.3% (SO 2026) | 77.2M PyPI | Plus (often installed along with LangChain) |
| Arize Phoenix | 0 | — | Arize 5.8% (SO 2026) | 0.63M PyPI | Niche |
| Braintrust | 0 | 1 | 5.8% (SO 2026) | 6.6M PyPI | Niche |
| promptfoo | 0 | 0 | 5.3% (SO 2026) | 3.1M npm | Niche (but cheap to add) |
| Ragas | 0 | 0 | 4.9% (SO 2026) | 1.05M PyPI | Niche |
| DeepEval | 0 | — | 5.8% (SO 2026) | 2.6M PyPI | Niche |
| OpenTelemetry | 0 | 5 | — | — | Niche in AI posts |
| pgvector | 0 | 0 | 17.9% (SO 2025) | — | Plus (no extra service; fits Postgres) |
| Pinecone / Qdrant / Weaviate | 0 | 1 / 1 / 1 | 11.2% / 8.2% / 4.5% (SO 2025) | — | Niche / overrated |
| Azure AI Search / OpenSearch | 0 / 0 | — / 5 | — | — | Niche ("vector search" asked in general: 2) |
| A2A | 0 | 3 | — | — | Hype for now |
| Kafka | 0 | 31 (all posts) | — | — | Niche for AI roles |
| Temporal | 0 | 18 (all posts) | 6.0% (SO 2026) | — | Niche |
| SQS | 0 | 4 | — | — | Niche |
| n8n / Make (low-code automation) | 1 | — | Make 38.9%, n8n 32.7% (SO 2026) | — | Niche for engineers. Common in ops teams. |
| Fine-tuning | 3 | "fine-tuning" 12 | 57% do NOT fine-tune (LC) | — | Niche |
| Classic ML (PyTorch, TF, scikit-learn) | 3 | — | — | — | Niche for LLM-app roles. Asked by consultancies. |

**Inference, how to read this:** Employers ask for skills ("built agents", "ran evals", "RAG in production") much more often than library names. The frameworks with real reach are LangChain/LangGraph and the OpenAI Agents SDK. Even so, only a handful of postings name any framework.

## 3. Python vs TypeScript

**Measured:**

- Hacker News, 249 posts that mention LLMs (May–Oct 2026): Python 111 (45%), TypeScript 86 (35%), React 90 (36%), Node 38 (15%).
- My sample of 34 posts: Python 16, TypeScript/JS 10. In Lithuania alone: Python 7 of 8, TypeScript/JS 1 of 8. In that one post (Energia futura), it is one choice next to Python and PowerShell.
- Downloads, Python vs JavaScript versions of the same tool:

| Tool | PyPI (Python) | npm (JavaScript) |
|---|---|---|
| langchain | 170.5M | 11.6M |
| langgraph | 44.8M | 13.9M |
| OpenAI Agents SDK | 12.4M | 7.8M |
| langfuse | 23.6M | 7.2M |
| openai | 295.9M | 159.8M |
| MCP SDK | 235.2M | 240.1M |

- Vercel's `ai` package (TypeScript only) has 112.0M npm downloads. That is more than any Python agent framework except LangChain.
- SO 2026, people who build agents: Vercel AI SDK 9.0% vs Pydantic AI 8.9%. Mastra (TypeScript) 3.0% vs CrewAI (Python) 5.5%.
- Several startup postings for AI product roles are TypeScript-first:
  - GC AI: "Deep, recent TypeScript/JavaScript + React"
  - Ambito: React, TypeScript, Node
  - Tether: JS/TS agent harness
  - PrairieLearn: Node/TS
  - Typify: Angular + NestJS

**Inference:**

- Python is the default language for this field. It wins in Lithuania, in consultancies and in data-heavy roles.
- TypeScript is a real second track, mostly at product startups that want one person to own the UI, the API and the agent.
- The safest portfolio uses both: Python for the agent/eval service and TypeScript/React for the product. Your first project already has this shape. Make the Python part the core next time, not a side service.
- Download counts include CI runs and packages that other packages pull in. Use them as a rough guide, not as a head count of developers.

## 4. Business use cases companies pay for

**Measured:**

| Use case | Evidence |
|---|---|
| Customer service / support | #1 primary agent use case at 26.5% ([LangChain](https://www.langchain.com/state-of-agent-engineering)). Customer success tools: $630M ([Menlo](https://menlovc.com/perspective/2025-the-state-of-generative-ai-in-the-enterprise/)). Postings: Ignitis (agents for "digital customer and employee experience"), ML6 ("LLMs to improve customer support"), Cora AI (customer-success agents), Close (AI agent that "makes sales calls") |
| Research & data analysis | 24.4% primary use case (LangChain). Data & analytics is the #2 work use of agents at 24.9% ([SO 2025](https://survey.stackoverflow.co/2025/ai)). Postings: Interview Resources (deep research), Seeq (industrial data), VOYGR (data checking) |
| Internal knowledge search / employee assistant | Internal productivity is the #1 use case at firms with 10k+ staff, at 26.8% (LangChain). 49.7% of developers use AI to search internal knowledge ([SO 2026](https://survey.stackoverflow.co/2026/ai/data)). Postings: Ignitis ("IgnitisGPT", RAG over enterprise data), Mikron (knowledge bases), Mozilla Thunderbolt (enterprise chat/search) |
| Back-office / workflow automation | 18% primary use case (LangChain). In the EU, 31.05% of AI-using firms use it for business admin and management ([Eurostat](https://ec.europa.eu/eurostat/statistics-explained/index.php?title=Use_of_artificial_intelligence_in_enterprises)). Postings: LTK Food Group (finance, HR, marketing and ops automations, with "measure how much time or money each automation saves"), GIH (UK accounting: reconciliation, payroll, VAT), Axmed (quoting, order matching), Brace (healthcare billing), Matterhaul (ERP) |
| Document processing / extraction | Text mining is the most-used AI technology in EU firms, at 11.75% of all firms and 35.04% of large firms (Eurostat). Legal AI is a $650M market (Menlo). Postings: Klassif.ai (email and document processing, Belgium), GC AI (legal documents) |
| Marketing / sales | 34.70% of EU AI-using firms use it for marketing or sales, the top purpose (Eurostat). Sales AI startups hold 78% of their market (Menlo). Postings: Close, Ambito (CRM) |
| Coding | $4.0B, or 55% of departmental AI spend (Menlo). 83.5% of developers who use agents at work use them for software engineering (SO 2025). Mostly bought tools: Claude Code 65.5%, Copilot 58.7% (SO 2026) |
| Healthcare (vertical) | $1.5B, or 43% of vertical AI spend. AI scribes alone: $600M (Menlo) |

**Growth (measured):**

- Enterprise GenAI spend grew from $11.5B to $37B in one year (Menlo).
- Coding spend grew from $550M to $4.0B (Menlo).
- Agents in production rose from 51% to 57.3% between LangChain's two surveys.
- Lithuanian firms using AI rose from 8.76% to 21.30% in one year (Eurostat).

**Reality check (measured):** Only 16% of enterprise deployments and 27% of startup deployments are "true agents". Most are fixed workflows around a model call (Menlo). Quality is the #1 blocker for 32% (LangChain).

**Inference:** The best portfolio targets are support, internal knowledge search and back-office automation. They are common in postings, companies build them in-house (not just buy them), and they need the skills employers name: RAG, tool calling, evals and human approval steps.

## 5. Lithuania / Baltics vs global

**Measured:**

- **AI use by firms (Eurostat, firms with 10+ staff):**

| | 2024 | 2025 |
|---|---|---|
| Lithuania | 8.76% | 21.30% |
| Estonia | 13.89% | 23.40% |
| Latvia | 8.83% | 12.21% |
| EU | 13.48% | 19.95% |

  Lithuania's jump of 12.54 points was the 3rd largest in the EU ([Eurostat API](https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/isoc_eb_ai?format=JSON&geo=LT&geo=LV&geo=EE&geo=EU27_2020&indic_is=E_AI_TANY&size_emp=GE10&unit=PC_ENT&time=2024&time=2025)).
- **Main reason EU firms don't use AI:** lack of expertise (70.89%). Next come unclear legal rules (52.52%) and data protection worries (48.83%).
- **Lithuanian postings (cvbankas.lt) are mostly from large employers:**
  - Ignitis (energy)
  - EY (consulting)
  - LTK Food Group (restaurants)
  - Mikron (manufacturing)
  - Energia futura (energy)
  - Digiteka (VPN product)
- **The stack is Microsoft-heavy:** Azure OpenAI, Microsoft Foundry, Fabric, M365 and Entra appear in 6 of 8 posts. Few framework names appear. Only the EY senior role lists LangChain and LangGraph.
- **The work is mostly internal:** company GPTs, enterprise agents, MCP integrations, shared-service automation and AI rollout to staff.
- **Salaries (gross per month, as posted):**

| Role | Salary |
|---|---|
| Ignitis AI Engineer | €4,290–6,440 |
| Ignitis AI Solutions Engineer | €3,430–5,150 |
| EY AI Engineer | €2,500–3,950 |
| EY AI Engineer (Senior) | €3,900–5,850 |
| LTK Senior IT & AI Manager | from €5,000 |
| Mikron Junior Data & AI Engineer | €2,400–3,400 |

- One Ignitis role requires fluent Lithuanian. Another lists Lithuanian as a plus.
- The cvbankas search "AI engineer" returned 92 results. Most were not AI jobs. The search "LLM" returned 16.

**Global (Hacker News):** more startups, more TypeScript, more AWS, and more "evals" and "forward deployed engineer" wording. Forward deployed engineers work on-site with customers to build solutions. "Forward deployed" appears 70 times in 6 months.

**Inference:**

- For Vilnius, show Azure OpenAI (or easy cloud switching), MCP, RAG over messy company data, and plain business value ("saves X hours").
- For remote EU or global jobs, show evals, tracing and a TypeScript + Python product.
- A project with an Azure deployment option and an English UI with Lithuanian text support covers both markets.

## 6. Method & limits

**What I did:**

- **Lithuanian postings:** I read 8 AI-related posts from cvbankas.lt in full. I found them with the searches "AI engineer" and "LLM".
- **Hacker News sample:**
  - I read all 34 comments that mention "LLM" in the October 2026 "Who is hiring" thread ([thread](https://news.ycombinator.com/item?id=49922569)). 20 were roles that build AI products. I dropped roles that only mention using AI tools.
  - I read 10 comments that mention "AI engineer" in the September 2026 thread. That added 6 roles. I dropped replies and a duplicate.
  - In total: 34 postings (8 LT + 26 HN), each tallied by hand.
- **Keyword counts:** I used the HN Algolia API with typo tolerance off across 6 threads (May–Oct 2026, 2,609 comments). Counts include the rare reply comment.
  - Algolia matches the last word of a query by its start, so "LLM" also matches "LLMs".
  - "postgres" does not match "postgresql", so Postgres is undercounted.
  - "react" may also match "reactive".
- **Downloads:** npm API for 2026-09-23 to 2026-10-22. pypistats.org "last_month" as of 2026-10-25.

**Limits:**

- This is a sample, not a census. 34 hand-read postings is small. Hacker News leans toward US startups.
- I did the tally myself, so some calls are judgment calls. For example, "Next.js" counts as React, and "vector search" counts as RAG.
- The LangChain and Menlo reports come from parties with a stake. LangChain sells LangSmith. Menlo invests in Anthropic and others. The Menlo survey covers US firms only.
- Download counts are inflated by CI and by packages that other packages pull in. Example: langsmith is installed together with langchain.

**What failed or was skipped:**

- **cv.lt:** the page fetch failed.
- **cvonline.lt and cv.ee:** the keyword search returned unrelated jobs (nurses, soldiers). There were no usable AI postings on page 1.
- **LinkedIn public job search:** it showed a login wall.
- **Not tried, for time:** Wellfound, RemoteOK, We Work Remotely, aijobs.net, McKinsey State of AI, a16z and Retool reports.
- **Anthropic Economic Index:** it loaded, but it covers consumer Claude.ai chats, not company deployments. Computer & Mathematical tasks are 21.7% of chats, Sales 8.9% and Office/Admin 8.4%. It is a weak signal for this question.

## 7. Sources

**Job postings, Lithuania (cvbankas.lt):**

- EY AI Engineer: https://www.cvbankas.lt/ai-engineer-vilniuje/1-14102815
- EY AI Engineer – Senior: https://www.cvbankas.lt/ai-engineer-senior-vilniuje/1-14129552
- Ignitis AI Solutions Engineer: https://www.cvbankas.lt/ai-solutions-engineer-f-m-d-vilniuje/1-14139318
- Ignitis AI Engineer: https://www.cvbankas.lt/ai-engineer-f-m-d-vilniuje/1-14045076
- Mikron Junior Data & AI Engineer: https://www.cvbankas.lt/junior-data-ai-engineer-kaune/1-14129678
- Digiteka IT Systems & Automation Engineer (AI): https://www.cvbankas.lt/it-systems-automation-engineer-ai-focus-panevezyje/1-14130190
- Energia futura IT & AI engineer: https://www.cvbankas.lt/it-sistemu-ir-ai-sprendimu-inzinierius-e-kaune/1-14138368
- LTK Food Group Senior IT & AI Manager: https://www.cvbankas.lt/senior-it-ai-manager-vilniuje/1-14138686
- Search pages: https://www.cvbankas.lt/?keyw=AI+engineer and https://www.cvbankas.lt/?keyw=LLM

**Job postings, Hacker News** (each at `https://news.ycombinator.com/item?id=<id>`):

- October 2026 thread: https://news.ycombinator.com/item?id=49922569
- September 2026 thread: https://news.ycombinator.com/item?id=49522897

| Company | Post ID | Month |
|---|---|---|
| 3Gimbals | 50095249 | Oct |
| GovStar | 50090302 | Oct |
| Typify | 50063001 | Oct |
| General Intelligence Holdings | 50055019 | Oct |
| Close | 49967489 | Oct |
| Axmed | 49963332 | Oct |
| Elman | 49962303 | Oct |
| Pond AI | 49951635 | Oct |
| GC AI | 49943713 | Oct |
| ML6 | 49935210 | Oct |
| Seeq | 49929522 | Oct |
| Ambito | 49929368 | Oct |
| Brace Health | 49929664 | Oct |
| Mozilla Thunderbolt | 49926511 | Oct |
| applyapply | 49925300 | Oct |
| VOYGR | 49925202 | Oct |
| Tether | 49924581 | Oct |
| PrairieLearn | 49922584 | Oct |
| StartupHakk | 50059584 | Oct |
| Artificial Analysis | 49928396 | Oct |
| Catalyst·Wayfare | 49650855 | Sep |
| Matterhaul | 49613617 | Sep |
| Klassif.ai | 49540773 | Sep |
| Interview Resources | 49534032 | Sep |
| Cora AI | 49528837 | Sep |
| Deya | 49528637 | Sep |

- Keyword counts came from queries in this form: `https://hn.algolia.com/api/v1/search?tags=comment,(story_49922569,story_49522897,story_49156683,story_48747976,story_48357725,story_47975571)&query=<term>&hitsPerPage=0&typoTolerance=false`

**Surveys and reports:**

- Stack Overflow Developer Survey 2026, AI data: https://survey.stackoverflow.co/2026/ai/data
- Stack Overflow Developer Survey 2025, AI: https://survey.stackoverflow.co/2025/ai
- LangChain, State of Agent Engineering (survey Nov–Dec 2025, n=1,340): https://www.langchain.com/state-of-agent-engineering
- LangChain, State of AI Agents (2024): https://www.langchain.com/stateofaiagents
- Menlo Ventures, 2025 State of Generative AI in the Enterprise: https://menlovc.com/perspective/2025-the-state-of-generative-ai-in-the-enterprise/
- Eurostat, Use of AI in enterprises: https://ec.europa.eu/eurostat/statistics-explained/index.php?title=Use_of_artificial_intelligence_in_enterprises
- Eurostat API, Baltic numbers: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/isoc_eb_ai?format=JSON&geo=LT&geo=LV&geo=EE&geo=EU27_2020&indic_is=E_AI_TANY&size_emp=GE10&unit=PC_ENT&time=2024&time=2025
- Anthropic Economic Index: https://www.anthropic.com/economic-index

**Download stats:**

- npm, format `https://api.npmjs.org/downloads/point/last-month/<pkg>`: `ai`, `@langchain/langgraph`, `langchain`, `@mastra/core`, `@modelcontextprotocol/sdk`, `@openai/agents`, `langfuse`, `llamaindex`, `promptfoo`, `openai`
- PyPI, format `https://pypistats.org/api/packages/<pkg>/recent`: `langgraph`, `langchain`, `llama-index`, `llama-index-core`, `crewai`, `openai-agents`, `pydantic-ai`, `langfuse`, `langsmith`, `fastapi`, `mcp`, `ragas`, `deepeval`, `arize-phoenix`, `braintrust`, `openai`
