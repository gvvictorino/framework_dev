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
# O script mantém um manifesto (~/.claude/.agent-framework-manifest) com os arquivos que ELE
# instalou. É o que permite detectar agente ou skill removido do framework sem nunca confundi-lo
# com arquivo que você mesmo pôs em ~/.claude/ por outra via.
#
# Uso:
#   ./setup-machine.sh            # instala/atualiza com confirmação por arquivo
#   ./setup-machine.sh --force    # sobrescreve tudo sem perguntar (usado por atualizar.sh)
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
MANIFESTO="$HOME/.claude/.agent-framework-manifest"

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

INSTALADOS=()

copiar_com_confirmacao() {
  local origem="$1"
  local destino="$2"
  local rotulo="${3:-$(basename "$destino")}"

  if [[ -f "$destino" ]] && [[ "$FORCE" != true ]]; then
    if cmp -s "$origem" "$destino"; then
      echo "  = $rotulo (idêntico, nada a fazer)"
      return
    fi
    read -r -p "  ? $rotulo já existe e é diferente. Sobrescrever? [s/N] " resp
    if [[ ! "$resp" =~ ^[sS]$ ]]; then
      echo "  - $rotulo (mantido, não sobrescrito)"
      return
    fi
  fi

  cp "$origem" "$destino"
  echo "  + $rotulo instalado/atualizado"
}

echo "Instalando agentes em $AGENTS_DEST"
for arquivo in "$AGENTS_SRC"/*.md; do
  destino="$AGENTS_DEST/$(basename "$arquivo")"
  copiar_com_confirmacao "$arquivo" "$destino"
  INSTALADOS+=("$destino")
done

# A árvore inteira de cada skill, não só o SKILL.md: skills do Claude Code admitem arquivos de
# apoio (references/, scripts/, assets/). Copiar só o SKILL.md funcionava enquanto todas as
# skills fossem de arquivo único — no dia em que uma ganhasse um arquivo de apoio, ele não seria
# instalado e a skill quebraria em todas as máquinas, sem nenhum erro aqui.
echo "Instalando skills em $SKILLS_DEST"
# O laco le a lista pelo descritor 3, nao pela stdin: copiar_com_confirmacao usa `read` para
# perguntar, e com a stdin tomada pelo find ele leria os proprios caminhos como se fossem a
# resposta do usuario, batendo em EOF e abortando o script sob `set -e`.
while IFS= read -r -d '' origem <&3; do
  relativo="${origem#"$SKILLS_SRC"/}"
  destino="$SKILLS_DEST/$relativo"
  mkdir -p "$(dirname "$destino")"
  copiar_com_confirmacao "$origem" "$destino" "$relativo"
  INSTALADOS+=("$destino")
done 3< <(find "$SKILLS_SRC" -type f -print0 | sort -z)

# --- Deriva: o que este script instalou um dia e o framework não tem mais ---
#
# Só o manifesto torna isso seguro. Sem ele, "está no destino e não na origem" incluiria
# qualquer agente ou skill que você tenha instalado por outra via, e o script passaria a
# sugerir apagar coisa que nunca foi dele.
MANTIDOS=()
if [[ -f "$MANIFESTO" ]]; then
  ORFAOS=()
  while IFS= read -r anterior; do
    [[ -z "$anterior" ]] && continue
    [[ ! -e "$anterior" ]] && continue
    encontrado=false
    for atual in ${INSTALADOS[@]+"${INSTALADOS[@]}"}; do
      if [[ "$atual" == "$anterior" ]]; then encontrado=true; break; fi
    done
    if [[ "$encontrado" == false ]]; then ORFAOS+=("$anterior"); fi
  done < "$MANIFESTO"

  if [[ ${#ORFAOS[@]} -gt 0 ]]; then
    echo ""
    echo "Estes arquivos foram instalados por este script e não existem mais no framework:"
    for orfao in "${ORFAOS[@]}"; do
      echo "    $orfao"
    done
    echo ""
    echo "Enquanto continuarem aí, seguem invocáveis pelo Claude Code — um agente removido do"
    echo "framework continua vivo e chamável em toda máquina onde já tinha sido instalado."

    if [[ "$FORCE" == true ]]; then
      # --force existe para rodar sem interação (atualizar.sh depende disso). Apagar em
      # silêncio nesse modo seria a única operação destrutiva do script acontecendo sem
      # ninguém ver. Reporta e para.
      echo ""
      echo "Modo --force: nada foi removido. Para remover, rode ./setup-machine.sh sem --force,"
      echo "ou apague à mão os caminhos listados acima."
      MANTIDOS=("${ORFAOS[@]}")
    else
      for orfao in "${ORFAOS[@]}"; do
        read -r -p "  ? Remover $orfao? [s/N] " resp
        if [[ "$resp" =~ ^[sS]$ ]]; then
          rm -f "$orfao"
          echo "  - $orfao removido"
        else
          echo "  = $orfao mantido"
          MANTIDOS+=("$orfao")
        fi
      done
    fi
  fi
else
  echo ""
  echo "(primeira execução com controle de deriva: a partir de agora este script registra o que"
  echo " instalou, e passa a avisar quando um agente ou skill sair do framework)"
fi

# Órfão mantido continua no manifesto de propósito: senão o script esqueceria que o arquivo veio
# dele e nunca mais ofereceria remover.
printf '%s\n' ${INSTALADOS[@]+"${INSTALADOS[@]}"} ${MANTIDOS[@]+"${MANTIDOS[@]}"} > "$MANIFESTO"

VERSAO="$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo 'desconhecida')"

echo ""
echo "Setup de máquina concluído. Versão instalada: $VERSAO"
echo "decide.py e bootstrap-project.sh continuam em: $SCRIPT_DIR"
