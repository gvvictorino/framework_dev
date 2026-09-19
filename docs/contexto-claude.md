# Contexto de trabalho — para quem abrir este repositório noutra estação

Última revisão: **2026-09-19** (framework na v1.0.6).

Este arquivo existe porque o `CHANGELOG.md` responde *o que mudou* e o `README.md` responde
*como usar*, mas nenhum dos dois responde *o que você precisa saber antes de mexer aqui*.
Ele registra só isso: o que não é dedutível lendo o repositório. Se uma informação já está no
changelog ou no README, o lugar dela é lá — não a duplique aqui, ou este arquivo apodrece.

O princípio é o mesmo que motiva o framework inteiro: nada que importa pode viver só no
histórico de uma conversa. Um agente novo, numa máquina nova, precisa reconstruir o contexto
lendo arquivos versionados.

---

## 1. Primeiro comando ao clonar: valide a cópia

```bash
python tests/test_decide.py
```

Esperado: **16/16 passaram**. A suíte é stdlib pura e roda como script — não use `pytest`, ele
não é dependência do projeto. Cada caso monta um projeto descartável em diretório temporário e
chama `decide.py` como subprocesso, o que cobre também o ponto de entrada e o formato de saída.

Se você vir `escalar_humano` em massa, não investigue o roteamento: é `pyyaml` faltando
(ver seção 2). Foi assim que a dependência passou despercebida por três versões — a falha se
disfarça de projeto mal configurado.

Se vier menos que 16/16 com o `pyyaml` instalado, **pare**. Os casos 1, 2, 6, 7 e 9 travam os
dois bugs de roteamento corrigidos na v1.0.1; uma falha neles significa regressão real, não
teste frágil. Não remova nenhum caso sem entender que bug ele protege.

## 2. O que o git não traz junto

O clone não basta. O que cada estação precisa ter antes de trabalhar:

**`pyyaml` e Python ≥ 3.10** — declarados no README desde a v1.0.4. O piso de 3.10 não é
arbitrário: `decide.py` anota assinaturas com `X | None` sem `from __future__ import
annotations`, então o interpretador avalia a anotação na definição e a 3.9 falha ao carregar o
módulo.

**Ambiente Linux — em estação Windows, WSL.** Desde a v1.0.6 esse é o padrão declarado, não
uma preferência. Clone e trabalhe dentro do sistema de arquivos do Linux (`~/...`), não em
`/mnt/c`. O bit `755` dos três `.sh` é obrigatório: o README manda rodar `setup-machine.sh`
diretamente e `atualizar.sh` o invoca com `--force`; sem o bit, os dois falham com
`Permission denied`. Ele foi zerado uma vez (ver seção 4) e restaurado na v1.0.2.

Fins de linha são garantidos pelo `.gitattributes` desde a v1.0.6 — um CRLF no shebang faz o
bash falhar com `bad interpreter: ^M`, erro que não diz o que de fato aconteceu. Não
sobrescreva essas regras com configuração local.

**Se por algum motivo você estiver em Windows nativo** (Git Bash, PowerShell — fora do padrão):
rode `git config core.filemode false`, senão os três `.sh` aparecem permanentemente como
modificados (`100755` → `100644`), porque o sistema de arquivos não representa o bit de
execução. É diff fantasma — não commite essa "mudança". Saiba também que os caminhos gravados
em `arquivos_envolvidos` saem com barra invertida, o que impede o circuit breaker de casar
decisões gravadas noutra plataforma (ver P9 em `docs/decisions/auditoria/2026-09-19.md`). É a
razão técnica por trás da padronização.

## 3. Push para o GitHub exige endereço noreply

O repositório remoto recusa commits que exponham o e-mail pessoal:

```
remote: error: GH007: Your push would publish a private email address.
```

A conta tem *Block command line pushes that expose my email* ativo. Configure a identidade
com o endereço noreply antes de commitar:

```bash
git config user.email "51134031+gvvictorino@users.noreply.github.com"
```

Isso não é preferência de estilo: um commit criado com o e-mail pessoal **não sobe**, e
descobrir isso depois obriga a reescrever histórico — que é precisamente como o repositório se
meteu no problema descrito na seção 4.

## 4. Por que o histórico tem duas linhagens

Vale entender antes de olhar `git log` e se assustar.

Em 2026-09-18 um commit `78b97c7` ("Add files via upload"), feito pela interface web do GitHub,
**substituiu** o histórico da `main`. O efeito foi silencioso e sério: o conteúdo voltou para o
da 1.0.0, `decide.py` regrediu para o estado com os dois bugs de roteamento, e
`tests/test_decide.py`, o relatório de auditoria e a entrada `[1.0.1]` do changelog sumiram. A
tag `v1.0.1` continuou existindo, mas apontando para uma linhagem órfã, inalcançável a partir
de qualquer branch — quem clonasse recebia 1.0.0 achando que tinha 1.0.1.

A v1.0.2 (PR #2) reintroduziu o conteúdo numa linhagem alcançável e restaurou os bits de
execução. A v1.0.3 (PR #4) aplicou três correções da auditoria do projeto `analistajuridico`.
A linhagem publicada hoje é a que descende de `78b97c7`, e é a única válida.

Duas lições que o repositório pagou caro para aprender, e que valem como regra:

- **Não use upload pela interface web neste repositório.** Ele não faz merge: substitui, zera
  permissão de arquivo e pode orfanar tags sem avisar.
- **Tag órfã é pior que tag ausente**, porque mente. Depois de mexer em histórico, confira que
  cada tag é alcançável a partir da `main`.

Pode existir um branch local `backup/linhagem-local-v1.0.1` numa estação ou outra, preservando
a linhagem órfã. Ele é **local, nunca foi publicado e não tem base comum com a `main`** — não
tente mesclá-lo. É só rede de segurança histórica e pode ser apagado sem perda.

## 5. Convenções que não são negociáveis

**Toda mudança em `agents/`, `skills/`, `decide.py`, `setup-machine.sh`, `bootstrap-project.sh`
ou `templates/` sobe com `VERSION` incrementado e entrada no `CHANGELOG.md`, no mesmo commit.**
Não é burocracia: `atualizar.sh` lê exatamente esses dois arquivos para reportar o que mudou
quando roda noutra máquina. Sem eles, a atualização acontece muda. A convenção vale também
para "qualquer outra mudança manual" — a v1.0.4, que só tocou o README, seguiu a regra.

**`decide.py` é puro e determinístico.** Ele lê estado e devolve JSON; não escreve nada. O
incremento de `ciclos_sem_progresso` pertence ao Implementador — se você sentir vontade de dar
efeito colateral ao `decide.py` para resolver algo, o lugar certo é quase sempre um agente.

**Agentes que escrevem em arquivo compartilhado precisam de `Edit`, não só de `Write`**, mais a
instrução explícita de ler antes de acrescentar. Vale para `planner` e `llm-qualification`
(`backlog.md`, `prompt-tests.md`) e para `documentador` (`docs/architecture.md`). A perda nunca
aparece na primeira execução, com o arquivo vazio — aparece na segunda, e por isso escapa de
teste manual.

## 6. Decisões de arquitetura que os arquivos não revelam sozinhos

- **A sessão principal (via `CLAUDE.md`) é o orquestrador conversacional, não um subagente.**
  Isso é imposto pela plataforma: subagentes do Claude Code não conseguem invocar outros
  subagentes, porque a ferramenta `Task` é removida do conjunto deles. Só a sessão principal
  tem esse acesso. Não tente transformar a orquestração num subagente — não funciona.
- **`orquestrador-llm` tem escopo fechado**: resolve apenas o que os gatilhos sinalizaram,
  nunca avalia o estado geral do projeto. Grava a decisão em dois lugares — o arquivo detalhado
  (append-only) e `docs/decisions/orchestrator/index.md`. É o índice que `decide.py` lê para
  calcular profundidade de cadeia de `supersedes`; manter os dois em dia não é redundância.
- **Instalação compartilhada por padrão.** Agentes e skills vivem em `~/.claude/agents/` e
  `~/.claude/skills/`, fora do versionamento de cada projeto, para evitar drift entre projetos.
  `decide.py` fica em `~/.claude-agent-framework/` e é referenciado por caminho absoluto no
  `CLAUDE.md` gerado. O caminho é fixo de propósito: a arquitetura depende de uma cópia única
  em local canônico. Desde a v1.0.3 o `bootstrap-project.sh` **valida** esse caminho em vez de
  presumi-lo.
- **O `CLAUDE.md` de projeto é gerado por merge, não por sobrescrita.** Se o projeto já tem um,
  o bloco da arquitetura vai para o fim, delimitado por
  `<!-- BEGIN/END arquitetura-agentes-ia -->`, para não duplicar em reexecuções.
- **Notion é via de mão única.** Espelho de leitura, nunca fonte de decisão. `decide.py` não lê
  o Notion e não deve passar a ler.

## 7. Pendências conhecidas e deliberadas

Nenhuma destas é esquecimento; não "corrija" sem conversar.

- **`setup-machine.sh` não instala `pyyaml`.** Decisão consciente: a forma de instalar (`pip`,
  `pipx`, gerenciador da distribuição, virtualenv) é de quem instala. O README declara a
  dependência desde a v1.0.4; o script continua sem tocar no ambiente Python da máquina.
- **O bloco *Estrutura* do README não lista `tests/` nem `docs/`**, que entraram na v1.0.1.
  Inexatidão conhecida, de baixa prioridade.

## 8. Manutenção deste arquivo

Atualize-o quando mudar algo que **outra estação precisaria saber antes de trabalhar** e que
não caiba no changelog: um requisito novo de ambiente, um bloqueio de publicação, uma decisão
de arquitetura tomada em conversa, uma armadilha que custou tempo a alguém.

Não o use como diário nem como log de sessão. Registro de *o que mudou* pertence ao
`CHANGELOG.md`; registro de *por que uma decisão foi tomada* pertence a `docs/decisions/`. Aqui
fica apenas o que um agente novo precisa carregar na cabeça para não repetir um erro já pago —
e a data no topo deve mudar junto.
