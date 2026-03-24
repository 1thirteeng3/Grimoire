# Incident Runbook: Degradação de RAG

## Sinais

- Alerta: `GrimoireRAGAverageLatencyHigh`
- Latência média RAG acima de baseline e/ou threshold absoluto
- Respostas com contexto pobre ou fallback frequente

## Diagnóstico rápido

1. Verificar:
   - `grimoire:sli:rag_avg_latency_ms:5m`
   - `grimoire_stage_operations_total{stage="RAG"}`
2. Confirmar disponibilidade de:
   - Qdrant
   - modelo de embeddings
   - modelo de rerank
3. Revisar logs de fallback lexical e erros de retrieval/scoring.

## Mitigação imediata (P2)

1. Reduzir top-k e/ou desabilitar rerank pesado temporariamente.
2. Priorizar fallback lexical para manter disponibilidade funcional.
3. Se regressão de release for confirmada:
   - `make rollback-deploy ENV=production STRATEGY=auto`

## Critério de estabilização

- Latência RAG abaixo do threshold efetivo por >=30 minutos.
- Queda de erros `RAG_PIPELINE_ERROR` e redução de fallback não planejado.

## Pós-incidente

- Revisar perfil de carga do índice e capacidade de I/O.
- Ajustar baseline e limiares após novo padrão de tráfego.
