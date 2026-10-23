r"""Curva de retencao de um video do YouTube (vale para Shorts, testado em 23/10/2026) e onde as pessoas saem.

    python -m robo retencao <youtube_id> [--pasta canais\<canal>\saida\<video>]

A YouTube Analytics API devolve 100 pontos (elapsedVideoTimeRatio 0,01..1) com:
- audienceWatchRatio: quantas visualizacoes chegam naquele ponto por visualizacao iniciada (passa de 1 no comeco
  quando as pessoas reveem);
- relativeRetentionPerformance: 0..1, comparado com videos de duracao parecida no YouTube (0,5 = na media).
Com a pasta do video (tempos.json da fabrica), cada cena ganha a perda dentro dela, e as 3 maiores quedas viram
o recado para o proximo roteiro. "Deslizou x assistiu" nao existe na API (so no Studio).
Precisa do token com yt-analytics.readonly (o do canal.py ja tem).
"""
import json
import os
import sys
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def curva(video_id, inicio='2026-01-01'):
    sys.path.insert(0, RAIZ)
    import canal
    from googleapiclient.discovery import build
    an = build('youtubeAnalytics', 'v2', credentials=canal.credencial(precisa=canal.NUMEROS))
    r = an.reports().query(ids='channel==MINE', startDate=inicio, endDate=date.today().isoformat(),
                           metrics='audienceWatchRatio,relativeRetentionPerformance',
                           dimensions='elapsedVideoTimeRatio', filters='video==' + video_id).execute()
    return [{'pos': x[0], 'assistem': x[1], 'relativo': x[2]} for x in r.get('rows', [])]


def _em(pontos, frac):
    """Valor da curva numa fracao do video (interpolado entre os 100 pontos)."""
    if frac <= pontos[0]['pos']:
        return pontos[0]['assistem']
    for a, b in zip(pontos, pontos[1:]):
        if a['pos'] <= frac <= b['pos']:
            t = (frac - a['pos']) / (b['pos'] - a['pos'])
            return a['assistem'] + t * (b['assistem'] - a['assistem'])
    return pontos[-1]['assistem']


def por_cena(pontos, pasta):
    tempos = json.load(open(os.path.join(pasta, 'tempos.json'), encoding='utf-8'))
    fim = max(p[2] for c in tempos for p in c['palavras']) + 1.0
    cenas = []
    for i, c in enumerate(tempos):
        ini = c['inicio'] / fim
        ate = (tempos[i + 1]['inicio'] if i + 1 < len(tempos) else fim) / fim
        antes, depois = _em(pontos, max(ini, 0.01)), _em(pontos, ate)
        texto = ' '.join(t for t, _, _ in c['legenda'])
        cenas.append({'cena': i, 'inicio_s': round(c['inicio'], 1), 'perda_pct': round(100 * (antes - depois) / max(antes, 1e-6), 1),
                      'assistem_no_fim': round(depois, 2), 'texto': texto[:90]})
    return cenas


def relatorio(video_id, pasta=None):
    pontos = curva(video_id)
    if not pontos:
        return {'video': video_id, 'erro': 'sem dados ainda (video novo demais ou sem views)'}
    rel = {'video': video_id, 'chegam_ao_fim': round(pontos[-1]['assistem'], 2),
           'relativo_medio': round(sum(p['relativo'] for p in pontos) / len(pontos), 2)}
    if pasta and os.path.exists(os.path.join(pasta, 'tempos.json')):
        cenas = por_cena(pontos, pasta)
        rel['cenas'] = cenas
        rel['maiores_quedas'] = sorted(cenas, key=lambda c: -c['perda_pct'])[:3]
        json.dump(rel, open(os.path.join(pasta, 'retencao.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return rel
