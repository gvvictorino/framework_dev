"""
Suite de regressao do roteamento de decide.py.

Rode da raiz do framework:  python3 tests/test_decide.py

Cada caso monta um projeto descartavel em diretorio temporario e chama
decide.py como subprocesso, do jeito que a sessao principal chama — sem
importar o modulo, para tambem cobrir o ponto de entrada e o formato de saida.

Os casos 1, 2, 6, 7 e 9 sao os que falhavam antes da correcao da v1.0.1;
nao remova nenhum deles sem entender o bug que cada um trava.
"""
import json, subprocess, sys, tempfile, textwrap
from pathlib import Path

DECIDE = str(Path(__file__).resolve().parent.parent / "decide.py")
falhas = []

total = 0

def rodar(nome, arquivos, tarefa_id, esperado, motivo_contem=None):
    """
    `motivo_contem`: trecho que o campo `motivo` precisa conter. Existe para os
    casos de estado malformado, onde acertar a acao nao basta — o valor do
    tratamento esta em o motivo dizer QUAL arquivo esta torto.
    """
    global total
    total += 1
    with tempfile.TemporaryDirectory() as d:
        raiz = Path(d)
        for rel, conteudo in arquivos.items():
            alvo = raiz / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(textwrap.dedent(conteudo), encoding="utf-8")
        out = subprocess.run([sys.executable, DECIDE, tarefa_id],
                             cwd=raiz, capture_output=True, text=True)
        # json.loads falha alto de proposito: stdout vazio e a regressao que os
        # casos 17-19 travam, e ela nao deve passar por "esperado != obtido".
        got = json.loads(out.stdout)
    real = got.get("agente") or got.get("acao")
    ok = real == esperado
    if ok and motivo_contem is not None:
        ok = motivo_contem in got.get("motivo", "")
        if not ok:
            real = f"{real} (motivo sem {motivo_contem!r})"
    marca = "ok  " if ok else "FALHA"
    if not ok:
        falhas.append((nome, esperado, real, got))
    print(f"{marca} {nome}: esperado={esperado} obtido={real}")

TAREFA_UI = """\
    - id: T-001
      componente: checkout
      tipo: ui
      specs_referenciadas:
        - docs/specs/functional/checkout.md
        - docs/specs/design/checkout.md
      status: pending
      gerado_por: planner
    """
FUNC = "versao: 1\n# Checkout\n"

# 1. spec de design ausente -> agente design (antes: orquestrador-llm)
rodar("design ausente", {
    "tasks/backlog.md": TAREFA_UI,
    "docs/specs/functional/checkout.md": FUNC,
}, "T-001", "design")

# 2. spec funcional ausente -> planner (antes: orquestrador-llm)
rodar("funcional ausente", {"tasks/backlog.md": TAREFA_UI}, "T-001", "planner")

# 3. todas as specs presentes -> implementador
rodar("specs completas", {
    "tasks/backlog.md": TAREFA_UI,
    "docs/specs/functional/checkout.md": FUNC,
    "docs/specs/design/checkout.md": "versao: 1\n",
}, "T-001", "implementador")

# 4. spec orfa (categoria sem dono) -> orquestrador-llm, gatilho preservado
rodar("spec orfa sem dono", {
    "tasks/backlog.md": """\
    - id: T-002
      componente: checkout
      tipo: ui
      specs_referenciadas:
        - docs/specs/legado/checkout.md
      status: pending
    """,
}, "T-002", "orquestrador-llm")

# 5. spec de design de OUTRO componente -> orfa -> orquestrador-llm
rodar("design de outro componente", {
    "tasks/backlog.md": """\
    - id: T-003
      componente: checkout
      tipo: ui
      specs_referenciadas:
        - docs/specs/functional/checkout.md
        - docs/specs/design/carrinho.md
      status: pending
    """,
    "docs/specs/functional/checkout.md": FUNC,
}, "T-003", "orquestrador-llm")

# 6. pipeline: data_pipeline com schema ausente -> data-pipeline
rodar("pipeline ausente", {
    "tasks/backlog.md": """\
    - id: T-004
      componente: ingestao
      tipo: data_pipeline
      specs_referenciadas:
        - docs/specs/functional/ingestao.md
        - docs/specs/data-pipeline/ingestao.md
        - docs/specs/qualification/ingestao.md
      requer_qualificacao: true
      status: pending
    """,
    "docs/specs/functional/ingestao.md": FUNC,
}, "T-004", "data-pipeline")

# 7. prioridade: schema presente, qualification ausente -> llm-qualification
rodar("prioridade qualification", {
    "tasks/backlog.md": """\
    - id: T-004
      componente: ingestao
      tipo: data_pipeline
      specs_referenciadas:
        - docs/specs/functional/ingestao.md
        - docs/specs/data-pipeline/ingestao.md
        - docs/specs/qualification/ingestao.md
      requer_qualificacao: true
      status: pending
    """,
    "docs/specs/functional/ingestao.md": FUNC,
    "docs/specs/data-pipeline/ingestao.md": "versao: 1\n",
}, "T-004", "llm-qualification")

# 8. rede de seguranca: requer_qualificacao sem listar a spec -> llm-qualification
rodar("rede de seguranca por tipo", {
    "tasks/backlog.md": """\
    - id: T-005
      componente: ingestao
      tipo: api
      specs_referenciadas:
        - docs/specs/functional/ingestao.md
      requer_qualificacao: true
      status: pending
    """,
    "docs/specs/functional/ingestao.md": FUNC,
}, "T-005", "llm-qualification")

# 9. circuit breaker: 3 decisoes INDEPENDENTES nao escalam (antes: escalava)
ORFA = """\
    - id: T-002
      componente: checkout
      tipo: ui
      specs_referenciadas:
        - docs/specs/legado/checkout.md
      status: pending
    """
rodar("3 decisoes independentes", {
    "tasks/backlog.md": ORFA,
    "docs/decisions/orchestrator/index.md": """\
    - id: 1
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
    - id: 2
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
    - id: 3
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
    """,
}, "T-002", "orquestrador-llm")

# 10. circuit breaker: cadeia real de 3 supersedes ESCALA
rodar("cadeia real de 3", {
    "tasks/backlog.md": ORFA,
    "docs/decisions/orchestrator/index.md": """\
    - id: 1
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
    - id: 2
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
      supersedes: 1
    - id: 3
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
      supersedes: 2
    """,
}, "T-002", "escalar_humano")

# 11. indice corrompido (ciclo) nao trava
rodar("indice ciclico", {
    "tasks/backlog.md": ORFA,
    "docs/decisions/orchestrator/index.md": """\
    - id: 1
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
      supersedes: 2
    - id: 2
      gatilho: spec_ausente
      arquivos_envolvidos: [docs/specs/legado/checkout.md]
      status: resolved
      supersedes: 1
    """,
}, "T-002", "orquestrador-llm")

# 12. in-progress sem implementado -> implementador
rodar("in-progress pendente", {
    "tasks/in-progress.md": """\
    - id: T-010
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: doing
    """,
}, "T-010", "implementador")

# 13. in-progress com implementado -> revisor-qualidade
rodar("in-progress implementado", {
    "tasks/in-progress.md": """\
    - id: T-010
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      implementado: true
      status: doing
    """,
}, "T-010", "revisor-qualidade")

# 14. done -> documentador
rodar("done", {
    "tasks/done.md": """\
    - id: T-010
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      status: done
    """,
}, "T-010", "documentador")

# 15. travada 5 ciclos -> orquestrador-llm
rodar("travada 5 ciclos", {
    "tasks/in-progress.md": """\
    - id: T-010
      componente: checkout
      tipo: ui
      specs_referenciadas: []
      ciclos_sem_progresso: 5
      status: doing
    """,
}, "T-010", "orquestrador-llm")

# 16. tarefa inexistente -> escalar_humano
rodar("tarefa inexistente", {"tasks/backlog.md": "[]\n"}, "T-999", "escalar_humano")

# ---------------------------------------------------------------------------
# 17-19. Contrato de saida no erro (v1.0.7). Antes: traceback e stdout vazio,
# que a docstring de decide.py contradizia ao prometer "sempre um destes tres
# formatos". Quem escreve esses arquivos e agente de LLM — YAML torto e cenario
# de operacao normal, nao corrupcao exotica.
# ---------------------------------------------------------------------------

# 17. lista de itens que nao sao mapeamentos -> escalar_humano nomeando o
# arquivo. Antes: AttributeError em `tarefa.get`, porque localizar_tarefa
# presumia dict em cada entrada.
rodar("backlog com itens nao-mapeamento", {
    "tasks/backlog.md": """\
    - T-001
    - T-002
    """,
}, "T-001", "escalar_humano", motivo_contem="tasks/backlog.md")

# 18. YAML sintaticamente invalido -> escalar_humano, nao AttributeError
rodar("backlog YAML invalido", {
    "tasks/backlog.md": "- id: T-001\n   componente: [checkout\n",
}, "T-001", "escalar_humano", motivo_contem="tasks/backlog.md")

# 19. indice de decisoes torto -> escalar_humano, e nao breaker falhando aberto.
# Usa a tarefa de spec orfa do caso 4 porque o indice so e lido quando algum
# gatilho dispara — com tarefa saudavel, profundidade_cadeia nem roda.
rodar("indice de decisoes torto", {
    "tasks/backlog.md": """\
    - id: T-002
      componente: checkout
      tipo: ui
      specs_referenciadas:
        - docs/specs/legado/checkout.md
      status: pending
    """,
    "docs/decisions/orchestrator/index.md": """\
    - id: 1
      gatilho: spec_ausente
      arquivos_envolvidos: docs/specs/legado/checkout.md
      status: resolved
    """,
}, "T-002", "escalar_humano", motivo_contem="index.md")

print()
print(f"{total - len(falhas)}/{total} passaram")
for nome, esp, real, got in falhas:
    print(f"  FALHA {nome}: esperado={esp} obtido={real} :: {got}")
sys.exit(1 if falhas else 0)
