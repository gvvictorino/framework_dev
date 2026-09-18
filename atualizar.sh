#!/usr/bin/env bash
#
# atualizar.sh — busca atualizações do framework via git e propaga para ~/.claude/agents e
# ~/.claude/skills. Precisa rodar de dentro do repositório do framework (tipicamente
# ~/.claude-agent-framework/), que precisa ser um clone git com um remote configurado — sem
# isso, não há de onde buscar atualização, e o script avisa em vez de fingir que funcionou.
#
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -d .git ]]; then
  echo "Erro: $SCRIPT_DIR não é um repositório git." >&2
  echo "Sem controle de versão aqui, não há o que atualizar. Rode 'git init' (e configure um" >&2
  echo "remote, se quiser manter isto num repositório próprio) antes de usar este script." >&2
  exit 1
fi

VERSAO_ANTES="$(cat VERSION 2>/dev/null || echo 'desconhecida')"
echo "Versão instalada atualmente: $VERSAO_ANTES"
echo "Buscando atualizações..."
echo ""

git fetch --quiet

LOCAL="$(git rev-parse @)"
REMOTO="$(git rev-parse '@{u}' 2>/dev/null || echo "")"

if [[ -z "$REMOTO" ]]; then
  echo "Nenhum remote com upstream configurado para este branch — nada para buscar."
  echo "Se você mantém o framework só localmente (sem repositório remoto), isso é esperado:"
  echo "não há como haver 'atualização' sem uma origem para buscar."
  exit 0
fi

if [[ "$LOCAL" == "$REMOTO" ]]; then
  echo "Já está na versão mais recente ($VERSAO_ANTES)."
  exit 0
fi

echo "Mudanças disponíveis:"
git log --oneline "$LOCAL..$REMOTO"
echo ""

read -r -p "Aplicar atualização? [s/N] " resp
if [[ ! "$resp" =~ ^[sS]$ ]]; then
  echo "Cancelado — nada foi alterado."
  exit 0
fi

git pull --quiet

VERSAO_DEPOIS="$(cat VERSION 2>/dev/null || echo 'desconhecida')"
echo ""
echo "Atualizado: $VERSAO_ANTES → $VERSAO_DEPOIS"

if [[ -f CHANGELOG.md ]] && [[ "$VERSAO_ANTES" != "$VERSAO_DEPOIS" ]]; then
  echo ""
  echo "Changelog desta versão:"
  awk -v ver="$VERSAO_DEPOIS" '
    $0 ~ "\\[" ver "\\]" { found=1; print; next }
    found && /^## \[/ { exit }
    found { print }
  ' CHANGELOG.md
fi

echo ""
echo "Propagando para ~/.claude/agents e ~/.claude/skills..."
"$SCRIPT_DIR/setup-machine.sh" --force

echo ""
echo "Atualização concluída."
