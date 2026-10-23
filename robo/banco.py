"""Historico do robo em SQLite (robo/robo.db): execucoes, etapas, temas usados, chamadas de IA, midias e postagens.
Tambem a trava que impede dois ciclos ao mesmo tempo."""
import json
import os
import sqlite3
from datetime import datetime

AQUI = os.path.join(os.environ['ROBO_DADOS'], 'robo') if os.environ.get('ROBO_DADOS') else os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(AQUI, 'robo.db')
TRAVA = os.path.join(AQUI, 'robo.lock')

ESQUEMA = """
create table if not exists execucoes (
  id integer primary key, canal text not null, inicio text not null, fim text,
  estado text not null,            -- rodando | aguardando_aprovacao | aprovado | postado | falhou | precisa_roteiro
  tema text, slug text, pasta text, erro text);
create table if not exists etapas (
  execucao integer not null, etapa text not null, estado text not null, saida text, erro text, em text,
  primary key (execucao, etapa));
create table if not exists temas (
  canal text not null, chave text not null, titulo text, execucao integer, em text, primary key (canal, chave));
create table if not exists chamadas_ia (
  id integer primary key, em text, execucao integer, tarefa text, provedor text, modelo text,
  tokens_entrada integer, tokens_saida integer, custo_usd real, cache integer, ok integer, nota text);
create table if not exists cache (chave text primary key, valor text, em text);
create table if not exists midias (execucao integer, arquivo text, autor text, licenca text, url text);
create table if not exists postagens (execucao integer, onde text, link text, em text);
"""


def agora():
    return datetime.now().isoformat(timespec='seconds')


def conectar():
    c = sqlite3.connect(ARQ)
    c.row_factory = sqlite3.Row
    c.executescript(ESQUEMA)
    return c


# ---------- trava: um ciclo por vez ----------
def _vivo(pid):
    import ctypes
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    codigo = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(codigo))
    ctypes.windll.kernel32.CloseHandle(h)
    return codigo.value == 259  # STILL_ACTIVE


def travar():
    if os.path.exists(TRAVA):
        try:
            pid = int(open(TRAVA).read().strip() or 0)
        except ValueError:
            pid = 0
        if pid and pid != os.getpid() and _vivo(pid):
            raise RuntimeError(f'outro ciclo do robo ja esta rodando (processo {pid})')
    open(TRAVA, 'w').write(str(os.getpid()))


def destravar():
    try:
        os.remove(TRAVA)
    except FileNotFoundError:
        pass


# ---------- etapas (retomada) ----------
def etapa_feita(c, ex, nome):
    r = c.execute('select saida from etapas where execucao=? and etapa=? and estado="ok"', (ex, nome)).fetchone()
    return json.loads(r['saida']) if r and r['saida'] else (True if r else None)


def marcar_etapa(c, ex, nome, estado, saida=None, erro=None):
    c.execute('insert or replace into etapas values (?,?,?,?,?,?)',
              (ex, nome, estado, json.dumps(saida, ensure_ascii=False) if saida is not None else None, erro, agora()))
    c.commit()


# ---------- cache ----------
def cache_ler(c, chave):
    r = c.execute('select valor from cache where chave=?', (chave,)).fetchone()
    return r['valor'] if r else None


def cache_gravar(c, chave, valor):
    c.execute('insert or replace into cache values (?,?,?)', (chave, valor, agora()))
    c.commit()
