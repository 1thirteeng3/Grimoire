# Incident Runbook: Prompt Bloat Recorrente

## Sinais

- Alerta: `GrimoirePromptBloatRecurring`
- Eventos WS: `PROMPT_BLOATING`
- Queda de throughput no pipeline RAG/LLM

## Diagnóstico rápido

1. Inspecionar métricas:
   - `grimoire_errors_total{stage="RAG",error_type="PROMPT_BLOAT"}`
   - `grimoire:sli:prompt_bloat_events_15m`
2. Validar domínio/consulta que dispara crescimento de contexto.
3. Conferir chunks recuperados e tamanho da constituição gerada.

## Mitigação imediata (P2)

1. Reduzir `retrieval_top_k` temporariamente.
2. Aplicar filtro de domínio/escopo para evitar contexto excessivo.
3. Se necessário, reduzir `GRIMOIRE_MAX_CONSTITUTION_TOKENS` de forma controlada.
4. Em release recém-promovido, considerar rollback:
   - `make rollback-deploy ENV=production STRATEGY=auto`

## Critério de estabilização

- Eventos de prompt bloat abaixo do baseline + margem por >=30 minutos.
- Fluxo `INTENT_SUBMIT` volta ao caminho happy-path sem interrupção frequente.

## Pós-incidente

- Revisar estratégia de chunking/rerank para o domínio afetado.
- Atualizar política de top-k e filtros por tipo de consulta.
