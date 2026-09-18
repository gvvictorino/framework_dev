#!/usr/bin/env bash
#
# setup-machine.sh — propaga os agentes e skills deste repositório (a árvore em que este
# script está, tipicamente ~/.claude-agent-framework/) para os locais fixos que o Claude Code
# espera: ~/.claude/agents/ e ~/.claude/skills/. decide.py e bootstrap-project.sh NÃO são
# copiados para lugar nenhum — eles já estão no lugar certo, aqui mesmo, referenciados por
# caminho absoluto a partir de ~/.claude-agent-framework/.
#
# Roda na primeira instalação, e de novo sempre que atualizar.sh (ou você manualmente) trouxer
# mudanças novas via git pull — é o passo que faz essas mudanças chegarem ao Claude Code.
#
# Uso:
#   ./setup-machine.sh            # instala/atualiza com confirmação por arquivo
#   ./setup-machine.sh --force    # sobrescreve tudo sem perguntar
#
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_SRC="$SCRIPT_DIR/agents"
SKILLS_SRC="$SCRIPT_DIR/skills"

AGENTS_DEST="$HOME/.claude/agents"
SKILLS_DEST="$HOME/.claude/skills"

FORCE=false
if [[ "${1:-}" == "--force" ]]; then
  FORCE=true
fi

if [[ ! -d "$AGENTS_SRC" ]] || [[ ! -d "$SKILLS_SRC" ]]; then
  echo "Erro: pastas 'agents/' e/ou 'skills/' não encontradas ao lado deste script ($SCRIPT_DIR)." >&2
  echo "Este script deve rodar de dentro do repositório do framework, não isolado." >&2
  exit 1
fi

mkdir -p "$AGENTS_DEST" "$SKILLS_DEST"

copiar_com_confirmacao() {
  local origem="$1"
  local destino="$2"

  if [[ -f "$destino" ]] && [[ "$FORCE" != true ]]; then
    if cmp -s "$origem" "$destino"; then
      echo "  = $(basename "$destino") (idêntico, nada a fazer)"
      return
    fi
    read -r -p "  ? $(basename "$destino") já existe e é diferente. Sobrescrever? [s/N] " resp
    if [[ ! "$resp" =~ ^[sS]$ ]]; then
      echo "  - $(basename "$destino") (mantido, não sobrescrito)"
      return
    fi
  fi

  cp "$origem" "$destino"
  echo "  + $(basename "$destino") instalado/atualizado"
}

echo "Instalando agentes em $AGENTS_DEST"
for arquivo in "$AGENTS_SRC"/*.md; do
  copiar_com_confirmacao "$arquivo" "$AGENTS_DEST/$(basename "$arquivo")"
done

echo "Instalando skills em $SKILLS_DEST"
for pasta_skill in "$SKILLS_SRC"/*/; do
  nome_skill="$(basename "$pasta_skill")"
  mkdir -p "$SKILLS_DEST/$nome_skill"
  copiar_com_confirmacao "$pasta_skill/SKILL.md" "$SKILLS_DEST/$nome_skill/SKILL.md"
done

VERSAO="$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo 'desconhecida')"

echo ""
echo "Setup de máquina concluído. Versão instalada: $VERSAO"
echo "decide.py e bootstrap-project.sh continuam em: $SCRIPT_DIR"
