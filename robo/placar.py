r"""Placar dos videos do canal e o "peso" que ele da para a escolha de tema (sem IA).

De onde vem: o tendencias.py ja grava, 3 vezes por dia, as views e likes dos nossos videos em
tendencias\<data>.json -> "nossos". O placar le a coleta mais recente (nao chama API de novo).

- ranking(perfil): videos do canal com views por dia desde a publicacao (a medida que compara videos de idades
  diferentes) e taxa de like. Inscritos ganhos por video sao parciais na API (so contam inscricao na pagina de
  exibicao), por isso ficam de fora.
- bonus(texto, perfil): nota de 0 a ~3 para um candidato. Soma (a) palavras em comum com os 3 melhores videos e
  (b) termos que estao em alta (Google BR/EUA) e a "IDEIA PARA O ARQUIVO DARK" do aviso mais recente.
  E um empurrao na ordem, nao um filtro: tema sem bonus continua podendo ser escolhido.
"""
import glob
import json
import os
import re
import unicodedata
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_TEND = os.path.join(RAIZ, 'tendencias')
VAZIAS = set('''sobre entre depois antes quando porque ainda nunca ninguem alguem tinha foram seria esses essas
desse dessa este esta isso aquele aquela muito mais menos onde como qual quais quem cada todo toda todos todas outro
outra outros outras shorts video videos canal historia historias misterio misterios teoria explicou explicacao
ninguem hoje anos'''.split())


def _norm(t):
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9 ]+', ' ', t)


def _palavras(t, minimo=5):
    return {w for w in _norm(t).split() if len(w) >= minimo and w not in VAZIAS and not w.isdigit()}


def _ultima_coleta():
    arqs = sorted(glob.glob(os.path.join(PASTA_TEND, '*.json')))
    if not arqs:
        return {}
    try:
        return json.load(open(arqs[-1], encoding='utf-8'))
    except ValueError:
        return {}


def ranking(perfil):
    hoje = datetime.now()
    nome = perfil.get('nome', '')
    linhas = []
    for v in _ultima_coleta().get('nossos', []):
        if nome and v.get('canal') != nome:
            continue
        try:
            dias = max(0.5, (hoje - datetime.fromisoformat(v['publicado'][:10])).days + 0.5)
        except (KeyError, ValueError):
            continue
        views = v.get('views') or 0
        linhas.append({'titulo': re.sub(r'\s*#shorts\s*', ' ', v.get('titulo', '')).strip(), 'publicado': v['publicado'][:10],
                       'views': views, 'likes': v.get('likes') or 0, 'views_dia': round(views / dias, 1),
                       'like_pct': round(100 * (v.get('likes') or 0) / views, 1) if views else 0.0})
    return sorted(linhas, key=lambda x: -x['views_dia'])


def _termos_em_alta():
    col = _ultima_coleta()
    termos = set()
    for pais in ('BR', 'US'):
        for g in col.get('google', {}).get(pais, []):
            termos |= _palavras(g.get('termo', ''), 4)
    avisos = sorted(glob.glob(os.path.join(PASTA_TEND, '*_aviso.txt')))
    if avisos:
        txt = open(avisos[-1], encoding='utf-8').read()
        m = re.search(r'IDEIA PARA O ARQUIVO DARK\s*(.+?)(?:\n[A-ZÚÇÃÉ ]{6,}\n|\Z)', txt, re.S)
        if m and not re.search(r'nenhuma liga', m.group(1), re.I):
            termos |= _palavras(m.group(1))
    return termos


def bonus(texto, perfil):
    """Quanto este tema combina com o que ja deu certo e com o que esta em alta."""
    alvo = _palavras(texto[:3000])
    melhores = ranking(perfil)[:3]
    fortes = set().union(*(_palavras(v['titulo']) for v in melhores)) if melhores else set()
    pontos = 0.5 * len(alvo & fortes) + 1.0 * len(alvo & _termos_em_alta())
    return min(pontos, 3.0)


def resumo(perfil, pasta_canal=None):
    """Grava canais/<canal>/placar.json (para quem quiser olhar) e devolve o ranking."""
    r = ranking(perfil)
    if pasta_canal:
        json.dump({'atualizado': datetime.now().isoformat(timespec='minutes'), 'videos': r},
                  open(os.path.join(pasta_canal, 'placar.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return r
