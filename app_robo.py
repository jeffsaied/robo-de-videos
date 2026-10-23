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

VERSAO = '1.0.1'
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
def janela():
    import tkinter as tk
    from tkinter import messagebox, ttk

    raiz = tk.Tk()
    raiz.title(f'Robô de Vídeos {VERSAO}')
    pos = os.path.join(DADOS, 'robo', 'janela.txt')   # abre onde foi fechada da ultima vez
    try:
        raiz.geometry(open(pos).read().strip())
    except (OSError, tk.TclError):
        raiz.geometry('720x520')

    def fechar():
        try:
            open(pos, 'w').write(raiz.geometry())
        except OSError:
            pass
        raiz.destroy()
    raiz.protocol('WM_DELETE_WINDOW', fechar)
    canais = sorted(d for d in os.listdir(os.path.join(DADOS, 'canais'))
                    if os.path.exists(os.path.join(DADOS, 'canais', d, 'canal.json')))
    topo = ttk.Frame(raiz, padding=8)
    topo.pack(fill='x')
    ttk.Label(topo, text='Canal:').pack(side='left')
    canal = ttk.Combobox(topo, values=canais, state='readonly', width=22)
    canal.set('casos-curiosos' if 'casos-curiosos' in canais else (canais[0] if canais else ''))
    canal.pack(side='left', padx=4)
    ttk.Label(topo, text='Hora:').pack(side='left', padx=(12, 0))
    hora = ttk.Entry(topo, width=6)
    hora.insert(0, '09:00')
    hora.pack(side='left', padx=4)

    botoes = ttk.Frame(raiz, padding=(8, 0))
    botoes.pack(fill='x')
    caixa = tk.Text(raiz, height=20, wrap='word', font=('Consolas', 9))
    caixa.pack(fill='both', expand=True, padx=8, pady=8)
    status = ttk.Label(raiz, text='', padding=(8, 0, 8, 8))
    status.pack(fill='x')

    def escreve(t):
        raiz.after(0, lambda: (caixa.insert('end', t), caixa.see('end')))

    def avisa(t):
        raiz.after(0, lambda: status.config(text=t))

    def produzir():
        b_prod.config(state='disabled')
        cmd = [sys.executable, '--produzir', '--canal', canal.get()] if CONGELADO else \
            [sys.executable, '-m', 'robo', 'produzir', '--canal', canal.get()]

        def roda():
            escreve(f'--- produzindo para {canal.get()} ---\n')
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                 errors='replace', cwd=DADOS, creationflags=SEM_JANELA)
            for linha in p.stdout:
                escreve(linha)
            escreve(f'--- fim (código {p.wait()}) ---\n')
            raiz.after(0, lambda: b_prod.config(state='normal'))
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
                instalar(url, avisa)
            except Exception as e:
                avisa(f'Não deu para atualizar: {e}')
        threading.Thread(target=roda, daemon=True).start()

    b_prod = ttk.Button(botoes, text='Produzir vídeo agora', command=produzir)
    b_prod.pack(side='left')
    ttk.Button(botoes, text='Abrir fila', command=abrir_fila).pack(side='left', padx=4)
    ttk.Button(botoes, text='Agendar todo dia', command=agendar).pack(side='left')
    ttk.Button(botoes, text='Atualizar', command=atualizar).pack(side='right')
    ttk.Button(botoes, text='Pasta de dados', command=lambda: os.startfile(DADOS)).pack(side='right', padx=4)

    faltas = [n for n in ('ffmpeg', 'ffprobe') if not shutil.which(n)]
    if faltas:
        escreve('Falta o ffmpeg. Instale com:  winget install Gyan.FFmpeg  e abra o app de novo.\n')
    escreve(f'Dados em: {DADOS}\nO robô produz e deixa na fila; quem posta é você (legenda e hashtags vão junto).\n')

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
