# Pipeline diário no GCP (pausado)

## Status

**Pausado em 2026-10-19** por Jair Pontes Pisani.

**Motivo:** nova importação.

## O que foi parado

| Item | Valor |
|---|---|
| Projeto GCP | `falai-painelista-data` |
| Região | `southamerica-east1` |
| Job do Cloud Run | `falai-pipeline` |
| Gatilho (Cloud Scheduler) | `falai-pipeline-diario`, `0 6 * * *` (todo dia às 06:00 UTC) |

Só o gatilho foi pausado. O job do Cloud Run continua lá, sem nenhuma alteração, e ainda pode ser executado manualmente.
A última execução automática foi `falai-pipeline-b4ws5`, em 2026-10-19 às 06:00 UTC, e terminou sem erro.

## Como voltar a rodar

Reativar o gatilho diário:

```bash
gcloud scheduler jobs resume falai-pipeline-diario \
  --project=falai-painelista-data --location=southamerica-east1
```

Conferir que voltou (deve mostrar `ENABLED`):

```bash
gcloud scheduler jobs describe falai-pipeline-diario \
  --project=falai-painelista-data --location=southamerica-east1 --format="value(state)"
```

Rodar uma vez agora, sem esperar o horário:

```bash
gcloud run jobs execute falai-pipeline \
  --project=falai-painelista-data --region=southamerica-east1
```
