r"""Graficos proprios do canal (so dados reais), 1080x1920, com margem folgada (a cena da zoom de ate 12%)
e o conteudo acima da faixa da legenda. Cores e fontes vem do perfil do canal: chame usar(perfil) antes.
Texto nunca menor que 38 px (tem que ler no celular).
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

LARG, ALT = 1080, 1920
FUNDO, AMBAR, CINZA, BRANCO, VERMELHO = (10, 10, 14), (255, 196, 0), (120, 120, 130), (240, 240, 240), (235, 30, 30)
FONTES = {'impact.ttf': r'C:\Windows\Fonts\impact.ttf', 'segoeui.ttf': r'C:\Windows\Fonts\segoeui.ttf',
          'segoeuib.ttf': r'C:\Windows\Fonts\segoeuib.ttf', 'segoeuii.ttf': r'C:\Windows\Fonts\segoeuii.ttf'}


def _rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def usar(perfil):
    """Troca cores e fontes pelas do perfil do canal (canal.json -> visual)."""
    global FUNDO, AMBAR, CINZA, BRANCO, VERMELHO
    v = perfil['visual']
    FUNDO, AMBAR, VERMELHO, BRANCO, CINZA = (_rgb(v[k]) for k in ('fundo', 'destaque', 'alerta', 'texto', 'apagado'))
    FONTES.update({'impact.ttf': v['fonte_titulo'], 'segoeui.ttf': v['fonte_texto'],
                   'segoeuib.ttf': v['fonte_texto_negrito'], 'segoeuii.ttf': v['fonte_texto_italico']})


def fonte(nome, tam):
    return ImageFont.truetype(FONTES[nome], tam)


def centro(d, y, texto, f, cor):
    while d.textlength(texto, font=f) > LARG - 160 and f.size > 38:   # encolhe ate caber, nunca abaixo de 38 px
        f = ImageFont.truetype(f.path, f.size - 4)
    d.text(((LARG - d.textlength(texto, font=f)) / 2, y), texto, font=f, fill=cor)


def _rodape(d, texto):
    centro(d, ALT - 250, texto, fonte('segoeuii.ttf', 38), (140, 140, 150))


def barras(rotulos, valores, titulo, subtitulo, eixo, fonte_dados, destino, destaque=None):
    """Barras verticais com o valor em cima de cada uma; `destaque` = indice pintado de vermelho."""
    img = Image.new('RGB', (LARG, ALT), FUNDO)
    d = ImageDraw.Draw(img)
    centro(d, 110, titulo, fonte('impact.ttf', 92), BRANCO)
    centro(d, 230, subtitulo, fonte('segoeui.ttf', 44), CINZA)
    base, topo, esq, dir_ = 1060, 420, 170, LARG - 150
    passo = (dir_ - esq) / len(valores)
    larg = passo * 0.62
    vmax = max(valores)
    for k in range(0, int(vmax) + 1, 10):   # grade
        y = base - (base - topo) * k / vmax
        d.line([(esq - 20, y), (dir_, y)], fill=(40, 40, 48), width=2)
        d.text((esq - 80, y - 22), str(k), font=fonte('segoeui.ttf', 40), fill=CINZA)
    for i, (r, v) in enumerate(zip(rotulos, valores)):
        x = esq + passo * i + (passo - larg) / 2
        y = base - (base - topo) * v / vmax
        cor = VERMELHO if i == destaque else AMBAR
        d.rectangle([x, y, x + larg, base], fill=cor)
        fv, fr = fonte('impact.ttf', 58), fonte('impact.ttf', 84)
        d.text((x + (larg - d.textlength(str(v), font=fv)) / 2, y - 76), str(v), font=fv, fill=BRANCO)
        d.text((x + (larg - d.textlength(r, font=fr)) / 2, base + 24), r, font=fr, fill=cor)
    centro(d, base + 140, eixo, fonte('segoeui.ttf', 40), CINZA)
    _rodape(d, fonte_dados)
    img.save(destino, quality=95)


def linha_do_tempo(eventos, titulo, fonte_dados, destino, destaque=None):
    """eventos = [(ano, texto curto, texto menor)]; linha vertical com pontos."""
    img = Image.new('RGB', (LARG, ALT), FUNDO)
    d = ImageDraw.Draw(img)
    centro(d, 110, titulo, fonte('impact.ttf', 92), BRANCO)
    x0, y0, y1 = 300, 330, 1080
    d.line([(x0, y0), (x0, y1)], fill=(60, 60, 70), width=6)
    passo = (y1 - y0) / max(1, len(eventos) - 1)
    for i, (ano, txt, menor) in enumerate(eventos):
        y = y0 + passo * i
        cor = VERMELHO if i == destaque else AMBAR
        d.ellipse([x0 - 22, y - 22, x0 + 22, y + 22], fill=cor)
        fa = fonte('impact.ttf', 70)
        d.text((x0 - 50 - d.textlength(ano, font=fa), y - 44), ano, font=fa, fill=cor)
        d.text((x0 + 50, y - 46), txt, font=fonte('segoeuib.ttf', 50), fill=BRANCO)
        d.text((x0 + 50, y + 14), menor, font=fonte('segoeui.ttf', 40), fill=CINZA)
    _rodape(d, fonte_dados)
    img.save(destino, quality=95)


def cartao(numero, legenda, linhas, fonte_dados, destino):
    """Um numero grande em ambar com 2 ou 3 linhas de contexto."""
    img = Image.new('RGB', (LARG, ALT), FUNDO)
    d = ImageDraw.Draw(img)
    f = fonte('impact.ttf', 230)
    while d.textlength(numero, font=f) > LARG - 200:
        f = fonte('impact.ttf', f.size - 10)
    centro(d, 280, numero, f, AMBAR)
    centro(d, 560, legenda, fonte('segoeuib.ttf', 56), BRANCO)
    for i, l in enumerate(linhas):
        centro(d, 720 + i * 100, l, fonte('segoeui.ttf', 48), (205, 205, 212))
    _rodape(d, fonte_dados)
    img.save(destino, quality=95)


def trajetoria(q, e, marcas, titulo, subtitulo, fonte_dados, destino, alcance=1.7):
    """Orbita hiperbolica (q em UA, excentricidade e) desenhada no plano dela, com as orbitas de Mercurio a
    Marte para dar escala. marcas = [(dias_depois_do_perielio, rotulo, 'dir'|'esq'|'baixo')]; posicao calculada pela equacao de Kepler."""
    img = Image.new('RGB', (LARG, ALT), FUNDO)
    d = ImageDraw.Draw(img)
    centro(d, 110, titulo, fonte('impact.ttf', 92), BRANCO)
    centro(d, 230, subtitulo, fonte('segoeui.ttf', 42), CINZA)
    cx, cy, esc = LARG / 2, 780, 440 / alcance       # px por UA
    tela = lambda x, y: (cx + x * esc, cy - y * esc)
    for raio, nome in ((0.387, None), (0.723, None), (1.0, 'Terra'), (1.524, 'Marte')):
        d.ellipse([cx - raio * esc, cy - raio * esc, cx + raio * esc, cy + raio * esc], outline=(55, 55, 65), width=3)
        if nome:
            f = fonte('segoeui.ttf', 38)
            d.text((cx - d.textlength(nome, font=f) / 2, cy + raio * esc + 4), nome, font=f, fill=CINZA)
    d.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=AMBAR)                      # Sol
    a = q / (e - 1)
    n = math.sqrt(2.9591220828e-4 / a ** 3)                                          # rad/dia (GM do Sol em UA^3/dia^2)

    def pos(dias):
        m, h = n * dias, math.asinh(n * dias / e) if dias else 0.0
        for _ in range(60):
            h -= (e * math.sinh(h) - h - m) / (e * math.cosh(h) - 1)
        nu = 2 * math.atan(math.sqrt((e + 1) / (e - 1)) * math.tanh(h / 2))
        r = a * (e * math.cosh(h) - 1)
        return r * math.cos(nu), r * math.sin(nu), r

    pts = [pos(t) for t in range(-400, 401, 2)]
    pts = [tela(x, y) for x, y, r in pts if r <= alcance * 1.15]
    meio = len(pts) // 2
    d.line(pts[:meio + 1], fill=(110, 90, 30), width=6)                               # chegando
    d.line(pts[meio:], fill=AMBAR, width=8)                                          # indo embora
    for dias, rotulo, lado in marcas:
        x, y, _ = pos(dias)
        px, py = tela(x, y)
        d.ellipse([px - 16, py - 16, px + 16, py + 16], fill=VERMELHO if dias else BRANCO)
        f = fonte('segoeuib.ttf', 40)
        w = d.textlength(rotulo, font=f)
        lx, ly = {'dir': (px + 30, py - 24), 'esq': (px - 30 - w, py - 24), 'baixo': (px - w / 2, py + 26)}[lado]
        d.text((min(max(lx, 70), LARG - 70 - w), ly), rotulo, font=f, fill=BRANCO)
    _rodape(d, fonte_dados)
    img.save(destino, quality=95)


def desenhar(spec, destino):
    """Grafico a partir do roteiro: {"tipo": "barras"|"linha_do_tempo"|"cartao"|"trajetoria"|"progresso"|"curva"|"bitmap", ...campos}."""
    s = dict(spec)
    tipo = s.pop('tipo')
    if tipo == 'linha_do_tempo':
        s['eventos'] = [tuple(ev) for ev in s['eventos']]
    {'barras': barras, 'linha_do_tempo': linha_do_tempo, 'cartao': cartao, 'trajetoria': trajetoria,
     'progresso': progresso, 'curva': curva, 'bitmap': bitmap, 'espectrograma': espectrograma, 'engrenagem': engrenagem}[tipo](
        destino=destino, **s)


def progresso(feito, total, titulo, rotulo_feito, rotulo_total, linhas, fonte_dados, destino):
    """Barra de quanto do caminho ja foi feito (ex.: anos-luz percorridos de um total), com a % real."""
    img = Image.new('RGB', (LARG, ALT), FUNDO)
    d = ImageDraw.Draw(img)
    centro(d, 110, titulo, fonte('impact.ttf', 92), BRANCO)
    pct = 100 * feito / total
    centro(d, 300, f'{pct:.1f}%'.replace('.', ','), fonte('impact.ttf', 200), AMBAR)
    x0, x1, y = 130, LARG - 130, 620
    d.rounded_rectangle([x0, y, x1, y + 70], 12, outline=CINZA, width=4)
    d.rounded_rectangle([x0, y, x0 + max(14, (x1 - x0) * feito / total), y + 70], 12, fill=AMBAR)
    f = fonte('segoeuib.ttf', 44)
    d.text((x0, y + 95), rotulo_feito, font=f, fill=AMBAR)
    d.text((x1 - d.textlength(rotulo_total, font=f), y + 95), rotulo_total, font=f, fill=BRANCO)
    for i, l in enumerate(linhas):
        centro(d, 860 + i * 100, l, fonte('segoeui.ttf', 48), (205, 205, 212))
    _rodape(d, fonte_dados)
    img.save(destino, quality=95)


def curva(pontos, titulo, subtitulo, eixo_x, eixo_y, marcas, fonte_dados, destino, y_min=None, y_max=None):
    """Linha (x, y) com marcas [(x, y, rotulo)] nos pontos que importam; dados reais, eixo legivel."""
    img = Image.new('RGB', (LARG, ALT), FUNDO)
    d = ImageDraw.Draw(img)
    centro(d, 110, titulo, fonte('impact.ttf', 92), BRANCO)
    centro(d, 230, subtitulo, fonte('segoeui.ttf', 42), CINZA)
    esq, dir_, topo, base = 190, LARG - 110, 420, 1040
    xs, ys = [p[0] for p in pontos], [p[1] for p in pontos]
    y_min = min(ys) if y_min is None else y_min
    y_max = max(ys) if y_max is None else y_max
    px = lambda x: esq + (dir_ - esq) * (x - min(xs)) / (max(xs) - min(xs))
    py = lambda y: base - (base - topo) * (y - y_min) / (y_max - y_min)
    for v in eixo_y:
        d.line([(esq, py(v)), (dir_, py(v))], fill=(40, 40, 48), width=2)
        t = f'{v}%'
        d.text((esq - 20 - d.textlength(t, font=fonte('segoeui.ttf', 40)), py(v) - 24), t, font=fonte('segoeui.ttf', 40), fill=CINZA)
    d.line([(px(x), py(y)) for x, y in pontos], fill=AMBAR, width=7)
    for x, y, rot in marcas:
        d.ellipse([px(x) - 14, py(y) - 14, px(x) + 14, py(y) + 14], fill=VERMELHO)
        f = fonte('segoeuib.ttf', 44)
        w = d.textlength(rot, font=f)
        d.text((min(max(px(x) - w / 2, 70), LARG - 70 - w), py(y) + 26), rot, font=f, fill=BRANCO)
    centro(d, base + 120, eixo_x, fonte('segoeui.ttf', 40), CINZA)
    _rodape(d, fonte_dados)
    img.save(destino, quality=95)


def bitmap(arquivo, titulo, linhas, fonte_dados, destino):
    """Desenha um bitmap pequeno (ex.: a mensagem de Arecibo, 23x73) ampliado em blocos, na cor de destaque."""
    pequeno = Image.open(arquivo).convert('L')
    w, h = pequeno.size
    img = Image.new('RGB', (LARG, ALT), FUNDO)
    d = ImageDraw.Draw(img)
    centro(d, 150, titulo, fonte('impact.ttf', 84), BRANCO)
    lado = min(520 / w, 860 / h)
    x0, y0 = 130, 290
    for y in range(h):
        for x in range(w):
            if pequeno.getpixel((x, y)) > 128:
                d.rectangle([x0 + x * lado, y0 + y * lado, x0 + (x + 1) * lado - 1, y0 + (y + 1) * lado - 1], fill=AMBAR)
    tx = x0 + w * lado + 50
    for i, l in enumerate(linhas):
        f = fonte('segoeuib.ttf' if i == 0 else 'segoeui.ttf', 48 if i == 0 else 42)
        d.text((tx, y0 + 20 + i * 90), l, font=f, fill=BRANCO if i == 0 else (205, 205, 212))
    _rodape(d, fonte_dados)
    img.save(destino, quality=95)


def espectrograma(arquivo, inicio, duracao, freq_max, fator, titulo, subtitulo, marca, fonte_dados, destino, topo=330):
    """Espectrograma proprio de um trecho de audio real. `fator` = quanto o arquivo foi acelerado (os eixos mostram
    a frequencia e o tempo reais: Hz do arquivo / fator, segundos do arquivo * fator)."""
    import subprocess
    import tempfile
    png = os.path.join(tempfile.gettempdir(), 'espectro_tmp.png')
    larg, alt = LARG - 260, min(720, 1080 - topo)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(inicio), '-t', str(duracao), '-i', arquivo, '-lavfi',
                    f'showspectrumpic=s={larg}x{alt}:legend=0:scale=log:color=fire:start=0:stop={freq_max}', png], check=True)
    img = Image.new('RGB', (LARG, ALT), FUNDO)
    d = ImageDraw.Draw(img)
    if titulo:
        centro(d, 110, titulo, fonte('impact.ttf', 92), BRANCO)
        centro(d, 230, subtitulo, fonte('segoeui.ttf', 42), CINZA)
    x0, y0 = 170, topo                                     # topo maior quando o gancho do video fica por cima
    img.paste(Image.open(png).convert('RGB'), (x0, y0))
    d.rectangle([x0, y0, x0 + larg, y0 + alt], outline=(60, 60, 70), width=3)
    f = fonte('segoeui.ttf', 40)
    for k in range(0, 5):                                  # eixo de frequencia real
        hz = freq_max / fator * k / 4
        y = y0 + alt - alt * k / 4
        t = f'{hz:.0f} Hz'
        d.text((x0 - 16 - d.textlength(t, font=f), y - 24), t, font=f, fill=CINZA)
    t = f'{duracao * fator:.0f} segundos de som real'
    centro(d, y0 + alt + 24, t, f, CINZA)
    centro(d, y0 + alt + 110, marca, fonte('segoeuib.ttf', 46), AMBAR)
    _rodape(d, fonte_dados)
    img.save(destino, quality=95)


def engrenagem(dentes, titulo, legenda, linhas, fonte_dados, destino):
    """Engrenagem desenhada com o numero real de dentes (ex.: 223 do mecanismo de Anticitera)."""
    img = Image.new('RGB', (LARG, ALT), FUNDO)
    d = ImageDraw.Draw(img)
    centro(d, 110, titulo, fonte('impact.ttf', 110), AMBAR)
    centro(d, 250, legenda, fonte('segoeuib.ttf', 50), BRANCO)
    cx, cy, r_ext, r_int = LARG / 2, 690, 330, 306
    pts = []
    for k in range(dentes):                           # cada dente: subida, topo, descida, vale
        a0 = 2 * math.pi * k / dentes
        passo = 2 * math.pi / dentes
        for frac, r in ((0.0, r_int), (0.2, r_ext), (0.5, r_ext), (0.7, r_int)):
            a = a0 + passo * frac
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=AMBAR)
    d.ellipse([cx - 285, cy - 285, cx + 285, cy + 285], fill=(150, 112, 20))
    for k in range(4):                                # raios, como na roda grande do mecanismo
        a = math.pi / 4 + k * math.pi / 2
        d.line([(cx, cy), (cx + 270 * math.cos(a), cy + 270 * math.sin(a))], fill=AMBAR, width=46)
    d.ellipse([cx - 235, cy - 235, cx + 235, cy + 235], outline=AMBAR, width=30)
    d.ellipse([cx - 60, cy - 60, cx + 60, cy + 60], fill=AMBAR)
    d.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=FUNDO)
    for i, l in enumerate(linhas):
        centro(d, 1060 + i * 70, l, fonte('segoeui.ttf', 44), (205, 205, 212))
    _rodape(d, fonte_dados)
    img.save(destino, quality=95)
