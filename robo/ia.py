"""Chamadas de IA, so onde agregam qualidade (roteiro e conferencia de fatos), com cache, orcamento e registro.

Provedores:
  claude_cli    -> o claude.exe da extensao do VS Code (usa a assinatura do Claude: sem cobranca por chamada,
                   mas com limite de uso da assinatura). O custo gravado e a estimativa que o proprio claude.exe
                   devolve (total_cost_usd), so como referencia.
  anthropic_api -> a API paga da Anthropic (chave ANTHROPIC_API_KEY no .env). Custo estimado pela tabela de
                   precos do robo.json, que tem de ser conferida com a pagina oficial antes de usar.
Modo sem IA (robo.json "ia.ligada": false ou --sem-ia): nenhuma chamada; o ciclo para na fila "precisa_roteiro".
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import date

from . import banco

PASTA = os.environ.get('ROBO_DADOS') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SemOrcamento(RuntimeError):
    pass


def _gasto_hoje(c):
    hoje = date.today().isoformat()
    r = c.execute("select count(*) n, coalesce(sum(custo_usd),0) s from chamadas_ia where em like ? and cache=0", (hoje + '%',)).fetchone()
    return r['n'], r['s']


def _claude_cli(cfg, prompt):
    import canal
    exe = canal.claude_exe(canal.cfg())
    r = subprocess.run([exe, '-p', '--model', cfg.get('modelo', 'sonnet'), '--output-format', 'json',
                        '--settings', json.dumps({'disableAllHooks': True}),
                        '--disallowedTools', 'Bash,PowerShell,Edit,Write,Read,WebFetch,WebSearch,Glob,Grep,Agent,Skill'],
                       input=prompt, capture_output=True, text=True, encoding='utf-8',
                       env=dict(os.environ, CLAUDE_SEM_AVISO='1'), cwd=PASTA, timeout=cfg.get('tempo_limite_s', 600))
    if r.returncode != 0:
        raise RuntimeError(f'claude.exe falhou ({r.returncode}): {(r.stderr or r.stdout)[-400:]}')
    j = json.loads(r.stdout)
    u = j.get('usage', {})
    return j.get('result', ''), u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0) + u.get('cache_creation_input_tokens', 0), \
        u.get('output_tokens', 0), float(j.get('total_cost_usd') or 0)


def _anthropic_api(cfg, prompt):
    import requests
    chave = os.environ.get('ANTHROPIC_API_KEY')
    if not chave:
        raise RuntimeError('falta ANTHROPIC_API_KEY no .env (provedor anthropic_api)')
    r = requests.post('https://api.anthropic.com/v1/messages', timeout=cfg.get('tempo_limite_s', 600), headers={
        'x-api-key': chave, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
        json={'model': cfg['modelo_api'], 'max_tokens': cfg.get('max_tokens', 8000),
              'messages': [{'role': 'user', 'content': prompt}]})
    r.raise_for_status()
    j = r.json()
    texto = ''.join(b.get('text', '') for b in j.get('content', []))
    ent, sai = j['usage']['input_tokens'], j['usage']['output_tokens']
    preco = cfg.get('preco_por_milhao_usd', {})
    custo = ent / 1e6 * preco.get('entrada', 0) + sai / 1e6 * preco.get('saida', 0)
    return texto, ent, sai, custo


PROVEDORES = {'claude_cli': _claude_cli, 'anthropic_api': _anthropic_api}


def chamar(c, cfg_ia, execucao, tarefa, prompt):
    """Devolve o texto. Usa o cache; respeita o orcamento do dia; grava provedor, modelo, tokens e custo."""
    if not cfg_ia.get('ligada', True):
        raise SemOrcamento('IA desligada (modo sem IA)')
    prov = cfg_ia.get('provedor', 'claude_cli')
    modelo = cfg_ia.get('modelo_api') if prov == 'anthropic_api' else cfg_ia.get('modelo', 'sonnet')
    chave = hashlib.sha256(f'{prov}|{modelo}|{prompt}'.encode('utf-8')).hexdigest()
    guardado = banco.cache_ler(c, chave)
    if guardado is not None:
        c.execute('insert into chamadas_ia (em,execucao,tarefa,provedor,modelo,tokens_entrada,tokens_saida,custo_usd,cache,ok,nota) values (?,?,?,?,?,0,0,0,1,1,?)',
                  (banco.agora(), execucao, tarefa, prov, modelo, 'do cache'))
        c.commit()
        return guardado
    n, gasto = _gasto_hoje(c)
    if n >= cfg_ia.get('max_chamadas_dia', 6):
        raise SemOrcamento(f'limite de {cfg_ia.get("max_chamadas_dia")} chamadas de IA por dia atingido')
    if gasto >= cfg_ia.get('max_custo_usd_dia', 1.0):
        raise SemOrcamento(f'orçamento do dia atingido (US$ {gasto:.2f})')
    try:
        texto, ent, sai, custo = PROVEDORES[prov](cfg_ia, prompt)
    except Exception as e:
        c.execute('insert into chamadas_ia (em,execucao,tarefa,provedor,modelo,tokens_entrada,tokens_saida,custo_usd,cache,ok,nota) values (?,?,?,?,?,0,0,0,0,0,?)',
                  (banco.agora(), execucao, tarefa, prov, modelo, str(e)[:300]))
        c.commit()
        raise
    nota = 'assinatura: custo só de referência' if prov == 'claude_cli' else 'estimativa pela tabela do robo.json'
    c.execute('insert into chamadas_ia (em,execucao,tarefa,provedor,modelo,tokens_entrada,tokens_saida,custo_usd,cache,ok,nota) values (?,?,?,?,?,?,?,?,0,1,?)',
              (banco.agora(), execucao, tarefa, prov, modelo, ent, sai, custo, nota))
    c.commit()
    banco.cache_gravar(c, chave, texto)
    return texto


def json_da_resposta(texto):
    return json.loads(texto[texto.index('{'):texto.rindex('}') + 1])
