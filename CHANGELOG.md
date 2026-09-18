# Changelog

Todas as mudanças notáveis nos agentes, skills e scripts deste framework ficam registradas
aqui. Formato baseado em [Keep a Changelog](https://keepachangelog.com/), versionamento
[semver](https://semver.org/): MAJOR.MINOR.PATCH — MAJOR para mudança que quebra projetos já
em andamento (ex: campo renomeado, contrato de `decide.py` alterado), MINOR para agente/skill
novo ou capacidade nova sem quebrar nada existente, PATCH para correção de bug.

Ao aplicar uma proposta de melhoria vinda da skill `/auditoria-arquitetura` (ou qualquer outra
mudança manual), quem aplica é responsável por: incrementar `VERSION` e acrescentar uma entrada
aqui, no mesmo commit. Sem isso, `atualizar.sh` não tem o que reportar ao rodar em outra
máquina.

## [1.0.2] — 2026-09-18

Restauração da v1.0.1 e correção do bit de execução dos scripts. O commit `78b97c7`
("Add files via upload") substituiu o histórico do repositório e reverteu a `main` para o
conteúdo da 1.0.0: `decide.py` voltou ao estado com os dois bugs de roteamento, e
`tests/test_decide.py`, o relatório de auditoria e a entrada `[1.0.1]` deste changelog
sumiram. A tag `v1.0.1` continuou existindo no remoto, mas apontando para uma linhagem órfã,
inalcançável a partir de qualquer branch — quem clonasse o repositório recebia 1.0.0.
Regressão medida rodando a suíte contra os dois `decide.py`: 16/16 na v1.0.1, 11/16 na `main`.

- Conteúdo da 1.0.1 reintroduzido numa linhagem alcançável a partir da `main`, com a suíte de
  regressão de volta em `tests/test_decide.py`.
- Bit de execução restaurado em `setup-machine.sh`, `bootstrap-project.sh` e `atualizar.sh`
  (`100644` → `100755`). O upload zerou a permissão nos três, o que quebrava as duas formas
  documentadas de uso: o README instrui a rodar `~/.claude-agent-framework/setup-machine.sh`
  diretamente, e `atualizar.sh` invoca `"$SCRIPT_DIR/setup-machine.sh" --force` na etapa de
  propagação — ambos falhavam com `Permission denied`.

Quem instalou a partir da `main` depois do upload está com 1.0.0 e precisa atualizar: os dois
bugs de roteamento de `decide.py` descritos na 1.0.1 estavam ativos nessa cópia.

## [1.0.1] — 2026-09-18

Correção de dois bugs de roteamento em `decide.py`. Ambos reproduzidos em projeto sintético
antes da correção; suíte de regressão adicionada em `tests/test_decide.py` (16 casos).

- `gatilho_spec_ausente` disparava para QUALQUER spec referenciada e inexistente. Como os
  gatilhos são avaliados antes de `mapear_tarefa_para_agente()`, ele interceptava o estado
  normal de uma tarefa recém-criada — o Planner lista `docs/specs/design/<componente>.md` em
  `specs_referenciadas` justamente porque a spec ainda não existe. Consequências: todo o
  despacho para especialista era código inalcançável (os agentes `planner`, `design`,
  `data-pipeline` e `llm-qualification` só entravam por decisão de LLM); cada componente novo
  custava uma chamada de orquestrador e uma entrada no índice de decisões para reproduzir uma
  decisão já escrita em código. Agora o gatilho só dispara para spec sem agente dono
  (referência órfã) e o despacho determinístico volta a ser alcançável.
- `profundidade_cadeia` nunca lia `supersedes`, apesar da docstring e do prompt do
  `orquestrador-llm` exigirem o campo: contava a cardinalidade das entradas relacionadas. Três
  decisões INDEPENDENTES sobre os mesmos arquivos escalavam um projeto saudável para
  intervenção humana. Agora mede o comprimento da maior cadeia real de `supersedes`, com
  proteção contra índice cíclico.
- `orquestrador-llm`: a ação para `spec_ausente` foi reescrita para refletir a nova semântica
  do gatilho (referência órfã, não spec pendente).

Projetos em andamento não precisam de migração: o contrato de saída de `decide.py` (as três
formas de JSON) não mudou, e entradas de decisão já gravadas continuam válidas — as antigas
sem `supersedes` passam a contar como cadeias independentes, que é o comportamento correto.

## [1.0.0] — 2026-09-18

Primeira versão com controle de versão formal. Consolida todas as correções da auditoria de
18/09/2026:

- Planner e llm-qualification ganharam `Edit` nas tools e regra explícita de preservar
  entradas existentes em arquivo compartilhado (`backlog.md`, `prompt-tests.md`) — corrige
  risco de perda de dados por `Write` cego.
- `decide.py`: `gatilho_tarefa_travada` deixou de gravar estado a cada chamada — agora é
  leitura pura, conforme a docstring do módulo já prometia. O incremento de
  `ciclos_sem_progresso` passou para o Implementador.
- `CLAUDE.md.template`: referência a `.claude/agents/` corrigida para deixar explícito que é
  nível de usuário (`~/.claude/agents/`), com instrução de rodar `setup-machine.sh` se ausente.
- Estrutura do pacote simplificada: eliminada a duplicação entre `.claude/agents/` e
  `deploy/framework/agents/` — agora existe uma única árvore versionada.
