#!/usr/bin/env bash
#
# bootstrap-project.sh — cria o esqueleto de UM projeto (CLAUDE.md + docs/ + tasks/).
# Roda uma vez por projeto novo. É seguro rodar de novo num projeto existente: nunca
# sobrescreve arquivo que já existe (backlog.md, in-progress.md, done.md, specs, etc.) —
# só cria o que estiver faltando.
#
# Uso:
#   ./bootstrap-project.sh <caminho-do-projeto> [--shared|--local] [--atualizar-claude-md]
#
#   --atualizar-claude-md  se o projeto já tem o bloco da arquitetura numa versão anterior,
#                       substitui o conteúdo ENTRE os marcadores sem perguntar, preservando
#                       tudo fora deles e guardando CLAUDE.md.bak. Sem a flag, num terminal
#                       o script pergunta; fora de um, só reporta.
#
#   --shared (padrão)  CLAUDE.md aponta para o decide.py compartilhado em
#                       ~/.claude-agent-framework/decide.py (instalado por setup-machine.sh)
#   --local             copia decide.py PARA DENTRO do projeto, em orchestrator/decide.py —
#                       use isso só se este projeto precisar de uma versão própria da lógica
#                       de decisão, diferente dos outros
#
# Se invocado como "sh bootstrap-project.sh" em vez de "./bootstrap-project.sh" ou
# "bash bootstrap-project.sh", reexecuta automaticamente sob bash (ver setup-machine.sh
# para a explicação completa de por que isso é necessário).
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/templates/CLAUDE.md.template"
FRAMEWORK_DECIDE="$SCRIPT_DIR/decide.py"

PROJETO="${1:-}"

# Flags depois do caminho, em qualquer ordem. Antes o modo era estritamente posicional
# (`${2:---shared}`), o que faria qualquer flag nova passada em $2 ser lida como modo.
MODO="--shared"
ATUALIZAR_BLOCO=false
for arg in "${@:2}"; do
  case "$arg" in
    --shared|--local)        MODO="$arg" ;;
    --atualizar-claude-md)   ATUALIZAR_BLOCO=true ;;
    *) echo "Aviso: argumento desconhecido ignorado: $arg" >&2 ;;
  esac
done

if [[ -z "$PROJETO" ]]; then
  echo "Uso: ./bootstrap-project.sh <caminho-do-projeto> [--shared|--local] [--atualizar-claude-md]" >&2
  exit 1
fi

mkdir -p "$PROJETO"
cd "$PROJETO"

# --- Detecta qual comando python está disponível NESTA máquina ---
# "python" nem sempre existe (Mac/Linux modernos só têm "python3" por padrão) — hardcodar
# "python" quebra o CLAUDE.md gerado silenciosamente, sem erro até alguém tentar usá-lo.
if command -v python3 &>/dev/null; then
  PY_BIN="python3"
elif command -v python &>/dev/null; then
  PY_BIN="python"
else
  echo "Aviso: nem 'python3' nem 'python' encontrados no PATH desta máquina." >&2
  echo "O CLAUDE.md será gerado com 'python3' mesmo assim — ajuste manualmente se necessário." >&2
  PY_BIN="python3"
fi

criar_se_ausente() {
  local caminho="$1"
  local conteudo="$2"

  if [[ -e "$caminho" ]]; then
    echo "  = $caminho (já existe, mantido)"
    return
  fi
  mkdir -p "$(dirname "$caminho")"
  printf '%s' "$conteudo" > "$caminho"
  echo "  + $caminho criado"
}

echo "Bootstrap do projeto em: $(pwd)"
echo "Modo: $MODO"
echo ""

# --- Esqueleto de pastas e arquivos de estado (idempotente) ---
for pasta in \
  docs/specs/functional docs/specs/design docs/specs/data-pipeline docs/specs/qualification \
  docs/decisions/orchestrator docs/decisions/gap-reports docs/decisions/adr docs/decisions/auditoria \
  tasks
do
  mkdir -p "$pasta"
done

criar_se_ausente "tasks/backlog.md" "[]
"
criar_se_ausente "tasks/in-progress.md" "[]
"
criar_se_ausente "tasks/done.md" "[]
"
criar_se_ausente "docs/decisions/orchestrator/index.md" "[]
"

# --- CLAUDE.md, com o comando de decisão correto conforme o modo ---
if [[ "$MODO" == "--local" ]]; then
  DECIDE_CMD="$PY_BIN orchestrator/decide.py"
  mkdir -p orchestrator
  if [[ ! -f "orchestrator/decide.py" ]]; then
    cp "$FRAMEWORK_DECIDE" orchestrator/decide.py
    echo "  + orchestrator/decide.py copiado (modo local)"
    # A VERSION viaja junto com a cópia. É o que permite a decide.py perceber, e avisar em
    # stderr, que este projeto ficou para trás: atualizar.sh atualiza os agentes de toda a
    # máquina, mas nunca esta cópia do roteador — e agentes e roteador são acoplados (a
    # v1.0.1 mudou decide.py E orquestrador-llm.md na mesma correção). Sem a VERSION aqui,
    # o projeto roda agentes novos contra roteamento antigo sem nenhum sinal.
    cp "$SCRIPT_DIR/VERSION" orchestrator/VERSION
    echo "  + orchestrator/VERSION copiado (marca a versão desta cópia)"
  else
    echo "  = orchestrator/decide.py (já existe, mantido)"
    if [[ ! -f "orchestrator/VERSION" ]]; then
      echo "    nota: sem orchestrator/VERSION, esta cópia não consegue avisar quando ficar"
      echo "    desatualizada. Se ela veio do framework, registre a versão dela com:"
      echo "        cp $SCRIPT_DIR/VERSION orchestrator/VERSION"
    fi
  fi
else
  # O caminho é deliberadamente fixo: a arquitetura depende de uma cópia única do
  # framework em local canônico, com os artefatos resolvidos relativos ao projeto
  # chamador (decide.py usa ROOT = Path.cwd()). Derivar de SCRIPT_DIR devolveria
  # variabilidade a um caminho que precisa ser o mesmo em todo projeto da máquina.
  #
  # Fixo não quer dizer presumido: se o framework não estiver instalado ali, o
  # CLAUDE.md gerado teria um Passo 1 que falha, e a instrução do próprio CLAUDE.md
  # nesse caso é PARAR — o projeto nasceria travado, sem sinal nenhum na hora.
  DECIDE_CMD="$PY_BIN \$HOME/.claude-agent-framework/decide.py"

  if [[ ! -f "$HOME/.claude-agent-framework/decide.py" ]]; then
    echo ""
    echo "  AVISO — o framework não está instalado no caminho canônico."
    echo ""
    echo "  Esperado: $HOME/.claude-agent-framework/decide.py (não encontrado)"
    echo "  Rodando de: $SCRIPT_DIR"
    echo ""
    echo "  O CLAUDE.md será gerado apontando para o caminho canônico, como deve ser."
    echo "  Enquanto ele não existir, o Passo 1 do ciclo falha e nenhuma tarefa avança."
    echo ""
    echo "  Para corrigir, instale o framework no lugar esperado:"
    echo "      git clone <este-repositório> $HOME/.claude-agent-framework"
    echo ""
  fi
fi

MARKER_BEGIN="<!-- BEGIN arquitetura-agentes-ia"
MARKER_END="<!-- END arquitetura-agentes-ia -->"
VERSAO_FRAMEWORK="$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo 'desconhecida')"

# O bloco carrega a versão do framework que o gerou. Sem essa marca, um projeto ficava com as
# instruções de fluxo de uma versão antiga para sempre, em silêncio: o script detectava o
# marcador e preservava o bloco, e nada mais no sistema olhava para ele. A auditoria de
# 2026-09-24 mediu o efeito — um projeto rodando o bloco da v1.0.6 não sabia da seleção
# automática de tarefa entregue na v1.1.0, e a sessão principal seguia escolhendo por
# julgamento, que é exatamente o que aquela correção removeu.
renderizar_template() {
  sed -e "s|{{DECIDE_PY_CMD}}|$DECIDE_CMD|" \
      -e "s|{{FRAMEWORK_VERSION}}|$VERSAO_FRAMEWORK|" "$TEMPLATE"
}

# Substitui SÓ o conteúdo entre os marcadores, preservando tudo fora deles — o arquivo ao redor
# é do usuário e costuma ser a maior parte dele.
substituir_bloco() {
  local renderizado="$1"
  "$PY_BIN" - "$renderizado" <<'PYEOF'
import sys, pathlib
INICIO = "<!-- BEGIN arquitetura-agentes-ia"
FIM = "<!-- END arquitetura-agentes-ia -->"
novo_bloco = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").strip("\n")
alvo = pathlib.Path("CLAUDE.md")
texto = alvo.read_text(encoding="utf-8")
i = texto.find(INICIO)
j = texto.find(FIM)
if i == -1 or j == -1 or j < i:
    sys.exit("  ERRO: marcadores ausentes ou fora de ordem — nada foi alterado.")
alvo.write_text(texto[:i] + novo_bloco + texto[j + len(FIM):], encoding="utf-8")
PYEOF
}

if [[ -f "CLAUDE.md" ]] && grep -q "$MARKER_BEGIN" CLAUDE.md 2>/dev/null; then
  versao_no_bloco="$(grep -o 'BEGIN arquitetura-agentes-ia v[0-9][0-9.]*' CLAUDE.md \
                     | head -1 | sed 's/.* v//')"

  if [[ "$versao_no_bloco" == "$VERSAO_FRAMEWORK" ]]; then
    echo "  = CLAUDE.md já tem o bloco da arquitetura na v$VERSAO_FRAMEWORK (nada a fazer)"
  else
    if [[ -z "$versao_no_bloco" ]]; then
      echo "  ! CLAUDE.md tem o bloco da arquitetura SEM marca de versão (gerado antes da v1.2.0)."
    else
      echo "  ! CLAUDE.md tem o bloco da arquitetura na v$versao_no_bloco; o framework está na v$VERSAO_FRAMEWORK."
    fi
    echo "    O bloco traz as instruções de fluxo que a sessão principal segue. Desatualizado,"
    echo "    o projeto deixa de usar capacidade que já existe no roteador — sem nenhum erro."

    aplicar=false
    if [[ "$ATUALIZAR_BLOCO" == true ]]; then
      aplicar=true   # pedido explícito na linha de comando; não pergunta
    elif [[ ! -t 0 ]]; then
      # Sem terminal não há como confirmar, e reescrever o CLAUDE.md do usuário em silêncio
      # seria a única operação destrutiva deste script sem ninguém ver.
      echo "    Execução não interativa: nada foi alterado. Rode num terminal, ou passe"
      echo "    --atualizar-claude-md para atualizar sem perguntar."
    else
      read -r -p "    Atualizar o bloco agora (o conteúdo fora dos marcadores é preservado)? [s/N] " resp
      if [[ "$resp" =~ ^[sS]$ ]]; then aplicar=true; else echo "    = bloco mantido como está"; fi
    fi

    if [[ "$aplicar" == true ]]; then
      cp CLAUDE.md CLAUDE.md.bak
      TMP_BLOCO="$(mktemp)"
      renderizar_template > "$TMP_BLOCO"
      substituir_bloco "$TMP_BLOCO"
      rm -f "$TMP_BLOCO"
      echo "    + bloco atualizado para a v$VERSAO_FRAMEWORK (cópia anterior em CLAUDE.md.bak)"
    fi
  fi
elif [[ -f "CLAUDE.md" ]]; then
  printf '\n' >> CLAUDE.md
  renderizar_template >> CLAUDE.md
  echo "  + bloco da arquitetura ACRESCENTADO ao CLAUDE.md existente (conteúdo anterior preservado)"
else
  renderizar_template > CLAUDE.md
  echo "  + CLAUDE.md criado (comando de decisão: $DECIDE_CMD)"
fi

# --- Aviso se não for repositório git ainda ---
if [[ ! -d ".git" ]]; then
  echo ""
  echo "Aviso: esta pasta ainda não é um repositório git. A arquitetura depende de git para"
  echo "sincronizar estado entre computadores — rode 'git init' quando for começar a trabalhar."
fi

echo ""
echo "Bootstrap concluído. Próximo passo: abra o projeto no Claude Code e peça ao Planner"
echo "para levantar os requisitos da primeira feature."
