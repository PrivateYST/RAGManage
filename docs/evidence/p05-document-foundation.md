# Document processing foundation

Date: 2026-09-17. This is partial P03/P05 progress, not G0 or business acceptance.

Implemented:

- Markdown/TXT parsing with original line ranges and SHA-256 source identity.
- DOCX paragraphs and PDF pages, with explicit warnings for omitted DOCX tables/images,
  PDF tables and pages with little text. These formats still require representative samples.
- File size, DOCX expanded-size and PDF page limits. UTF-8 text only in this iteration.
- Ollama embedding adapter: no silent truncation; validates count, dimensions, finite values
  and nonzero norms before cosine normalization.
- A local diagnostic CLI performs exact cosine recall over parsed blocks. It does not
  publish documents, persist indexes, generate answers, or implement tenant authorization.
- Removed temporary simulated login, ingestion progress and citation endpoints.
- Activated Antfu ESLint scripts; config 7.7.3 matches the existing TypeScript 5.9 toolchain.

Run from `backend`:

```powershell
../.tools/uv-bootstrap/bin/uv.exe run --frozen python -m app.rag.inspect ../frontend/docs/knowledgeBase
../.tools/uv-bootstrap/bin/uv.exe run --frozen python -m app.rag.inspect ../frontend/docs/knowledgeBase --query "可以提前几天预约？每天什么时候放号？"
```

The query option sends source blocks to the configured company Ollama service. Without it,
inspection is local and read-only. No automatic external service fallback is configured.

Observed recall smoke test: the first result was FAQ line 13, covering both seven-day advance
booking and the 07:00 release time. The booking-rules line 7 also appeared in the top ten.
This is one question, not a recall-rate benchmark. The nine source files describe themselves
as internal test material and must not be represented as production-approved business data.

Remaining gates: exact tokenizer/profile validation, bounded token chunking, model provenance,
held-out evaluation, resource capacity, database migrations, real sessions and authorization,
durable jobs, publication, generation and the business frontend. Parsers currently run in the
local diagnostic process; untrusted production uploads require worker resource isolation.

Verification: `./infra/scripts/check.ps1` passed on 2026-09-17: Ruff checks/format,
strict mypy, 19 backend tests, frozen dependency installation, ESLint, Vue typecheck,
3 frontend tests and Vite production build. `pnpm peers check` reported no issues.
Two pre-existing Starlette test-client deprecation warnings remain.
