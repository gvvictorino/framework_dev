---
description: "Sincroniza o estado atual de tasks/backlog.md, in-progress.md e done.md para um database do Notion, como visualização apenas. Via de mão única: nunca lê o Notion como fonte de estado."
---

# Sincronização com Notion — Visualização apenas

## Regra fundamental — isto é uma via de mão única

Os arquivos em `/tasks/` são e continuam sendo a ÚNICA fonte de verdade. Este skill só EMPURRA
estado dos arquivos para o Notion — nunca lê o Notion para decidir nada, nunca traz de volta
uma edição feita lá para os arquivos. Se o usuário editar algo diretamente no Notion (mudar um
status, escrever uma nota), essa edição fica só no Notion até a próxima sincronização
sobrescrever — isso é intencional, não um bug. Se em algum momento este skill (ou qualquer
outro) começar a ler o Notion para tomar decisão de roteamento, isso viola a razão pela qual a
opção "Notion como armazenamento real" foi descartada — não faça isso.

O script de decisão nunca chama o Notion, direta ou indiretamente. Isso continua valendo
depois deste skill existir.

## Pré-requisito

Um conector MCP do Notion precisa estar disponível nesta sessão. Se não estiver, informe o
usuário e pare — não prossiga tentando simular a sincronização de outra forma (não crie
arquivos locais fingindo ser Notion, não peça para o usuário colar dados manualmente).

Na primeira execução num projeto novo, se `docs/notion-database-id.md` não existir, você
precisa de um database no Notion já criado pelo usuário (ou criado por você, se o conector
permitir) com estas propriedades:

| Propriedade | Tipo Notion | Origem no arquivo de tarefa |
|---|---|---|
| Nome | title | `"{id} · {componente} · {tipo}"` (ex: "T-014 · frontend-site · ui") |
| Status | select (Backlog / Em andamento / Concluído) | qual arquivo contém a tarefa |
| Componente | select | `componente` |
| Tipo | select | `tipo` |
| Implementado | checkbox | `implementado` |
| Requer Qualificação | checkbox | `requer_qualificacao` |
| Specs referenciadas | text | `specs_referenciadas` (uma linha por item) |
| Origem do gap | text | `origem_gap` (vazio se ausente) |
| Última sincronização | date | data/hora desta execução |

Depois de identificar ou criar o database, grave o ID em `docs/notion-database-id.md` (arquivo
de uma linha só, sem frontmatter) para não precisar perguntar de novo nas próximas execuções.

## Execução

1. Leia `tasks/backlog.md`, `tasks/in-progress.md`, `tasks/done.md`. Status de cada tarefa é
   determinado pelo arquivo em que ela está — não existe campo `status` separado para isso.
2. Para cada tarefa, busque no database do Notion uma página cujo título comece com o `id` da
   tarefa (ex: busca por `"T-014"`).
   - Se existe: atualize as propriedades para refletir o estado atual do arquivo.
   - Se não existe: crie uma página nova com todas as propriedades da tabela acima.
3. NUNCA delete páginas do Notion, mesmo que a tarefa correspondente não exista mais nos
   arquivos — o usuário pode ter feito anotações manuais nela. Se detectar uma página órfã
   (nenhuma tarefa correspondente nos três arquivos), reporte isso no resumo final, não aja
   sozinho.
4. Ao final, informe um resumo curto e objetivo: quantas páginas foram criadas, quantas
   atualizadas, quantas órfãs detectadas (se houver). Não narre o processo passo a passo.

## Regras rígidas

- Isto é sempre uma ação explícita, disparada pelo usuário (`/sincronizar-notion` ou pedido em
  linguagem natural equivalente) — nunca automática a cada ciclo do Orquestrador.
- Se a chamada ao Notion falhar no meio da sincronização (rate limit, erro de rede), pare e
  reporte quantas tarefas já foram sincronizadas antes da falha — não tente adivinhar o estado
  parcial nem repetir do zero sem avisar.
- Nunca grave nos arquivos de `/tasks/` como resultado de rodar este skill — a única direção de
  escrita é arquivo → Notion.
