r"""App do Robo de Videos (vira RoboDeVideos.exe): produz o video, mostra a fila, agenda 1 por dia e se atualiza pelo GitHub.

    RoboDeVideos.exe                          abre a janela
    RoboDeVideos.exe --produzir [--canal x]   o que o Agendador do Windows roda
    RoboDeVideos.exe --fabrica <canal> <id>   uso interno do robo (montagem do video)

Os dados (canais, banco, fila, .env) ficam em Documentos\Robo de Videos; o .exe pode ser trocado sem perder nada."""
import os
import shutil
import subprocess
import sys
import threading

VERSAO = '1.3.0'
REPO = 'jeffsaied/robo-de-videos'
CONGELADO = getattr(sys, 'frozen', False)
SEM_JANELA = 0x08000000   # CREATE_NO_WINDOW

if CONGELADO:
    DADOS = os.path.join(os.path.expanduser('~'), 'Documents', 'Robo de Videos')
    os.environ['ROBO_DADOS'] = DADOS
else:
    DADOS = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')


def semear():
    """Na 1a vez (e quando uma versao nova traz canal novo) copia os perfis que vem dentro do .exe, sem sobrescrever."""
    origem = os.path.join(sys._MEIPASS, 'semente')
    for raiz, _, arqs in os.walk(origem):
        for a in arqs:
            destino = os.path.join(DADOS, os.path.relpath(os.path.join(raiz, a), origem))
            if not os.path.exists(destino):
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                shutil.copy2(os.path.join(raiz, a), destino)


def sem_janelas():
    """O .exe nao tem console: sem isto cada ffmpeg/claude abriria uma janela preta."""
    original = subprocess.Popen.__init__

    def novo(self, *a, **k):
        k['creationflags'] = k.get('creationflags', 0) | SEM_JANELA
        original(self, *a, **k)
    subprocess.Popen.__init__ = novo
    for f in (sys.stdout, sys.stderr):
        if f is not None and hasattr(f, 'reconfigure'):
            f.reconfigure(encoding='utf-8', errors='replace')
    if sys.stdout is None:   # rodando pelo Agendador: a saida vai para o log
        os.makedirs(os.path.join(DADOS, 'robo'), exist_ok=True)
        sys.stdout = sys.stderr = open(os.path.join(DADOS, 'robo', 'app.log'), 'a', encoding='utf-8', buffering=1)


def trabalho(a):
    if CONGELADO:
        sys.path.insert(0, sys._MEIPASS)
    if a[0] == '--fabrica':
        import fabrica_tiktok
        fabrica_tiktok.gerar(a[1], a[2])
    else:
        from robo.__main__ import main
        main(['produzir'] + a[1:])


# ---------- atualizacao pelo GitHub ----------
def _versao(t):
    return tuple(int(x) for x in t.lstrip('vV').split('.') if x.isdigit())


def ultima_versao():
    import requests
    j = requests.get(f'https://api.github.com/repos/{REPO}/releases/latest', timeout=15,
                     headers={'Accept': 'application/vnd.github+json'}).json()
    url = next((x['browser_download_url'] for x in j.get('assets', []) if x['name'].lower().endswith('.exe')), None)
    return j.get('tag_name', '0'), url


def instalar(url, aviso):
    """Baixa o .exe novo ao lado, troca pelo atual (Windows deixa renomear o .exe em uso) e reabre."""
    import requests
    exe = sys.executable
    novo, velho = exe + '.novo', exe + '.old'
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total, feito = int(r.headers.get('content-length', 0)), 0
        with open(novo, 'wb') as f:
            for bloco in r.iter_content(1 << 20):
                f.write(bloco)
                feito += len(bloco)
                if total:
                    aviso(f'Baixando... {feito * 100 // total}%')
    if os.path.exists(velho):
        os.remove(velho)
    os.rename(exe, velho)
    os.rename(novo, exe)
    subprocess.Popen([exe])
    os._exit(0)


# ---------- janela ----------
TEMAS = {   # escuro = preto puro; claro = papel
    'escuro': dict(fundo='#000000', painel='#0b0b0b', borda='#1c1c1c', texto='#ededed', fraco='#7d7d7d',
                   destaque='#f5a623', sobre_destaque='#000000', erro='#ff5c5c', ok='#4cd27a', campo='#111111'),
    'claro': dict(fundo='#f4f4f1', painel='#ffffff', borda='#dcdcd6', texto='#151515', fraco='#6b6b6b',
                  destaque='#c97a00', sobre_destaque='#ffffff', erro='#c62828', ok='#1e8e3e', campo='#ffffff'),
}


def _barra_escura(raiz, escura):
    """Barra de titulo do Windows no mesmo tema (DWMWA_USE_IMMERSIVE_DARK_MODE)."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(raiz.winfo_id())
        v = ctypes.c_int(1 if escura else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), 4)
        w, h = raiz.winfo_width(), raiz.winfo_height()   # o Windows so redesenha a barra quando o tamanho muda
        raiz.geometry(f'{w + 1}x{h}')
        raiz.after(30, lambda: raiz.geometry(f'{w}x{h}'))
    except Exception:
        pass


def janela():
    import tkinter as tk
    from tkinter import messagebox, ttk

    pref = os.path.join(DADOS, 'robo', 'janela.txt')   # posicao + tema da ultima vez
    salvo = {}
    try:
        texto = open(pref, encoding='utf-8').read()
        salvo = dict(l.strip().split('=', 1) for l in texto.splitlines() if '=' in l) or {'geometria': texto.strip()}
    except OSError:
        pass
    tema = [salvo.get('tema', 'escuro')]

    raiz = tk.Tk()
    raiz.title('Robô de Vídeos')
    raiz.minsize(760, 520)
    try:
        raiz.geometry(salvo.get('geometria') or '860x600')
    except tk.TclError:
        raiz.geometry('860x600')
    estilo = ttk.Style(raiz)
    estilo.theme_use('clam')
    F = ('Segoe UI', 10)
    pintar = []   # (widget, {opcao: chave_da_cor})

    def p(w, **cores):
        pintar.append((w, cores))
        return w

    def salvar():
        try:
            os.makedirs(os.path.dirname(pref), exist_ok=True)
            open(pref, 'w', encoding='utf-8').write(f'geometria={raiz.geometry()}\ntema={tema[0]}\nhora={hora.get()}\n')
        except OSError:
            pass

    def fechar():
        salvar()
        raiz.destroy()
    raiz.protocol('WM_DELETE_WINDOW', fechar)

    canais = sorted(d for d in os.listdir(os.path.join(DADOS, 'canais'))
                    if os.path.exists(os.path.join(DADOS, 'canais', d, 'canal.json')))

    # topo
    topo = p(tk.Frame(raiz, padx=22, pady=16), bg='fundo')
    topo.pack(fill='x')
    p(tk.Label(topo, text='Robô de Vídeos', font=('Segoe UI Semibold', 18)), bg='fundo', fg='texto').pack(side='left')
    p(tk.Label(topo, text=f'  v{VERSAO}', font=F), bg='fundo', fg='fraco').pack(side='left', pady=(8, 0))
    b_tema = p(tk.Button(topo, font=F, relief='flat', bd=0, padx=12, pady=4, cursor='hand2'),
               bg='painel', fg='texto', activebackground='borda', activeforeground='texto')
    b_tema.pack(side='right')

    # campos
    cartao = p(tk.Frame(raiz, padx=18, pady=14, highlightthickness=1), bg='painel', highlightbackground='borda')
    cartao.pack(fill='x', padx=22)
    for col, titulo in enumerate(('CANAL', 'QUANTOS VÍDEOS', 'HORA DO AGENDAMENTO')):
        p(tk.Label(cartao, text=titulo, font=('Segoe UI', 8, 'bold')), bg='painel', fg='fraco').grid(
            row=0, column=col, sticky='w', padx=(0, 22))
    canal = ttk.Combobox(cartao, values=canais, state='readonly', width=24, font=F)
    canal.set('casos-curiosos' if 'casos-curiosos' in canais else (canais[0] if canais else ''))
    canal.grid(row=1, column=0, sticky='w', padx=(0, 22), pady=(4, 0))
    qtd = ttk.Spinbox(cartao, from_=1, to=100, width=6, font=F)
    qtd.set(1)
    qtd.grid(row=1, column=1, sticky='w', padx=(0, 22), pady=(4, 0))
    hora = ttk.Entry(cartao, width=8, font=F)
    hora.insert(0, salvo.get('hora', '09:00'))
    hora.grid(row=1, column=2, sticky='w', pady=(4, 0))

    # botoes
    barra = p(tk.Frame(raiz, padx=22, pady=14), bg='fundo')
    barra.pack(fill='x')

    def botao(texto, cmd, principal=False, lado='left'):
        if principal:
            b = p(tk.Button(barra, text=texto, command=cmd, font=('Segoe UI Semibold', 10), relief='flat', bd=0,
                            padx=18, pady=7, cursor='hand2'),
                  bg='destaque', fg='sobre_destaque', activebackground='destaque', activeforeground='sobre_destaque')
        else:
            b = p(tk.Button(barra, text=texto, command=cmd, font=F, relief='flat', bd=0, padx=14, pady=7,
                            cursor='hand2', highlightthickness=1),
                  bg='painel', fg='texto', activebackground='borda', activeforeground='texto', highlightbackground='borda')
        b.pack(side=lado, padx=(0, 8) if lado == 'left' else (8, 0))
        return b

    # registro
    moldura = p(tk.Frame(raiz, highlightthickness=1), bg='painel', highlightbackground='borda')
    moldura.pack(fill='both', expand=True, padx=22)
    caixa = p(tk.Text(moldura, wrap='word', font=('Consolas', 10), relief='flat', bd=0, padx=14, pady=12),
              bg='painel', fg='texto', insertbackground='texto', selectbackground='borda')
    caixa.pack(fill='both', expand=True)
    status = p(tk.Label(raiz, text='Pronto.', font=F, anchor='w', padx=22, pady=10), bg='fundo', fg='fraco')
    status.pack(fill='x')

    def aplicar_tema():
        c = TEMAS[tema[0]]
        raiz.configure(bg=c['fundo'])
        for w, cores in pintar:
            w.configure(**{k: c[v] for k, v in cores.items()})
        caixa.tag_configure('erro', foreground=c['erro'])
        caixa.tag_configure('ok', foreground=c['ok'])
        caixa.tag_configure('fraco', foreground=c['fraco'])
        for nome in ('TCombobox', 'TSpinbox', 'TEntry'):
            estilo.configure(nome, fieldbackground=c['campo'], background=c['painel'], foreground=c['texto'],
                             bordercolor=c['borda'], lightcolor=c['borda'], darkcolor=c['borda'],
                             arrowcolor=c['texto'], insertcolor=c['texto'], padding=4)
            estilo.map(nome, fieldbackground=[('readonly', c['campo'])], foreground=[('readonly', c['texto'])],
                       selectbackground=[('readonly', c['campo'])], selectforeground=[('readonly', c['texto'])])
        raiz.option_add('*TCombobox*Listbox.background', c['campo'])
        raiz.option_add('*TCombobox*Listbox.foreground', c['texto'])
        raiz.option_add('*TCombobox*Listbox.selectBackground', c['destaque'])
        raiz.option_add('*TCombobox*Listbox.selectForeground', c['sobre_destaque'])
        b_tema.configure(text='☀  Claro' if tema[0] == 'escuro' else '●  Escuro')
        raiz.after(80, lambda: _barra_escura(raiz, tema[0] == 'escuro'))

    def trocar_tema():
        tema[0] = 'claro' if tema[0] == 'escuro' else 'escuro'
        aplicar_tema()
    b_tema.configure(command=trocar_tema)

    def escreve(t):
        etiqueta = 'erro' if ('FALHOU' in t or 'Traceback' in t or 'Falta' in t) else \
            'ok' if ('na fila para' in t or 'problemas: nenhum' in t) else 'fraco' if t.startswith('---') else ()
        raiz.after(0, lambda: (caixa.insert('end', t, etiqueta), caixa.see('end')))

    def avisa(t):
        raiz.after(0, lambda: status.config(text=t))

    rodando = {'p': None, 'parar': False}

    def produzir():
        if rodando['p']:   # enquanto produz, o botao vira "Parar"
            rodando['parar'] = True
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(rodando['p'].pid)], capture_output=True,
                           creationflags=SEM_JANELA)
            return
        try:
            n = max(1, int(qtd.get()))
        except ValueError:
            n = 1
        cn = canal.get()
        rodando['parar'] = False
        b_prod.config(text='■  Parar')

        def roda():
            feitos = 0
            for i in range(n):
                if rodando['parar']:
                    break
                avisa(f'Produzindo vídeo {i + 1} de {n} para {cn}...')
                escreve(f'--- vídeo {i + 1} de {n} · {cn} ---\n')
                cmd = [sys.executable, '--produzir', '--canal', cn] if CONGELADO else \
                    [sys.executable, '-m', 'robo', 'produzir', '--canal', cn]
                rodando['p'] = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                                encoding='utf-8', errors='replace', cwd=DADOS, creationflags=SEM_JANELA)
                for linha in rodando['p'].stdout:
                    escreve(linha)
                codigo = rodando['p'].wait()
                rodando['p'] = None
                if codigo != 0:
                    escreve('--- parou ---\n')
                    break
                feitos += 1
            avisa('Parado.' if rodando['parar'] else f'{feitos} de {n} vídeo(s) prontos na fila.')
            raiz.after(0, lambda: b_prod.config(text='▶  Produzir'))
        threading.Thread(target=roda, daemon=True).start()

    def abrir_fila():
        pasta = os.path.join(DADOS, 'robo', 'fila')
        os.makedirs(pasta, exist_ok=True)
        os.startfile(pasta)

    def agendar():
        exe = sys.executable
        args = f'--produzir --canal {canal.get()}' if CONGELADO else f'-m robo produzir --canal {canal.get()}'
        ps = (f"$a = New-ScheduledTaskAction -Execute '{exe}' -Argument '{args}' -WorkingDirectory '{DADOS}';"
              f"$t = New-ScheduledTaskTrigger -Daily -At '{hora.get()}';"
              "$s = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew;"
              f"Register-ScheduledTask -TaskName 'Robo de Videos - {canal.get()}' -Action $a -Trigger $t -Settings $s -Force | Out-Null")
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, creationflags=SEM_JANELA)
        if r.returncode == 0:
            messagebox.showinfo('Agendado', f'Todo dia às {hora.get()} sai um vídeo de {canal.get()} na fila.')
        else:
            messagebox.showerror('Erro ao agendar', r.stderr[-500:])

    def atualizar():
        if not CONGELADO:
            messagebox.showinfo('Atualizar', 'Só o .exe se atualiza; aqui é o código-fonte.')
            return

        def roda():
            try:
                avisa('Procurando versão nova no GitHub...')
                tag, url = ultima_versao()
                if _versao(tag) <= _versao(VERSAO) or not url:
                    avisa(f'Você já está na versão mais nova ({VERSAO}).')
                    return
                avisa(f'Baixando a versão {tag}...')
                raiz.after(0, salvar)
                instalar(url, avisa)
            except Exception as e:
                avisa(f'Não deu para atualizar: {e}')
        threading.Thread(target=roda, daemon=True).start()

    b_prod = botao('▶  Produzir', produzir, principal=True)
    botao('Abrir fila', abrir_fila)
    botao('Agendar todo dia', agendar)
    botao('Atualizar', atualizar, lado='right')
    botao('Pasta de dados', lambda: os.startfile(DADOS), lado='right')

    aplicar_tema()
    if not (shutil.which('ffmpeg') and shutil.which('ffprobe')):
        escreve('Falta o ffmpeg. Instale com:  winget install Gyan.FFmpeg  e abra o app de novo.\n')
    escreve(f'--- dados em {DADOS} ---\n')
    escreve('O robô produz e deixa na fila com legenda e hashtags; quem posta é você.\n')

    def checa():
        try:
            tag, url = ultima_versao()
            if url and _versao(tag) > _versao(VERSAO):
                avisa(f'Versão {tag} disponível: clique em Atualizar.')
        except Exception:
            pass
    if CONGELADO:
        threading.Thread(target=checa, daemon=True).start()
    raiz.mainloop()


if __name__ == '__main__':
    if CONGELADO:
        semear()
        try:
            os.remove(sys.executable + '.old')
        except OSError:
            pass
    if len(sys.argv) > 1 and sys.argv[1] in ('--fabrica', '--produzir'):
        sem_janelas()
        try:
            trabalho(sys.argv[1:])
        except Exception:   # sem isto o .exe sem console abre uma caixa de erro e fica parado esperando clique
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        janela()
