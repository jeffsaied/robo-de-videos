"""Pesquisa e escolha do tema SEM IA: Wikipedia (pt) por categorias do perfil do canal + o caderno de tendencias.
Nota cada candidato por tamanho do artigo, numero de imagens de licenca livre no Commons e se ja foi usado."""
import re
import unicodedata

import requests

AGENTE = {'User-Agent': 'FabricaDeCanais-Robo/1.0 (https://github.com/jeffsaied)'}
RECUSAR = re.compile(r'\bNC\b|NonCommercial|\bND\b|NoDerivs|Fair use', re.I)
LIVRES = re.compile(r'public domain|domínio público|\bPD\b|CC0|CC BY|CC-BY|GFDL|Attribution', re.I)


def chave(titulo):
    t = unicodedata.normalize('NFKD', titulo).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')


def _api(wiki, **p):
    p.update(format='json', formatversion=2)
    r = requests.get(f'https://{wiki}.wikipedia.org/w/api.php', params=p, headers=AGENTE, timeout=60)
    r.raise_for_status()
    return r.json()


def candidatos(fontes, limite=60):
    """Titulos das categorias configuradas (pt.wikipedia)."""
    titulos = []
    for cat in fontes.get('wikipedia_categorias', []):
        j = _api(fontes.get('wiki', 'pt'), action='query', list='categorymembers', cmtitle=cat, cmnamespace=0, cmlimit=limite)
        titulos += [m['title'] for m in j.get('query', {}).get('categorymembers', [])]
    titulos += fontes.get('temas_extras', [])
    return list(dict.fromkeys(titulos))


def artigo(titulo, wiki='pt'):
    """Texto puro, link e lista de imagens do artigo."""
    j = _api(wiki, action='query', titles=titulo, prop='extracts|images|info', explaintext=1, imlimit=50, inprop='url', redirects=1)
    p = j['query']['pages'][0]
    if p.get('missing'):
        return None
    # 'Ficheiro:' (pt) vira 'File:' (o Commons so entende o nome em ingles)
    imgs = ['File:' + i['title'].split(':', 1)[1] for i in p.get('images', []) if re.search(r'\.(jpe?g|png|tif+)$', i['title'], re.I)
            and not re.search(r'icon|logo|crystal|ambox|symbol|question|edit-|nuvola|wiki|flag of|bandeira', i['title'], re.I)]  # icones da Wikipedia
    return {'titulo': p['title'], 'texto': p.get('extract', ''), 'url': p.get('fullurl', ''), 'imagens': imgs}


def licencas(arquivos):
    """{arquivo: {licenca, autor, descricao}} so dos que tem licenca livre conhecida (Commons/Wikipedia)."""
    livres = {}
    for i in range(0, len(arquivos), 40):
        lote = arquivos[i:i + 40]
        r = requests.get('https://commons.wikimedia.org/w/api.php', headers=AGENTE, timeout=60, params={
            'action': 'query', 'titles': '|'.join(lote), 'prop': 'imageinfo', 'iiprop': 'extmetadata|size',
            'format': 'json', 'formatversion': 2})
        for p in r.json().get('query', {}).get('pages', []):
            info = (p.get('imageinfo') or [{}])[0]
            md = info.get('extmetadata', {})
            lic = (md.get('LicenseShortName', {}) or {}).get('value', '')
            if not lic or RECUSAR.search(lic) or not LIVRES.search(lic):
                continue
            if min(info.get('width', 0), info.get('height', 0)) < 500:  # pequena demais para 1080x1920
                continue
            desc = re.sub(r'<[^>]+>', '', (md.get('ImageDescription', {}) or {}).get('value', ''))[:160]
            autor = re.sub(r'<[^>]+>', '', (md.get('Artist', {}) or {}).get('value', ''))[:80]
            livres[p['title']] = {'licenca': lic, 'autor': autor.strip(), 'descricao': desc.strip()}
    return livres


def escolher(fontes, usados, minimo_texto=4000, minimo_imagens=4, avaliar=12, bonus=None):
    """Melhor candidato ainda nao usado: (dossie) ou None. Sem IA.
    `bonus(texto)` (0 a ~3, do placar: parecido com os melhores videos + termos em alta) soma 4000 pontos por unidade."""
    pontuados = []
    for t in candidatos(fontes):
        if chave(t) in usados or t.startswith(('Lista ', 'Categoria:')):
            continue
        a = artigo(t, fontes.get('wiki', 'pt'))
        if not a or len(a['texto']) < minimo_texto:
            continue
        extra = bonus(a['titulo'] + ' ' + a['texto']) if bonus else 0
        a['bonus_placar'] = round(extra, 2)
        pontuados.append((len(a['texto']) + 600 * len(a['imagens']) + 4000 * extra, a))
        if len(pontuados) >= avaliar:
            break
    for _, a in sorted(pontuados, key=lambda x: -x[0]):
        livres = licencas(a['imagens'])
        if len(livres) >= minimo_imagens:
            a['imagens_livres'] = livres
            a['chave'] = chave(a['titulo'])
            return a
    return None
