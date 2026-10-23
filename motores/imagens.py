r"""Motor de imagens de arquivo real: baixar(fonte, destino) -> credito.

`fonte` = {"commons": "File:...", "autor": "opcional, quando o Commons traz o autor incompleto",
"quadro": segundos (so para video: tira esse quadro; negativo conta do fim), "audio": true (baixa o som original)}. O credito guarda titulo, autor e licenca; licenca NC
ou sem licenca e recusada. A legenda de creditos do post sai dessas fichas.
"""
import json
import os
import re
import subprocess
import time
import urllib.parse

import requests

AGENTE = {'User-Agent': 'FabricaDeCanais/1.0 (https://github.com/jeffsaied)'}
RECUSAR = re.compile(r'\bNC\b|NonCommercial', re.I)
# concepcao artistica nao pode passar por foto: o selo ILUSTRACAO entra sozinho quando o Commons diz isso
ILUSTRACAO = re.compile(r"artist.{0,3}s? (impression|concept|rendering|illustration)|artist concept|illustration|"
                        r"\bconcept art\b|\brendering\b|\brender\b|\brepresentation\b|\bvisuali[sz]ation\b|\bCGI\b|"
                        r"\b3D model\b|ilustra[cç][aã]o|concep[cç][aã]o art[ií]stica|representa[cç][aã]o art", re.I)


def _get(url, **kw):
    for k in range(5):
        r = requests.get(url, headers=AGENTE, timeout=120, **kw)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        time.sleep(15 * (k + 1))
    r.raise_for_status()


def baixar(fonte, destino, largura=2400):
    ficha = destino + '.credito.json'
    if os.path.exists(destino) and os.path.exists(ficha):
        credito = json.load(open(ficha, encoding='utf-8'))
        if (credito['titulo'] == fonte['commons'] and credito.get('quadro') == fonte.get('quadro')
                and 'ilustracao' in credito):                    # mesma fonte: reaproveita (ficha antiga e refeita)
            return dict(credito, autor=fonte.get('autor', credito['autor']))
    titulo = fonte['commons']
    q = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode({
        'action': 'query', 'format': 'json', 'titles': titulo, 'prop': 'imageinfo',
        'iiprop': 'url|extmetadata', 'iiurlwidth': largura, 'iiextmetadatafilter': 'LicenseShortName|Artist|ImageDescription|ObjectName'})
    pag = list(_get(q).json()['query']['pages'].values())[0]
    if 'imageinfo' not in pag:
        raise FileNotFoundError(f'nao existe no Commons: {titulo}')
    info = pag['imageinfo'][0]
    meta = info['extmetadata']
    licenca = meta.get('LicenseShortName', {}).get('value', '')
    if not licenca or RECUSAR.search(licenca):
        raise PermissionError(f'licenca nao serve ({licenca or "sem licenca"}): {titulo}')
    autor = re.sub(r'<[^>]+>', '', meta.get('Artist', {}).get('value', '')).strip()
    autor = re.sub(r'\s+', ' ', re.sub(r'^(Credit|Image|IMAGE):\s*', '', autor))
    autor = re.sub(r'^[\s,]*(and\s+)?', '', re.sub(r'(,\s*)+,', ',', autor)).strip(' ,')
    if 'quadro' in fonte:              # video do Commons: baixa o original e tira um quadro (segundos; negativo = do fim)
        bruto = destino + '.video'
        with open(bruto, 'wb') as f:
            f.write(_get(info['url']).content)
        t = fonte['quadro']
        pos = ['-sseof', str(t)] if t < 0 else ['-ss', str(t)]
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *pos, '-i', bruto, '-frames:v', '1', '-f', 'image2', destino], check=True)
        os.remove(bruto)
    else:                              # audio vai inteiro (url original); imagem vem redimensionada (thumburl)
        with open(destino, 'wb') as f:
            f.write(_get(info['url'] if fonte.get('audio') else info.get('thumburl', info['url'])).content)
    descricao = ' '.join(re.sub(r'<[^>]+>', ' ', meta.get(k, {}).get('value', '')) for k in ('ImageDescription', 'ObjectName'))
    credito = {'titulo': titulo, 'autor': fonte.get('autor', autor), 'licenca': licenca, 'quadro': fonte.get('quadro'),
               'ilustracao': bool(ILUSTRACAO.search(titulo + ' ' + descricao)),
               'pagina': 'https://commons.wikimedia.org/wiki/' + urllib.parse.quote(titulo.replace(' ', '_'))}
    json.dump(credito, open(ficha, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    time.sleep(3)
    return credito


def linha_de_creditos(creditos):
    """Agrupa por autor/licenca: 'NASA (dominio publico) · ESO/M. Kornmesser (CC BY 4.0) ...'"""
    vistos, partes = set(), []
    for c in creditos:
        livre = c['licenca'].lower() in ('public domain', 'cc0', 'pd')
        autor = c['autor'] if len(c['autor']) <= 70 else c['autor'][:70].rsplit(' ', 1)[0] + '…'
        txt = autor + ('' if livre else f" ({c['licenca']})")
        if txt not in vistos:
            vistos.add(txt)
            partes.append(txt)
    return ' · '.join(partes)
