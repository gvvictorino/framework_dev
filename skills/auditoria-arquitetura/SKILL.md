---
description: "Audita se os mecanismos da arquitetura de agentes (gatilhos, campos de estado, circuit breaker, specs versionadas) estão de fato funcionando no projeto atual, e propõe uma rodada de melhoria nos agentes com base em evidência real do repositório."
---

# Auditoria de Arquitetura — Checklist e Documentação Viva

Este arquivo é dois coisas ao mesmo tempo: a documentação de referência de como esta
arquitetura de agentes deveria funcionar, e o roteiro que você segue quando é invocado (via
`/auditoria-arquitetura`) para checar se está funcionando de verdade.

## Visão geral do sistema (referência)

- **8 agentes especialistas** em `.claude/agents/` (ou `~/.claude/agents/`): planner, design,
  data-pipeline, llm-qualification, implementador, revisor-qualidade, documentador,
  orquestrador-llm. Cada um só invocado pela sessão principal via `Task`, nunca por outro
  subagente (subagentes não podem aninhar).
- **Sessão principal** age como orquestrador conversacional, seguindo `CLAUDE.md` do projeto.
- **O script de decisão (`decide.py`)** é a única fonte de decisão de roteamento — determinístico, sem
  julgamento de LLM, exceto para os 4 gatilhos fechados que escalam para `orquestrador-llm`.
- **4 gatilhos**: `spec_ausente`, `spec_conflict`, `gap_sem_tarefa`, `tarefa_travada_N_ciclos`.
- **Circuit breaker**: profundidade de cadeia de reaberturas (`supersedes`) ≥ 3 força
  `escalated_human`, sem depender de julgamento.
- **Campos de estado obrigatórios**: `origem_gap` (tarefa ↔ gap-report), `implementado`
  (marca fim da implementação para o Revisor assumir), `requer_qualificacao`, `versao` (em
  toda spec), `schema_referencia` (qualification → data-pipeline).

- **Skill `sincronizar-notion`** (opcional): espelha o backlog no Notion, via de mão única
  (arquivo → Notion). Nunca é fonte de decisão para `decide.py` nem para nenhum agente.

## Quando invocado — passo a passo da auditoria

Execute cada checagem abaixo contra o estado REAL do repositório (leia os arquivos, não
assuma). Para cada item, classifique: ✅ funcionando / ⚠️ parcial / ❌ não funciona / ➖ ainda
não aplicável (projeto muito novo para o mecanismo ter sido exercitado).

### 1. Roteamento determinístico
- Confira o `CLAUDE.md` do projeto para saber o comando exato de decisão configurado (varia
  entre modo `--shared`, apontando para `~/.claude-agent-framework/decide.py`, e modo `--local`,
  com uma cópia de `decide.py` dentro do próprio projeto). Rode esse comando para 2-3 tarefas
  reais do backlog atual e confirme que o agente retornado bate com o que você esperaria
  manualmente pela lógica documentada.
- Verifique se `tech-stack.md` tem `lint_command`/`test_command` como comandos literais
  executáveis, nunca texto vago.

### 2. Os 4 gatilhos já dispararam pelo menos uma vez?
- Leia `docs/decisions/orchestrator/index.md`. Para cada gatilho presente no histórico,
  confirme que a entrada tem `arquivos_envolvidos` no mesmo formato exato que
  `decide.py` gera (sem sufixo de versão, sem reformatação) — isso é o erro mais provável de
  aparecer silenciosamente.
- Se ALGUM gatilho nunca disparou e o projeto já tem histórico razoável (10+ tarefas
  concluídas), investigue se a condição está bem calibrada ou se está morta no código.

### 3. Circuit breaker
- Procure cadeias de `supersedes` no índice. Se alguma cadeia chegou a profundidade 3 sem
  forçar `escalated_human`, é bug — reporte com prioridade alta.
- Se nenhuma cadeia jamais passou de 1, isso é ➖ não aplicável ainda, não uma falha.

### 4. Campos de estado
- `origem_gap`: para cada gap-report com `status: divergente`, existe uma tarefa em
  backlog/in-progress referenciando-o? Se não, o gatilho `gap_sem_tarefa` deveria ter
  disparado — confirme se disparou e ficou sem resolução, ou se o agente que deveria
  preencher o campo (orquestrador-llm) esqueceu.
- `implementado`: tarefas em `in-progress.md` que já têm código pronto (confirme lendo o
  diff/commit) têm o campo marcado? Se não, o Revisor nunca vai ser acionado para elas.

### 5. Isolamento de contexto do Implementador
- Pegue uma tarefa concluída recentemente. Verifique, pelo histórico de ferramentas usadas
  (se disponível) ou pelo resultado, se o Implementador tocou apenas arquivos dentro do
  `path` do componente da tarefa — nenhum arquivo fora dele.

### 6. Sincronização multi-projeto/multi-máquina
- Confirme que `~/.claude/agents/` (nível usuário) contém a versão mais atual dos 8 agentes, e
  que nenhum projeto tem uma cópia desatualizada em `.claude/agents/` local conflitando por
  nome sem motivo — isso indica drift não intencional.
- Confirme que não existe `CLAUDE.md` divergente do template gerado por `bootstrap-project.sh`
  — um `CLAUDE.md` editado manualmente sem atualizar o template correspondente é a mesma classe
  de drift, só que entre um projeto e o gerador, não entre duas máquinas.

### 7. Consistência estática entre `tools:` declarado e o que o prompt realmente faz
- Para cada agente em `.claude/agents/`, leia o corpo do prompt e liste toda operação de
  arquivo que ele descreve fazer ("você escreve X", "crie Y", "rode Z via Bash"). Confirme que
  cada operação tem a ferramenta correspondente (`Write`, `Edit`, `Bash`) na lista `tools:` do
  frontmatter. Um agente que descreve escrever um arquivo sem ter `Write` nas tools é um bug
  silencioso — só aparece na primeira vez que o agente tenta agir, não na leitura do prompt.

### 8. Transição de estado backlog → in-progress → done
- Confirme que algum agente (hoje, o Implementador) move fisicamente a entrada da tarefa entre
  os três arquivos em cada etapa do ciclo — não basta marcar campos como `implementado: true`
  se a tarefa nunca sai de `backlog.md` para começar. Rastreie uma tarefa concluída recentemente
  pelos três arquivos e confirme que ela de fato passou pelos três estados, nessa ordem.

### 9. Referências cruzadas entre arquivos
- Grep por nomes de agentes/arquivos que não existem mais (ex: um agente removido, um script
  renomeado) em todos os prompts e no `decide.py` — referência obsoleta a algo removido numa
  correção anterior é o tipo de erro que só aparece em busca textual, nunca em leitura isolada
  de um arquivo por vez.

### 10. Agentes com `Write` mas sem `Edit`, escrevendo em arquivo compartilhado ou acumulativo
- Para cada agente com `tools:` incluindo `Write`, confirme se algum arquivo que ele escreve é
  compartilhado entre execuções (backlog.md, prompt-tests.md, index.md, architecture.md) ou se
  é sempre um arquivo novo e isolado por execução (gap-report por id de tarefa, por exemplo).
  Para os compartilhados, confirme que o agente tem `Edit` nas tools E instrução explícita de
  ler antes de escrever, acrescentando em vez de recriar. Um agente com só `Write` operando
  sobre arquivo compartilhado é risco de perda de dados silenciosa — só aparece quando alguém
  roda o agente pela segunda vez com conteúdo já existente no arquivo, o que pode não acontecer
  nos primeiros testes.

### 11. `decide.py` é realmente livre de efeito colateral?
- A docstring do módulo afirma que `decide.py` só lê e nunca grava. Confirme isso na prática:
  grep por `write_text`, `safe_dump` ou qualquer chamada de escrita dentro do arquivo. Se
  existir alguma, o contrato declarado está sendo violado — rodar o script para diagnóstico
  (como esta própria auditoria faz) estaria alterando o estado que deveria só observar.

### 12. Sincronização com Notion (se configurada)
- Se `docs/notion-database-id.md` existir, confirme que nenhum agente ou skill lê o Notion para
  decidir estado — grep por chamadas de leitura ao Notion fora do skill `sincronizar-notion`, e
  mesmo dentro dele, confirme que é só para localizar a página a atualizar, nunca para inferir
  status. Notion virar fonte de verdade por acidente é exatamente o tipo de drift que este
  checklist existe para pegar — a via tem que continuar sendo só arquivo → Notion.

### 13. Disciplina de versionamento
- Toda vez que esta auditoria (ou qualquer mudança manual) alterar `agents/*.md`, `skills/`,
  `decide.py`, `setup-machine.sh`, `bootstrap-project.sh` ou `templates/`, confirme que
  `VERSION` foi incrementado e `CHANGELOG.md` ganhou uma entrada correspondente, no mesmo
  commit. Sem isso, `atualizar.sh` continua funcionando (git não depende de VERSION para
  detectar mudança), mas o relatório de changelog que ele mostra ao usuário fica vazio ou
  desatualizado — a atualização acontece, só que silenciosa sobre o que mudou.

### 14. Robustez do contrato de saída de `decide.py`
- A docstring do módulo promete que o stdout é **sempre** um dos formatos JSON declarados.
  Confirme que isso vale também no erro: monte um projeto descartável com `backlog.md`,
  `in-progress.md` ou o índice de decisões malformado (YAML inválido, lista de itens que não
  são mapeamentos, `arquivos_envolvidos` que não é lista) e rode o script. Traceback com stdout
  vazio é violação de contrato: a sessão principal segue o template, "para e reporta", e fica
  sem motivo utilizável. Quem escreve esses arquivos são agentes de LLM, então malformação é
  cenário de operação normal, não corrupção exótica. Confirme também que entrada torta no
  índice **escala** em vez de ser ignorada — ignorar faz o circuit breaker falhar ABERTO, que é
  o modo de falha que ele existe para evitar.

### 15. Seleção de tarefa é determinística
- O template dispara o ciclo com "roda o próximo". Confirme que existe regra explícita de qual
  é a próxima e que ela mora em `decide.py`, não no julgamento da sessão — rode o script sem
  argumento num projeto com tarefas em mais de um arquivo de estado e verifique a ordem contra
  `proxima_tarefa()`. Confirme também que a seleção **termina**: toda tarefa escolhida precisa
  ter um estado que a tire da fila depois de processada (`implementado`, `documentado`). Fila
  que devolve para sempre a mesma tarefa é a mesma classe de bug do agente inalcançável, só que
  na direção oposta. A lacuna não aparece com backlog de uma tarefa.

### Nota sobre a numeração

Até a v1.0.7 este checklist pulava do item 9 para o 11 — não havia item 10. A numeração foi
fechada na v1.1.0, então **relatórios de auditoria datados de antes disso citam os números
antigos**: o que eles chamam de item 11 (`Write` sem `Edit`) é o item 10 aqui, e assim por
diante até o 14, que virou 13. Não reescreva relatório antigo para casar com esta numeração —
eles são registro do que foi auditado na época.

## Saída da auditoria

Escreva um relatório em `/docs/decisions/auditoria/<data>.md`:

```markdown
# Auditoria — <data>

## Resumo
<1-2 frases sobre o estado geral>

## Checklist
| Mecanismo | Status | Evidência |
|---|---|---|
| ... | ✅/⚠️/❌/➖ | arquivo/linha que sustenta a classificação |

## Propostas de melhoria
<lista concreta, cada item apontando qual arquivo de agente mudaria e por quê>
```

## Regra rígida — não pule esta parte

Você NUNCA edita `~/.claude/agents/*.md`, `CLAUDE.md` ou `decide.py` diretamente como parte
desta auditoria. Toda melhoria proposta fica registrada no relatório, como sugestão concreta,
para o usuário revisar e aplicar (ou pedir que você aplique, num pedido explícito e separado).
Agentes que reescrevem suas próprias regras de funcionamento sem revisão humana são exatamente
o tipo de risco que esta arquitetura foi desenhada para evitar em todo o resto do sistema — a
auditoria não é uma exceção a essa regra, é a peça que mais precisa dela.

Se o usuário pedir explicitamente para você aplicar uma ou mais propostas: edite dentro do
repositório do framework (`~/.claude-agent-framework/`, se for um clone git — ver item 14),
incremente `VERSION` e acrescente a entrada em `CHANGELOG.md` no mesmo pedido, e informe que o
usuário ainda precisa rodar `git add`, `git commit` e, se quiser propagar para outras máquinas,
`git push` — você não tem acesso a essas ações fora do sistema de arquivos.
