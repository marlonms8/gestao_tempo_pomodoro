#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestão de Tempo - Tkinter

- SQLite (projetos, matérias e logs)
- Exportação PDF (dia/semana) com reportlab (opcional)
- Dashboard com matplotlib (opcional)
- Agenda semanal com tkcalendar (opcional)
- Compatível com PyInstaller: banco .db fica na mesma pasta do .py/.exe
"""

import os
import sys
import sqlite3
import datetime as dt
from typing import Optional, List, Tuple

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ==============================
# Caminho do banco (PyInstaller-friendly)
# ==============================

def get_app_dir() -> str:
    """
    Retorna a pasta da aplicação:
    - Em script normal: pasta do arquivo .py
    - Em executável PyInstaller: pasta do .exe
    """
    if getattr(sys, "frozen", False):  # executável PyInstaller
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

APP_DIR = get_app_dir()
DB_FILE = os.path.join(APP_DIR, "pomodoro_study.db")

# ==============================
# Imports opcionais
# ==============================

# ==============================
# Som de alerta (alert.wav)
# ==============================
try:
    import winsound  # disponível no Windows
except ImportError:
    winsound = None


def play_alert_sound():
    """
    Toca o arquivo alert.wav na pasta da aplicação (APP_DIR).
    Se não encontrar ou der erro, usa o beep padrão (bell).
    """
    sound_path = os.path.join(APP_DIR, "alert.wav")

    # fallback: função para dar um "beep" simples
    def fallback_beep():
        root = tk._default_root
        if root is not None:
            try:
                root.bell()
            except Exception:
                pass

    if not os.path.exists(sound_path):
        fallback_beep()
        return

    try:
        if winsound is not None:
            winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            # Sem winsound (Linux/Mac) -> tenta bell
            fallback_beep()
    except Exception:
        fallback_beep()

try:
    from tkcalendar import Calendar
    TKCALENDAR_AVAILABLE = True
except Exception:
    TKCALENDAR_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False


# ==============================
# Camada de dados
# ==============================

class Database:
    def __init__(self, dbfile: str = DB_FILE) -> None:
        self.dbfile = dbfile
        self.conn = sqlite3.connect(self.dbfile, detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.create_tables()

    def create_tables(self) -> None:
        cur = self.conn.cursor()
        # projects
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
            """
        )
        # subjects
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS subjects (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name       TEXT NOT NULL,
                UNIQUE (project_id, name),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            """
        )
        # logs
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time   TEXT NOT NULL,
                duration   INTEGER NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            );
            """
        )
        self.conn.commit()

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    # ------------- projetos -------------
    def add_project(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Nome do projeto vazio.")
        cur = self.conn.cursor()
        cur.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (name,))
        self.conn.commit()
        cur.execute("SELECT id FROM projects WHERE name = ?", (name,))
        row = cur.fetchone()
        return row[0]

    def get_projects(self) -> List[Tuple[int, str]]:
        cur = self.conn.cursor()
        cur.execute("SELECT id, name FROM projects ORDER BY name")
        return cur.fetchall()

    def delete_project(self, project_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.conn.commit()

    # ------------- matérias -------------
    def add_subject(self, project_id: int, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Nome da matéria vazio.")
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO subjects (project_id, name) VALUES (?, ?)",
            (project_id, name),
        )
        self.conn.commit()
        cur.execute(
            "SELECT id FROM subjects WHERE project_id = ? AND name = ?",
            (project_id, name),
        )
        row = cur.fetchone()
        return row[0]

    def get_subjects(self, project_id: int) -> List[Tuple[int, str]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, name FROM subjects WHERE project_id = ? ORDER BY name",
            (project_id,),
        )
        return cur.fetchall()

    def delete_subject(self, subject_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
        self.conn.commit()

    # ------------- logs -------------
    def add_log(
        self,
        project_id: int,
        subject_id: int,
        start_iso: str,
        end_iso: str,
        duration_seconds: int,
    ) -> int:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO logs (project_id, subject_id, start_time, end_time, duration)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, subject_id, start_iso, end_iso, duration_seconds),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_logs_day(self, day_iso: str) -> List[Tuple]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT
                l.id,
                p.name AS project_name,
                s.name AS subject_name,
                l.start_time,
                l.end_time,
                l.duration
            FROM logs l
            LEFT JOIN projects p ON p.id = l.project_id
            LEFT JOIN subjects s ON s.id = l.subject_id
            WHERE DATE(l.start_time) = ?
            ORDER BY l.start_time
            """,
            (day_iso,),
        )
        return cur.fetchall()

    def get_logs_range(self, start_iso: str, end_iso: str) -> List[Tuple]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT
                l.id,
                p.name AS project_name,
                s.name AS subject_name,
                l.start_time,
                l.end_time,
                l.duration
            FROM logs l
            LEFT JOIN projects p ON p.id = l.project_id
            LEFT JOIN subjects s ON s.id = l.subject_id
            WHERE DATE(l.start_time) BETWEEN DATE(?) AND DATE(?)
            ORDER BY l.start_time
            """,
            (start_iso, end_iso),
        )
        return cur.fetchall()

    def summary_by_subject_day(self, day_iso: str) -> List[Tuple[str, int]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT s.name, SUM(l.duration) AS total_sec
            FROM logs l
            LEFT JOIN subjects s ON s.id = l.subject_id
            WHERE DATE(l.start_time) = ?
            GROUP BY s.name
            ORDER BY total_sec DESC
            """,
            (day_iso,),
        )
        return cur.fetchall()

    def summary_by_subject_range(
        self, start_iso: str, end_iso: str
    ) -> List[Tuple[str, int]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT s.name, SUM(l.duration) AS total_sec
            FROM logs l
            LEFT JOIN subjects s ON s.id = l.subject_id
            WHERE DATE(l.start_time) BETWEEN DATE(?) AND DATE(?)
            GROUP BY s.name
            ORDER BY total_sec DESC
            """,
            (start_iso, end_iso),
        )
        return cur.fetchall()

    def summary_by_day(self, start_iso: str, end_iso: str) -> List[Tuple[str, int]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT DATE(start_time) AS dia, SUM(duration) AS total_sec
            FROM logs
            WHERE DATE(start_time) BETWEEN DATE(?) AND DATE(?)
            GROUP BY DATE(start_time)
            ORDER BY DATE(start_time)
            """,
            (start_iso, end_iso),
        )
        return cur.fetchall()


# ==============================
# Janelas auxiliares
# ==============================

class ManagerWindow(tk.Toplevel):
    def __init__(self, master, db: Database, on_close=None):
        super().__init__(master)
        self.db = db
        self.on_close = on_close
        self.title("Projetos e Matérias")
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._handle_close)

        self._build_ui()
        self._load_projects()

    def _build_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)

        # Projetos
        proj_frame = ttk.LabelFrame(main, text="Projetos")
        proj_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 5))
        self.lb_projects = tk.Listbox(proj_frame, height=8, width=30)
        self.lb_projects.grid(row=0, column=0, columnspan=2, padx=5, pady=5)

        ttk.Label(proj_frame, text="Novo projeto:").grid(
            row=1, column=0, sticky="w", padx=5
        )
        self.ent_project = ttk.Entry(proj_frame, width=25)
        self.ent_project.grid(row=2, column=0, sticky="we", padx=5, pady=(0, 5))
        ttk.Button(proj_frame, text="Adicionar", command=self._add_project).grid(
            row=2, column=1, padx=5, pady=(0, 5)
        )
        ttk.Button(
            proj_frame, text="Excluir selecionado", command=self._delete_project
        ).grid(row=3, column=0, columnspan=2, padx=5, pady=(0, 5))

        # Matérias
        subj_frame = ttk.LabelFrame(main, text="Matérias do projeto selecionado")
        subj_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=(0, 5))
        self.lb_subjects = tk.Listbox(subj_frame, height=8, width=30)
        self.lb_subjects.grid(row=0, column=0, columnspan=2, padx=5, pady=5)

        ttk.Label(subj_frame, text="Nova matéria:").grid(
            row=1, column=0, sticky="w", padx=5
        )
        self.ent_subject = ttk.Entry(subj_frame, width=25)
        self.ent_subject.grid(row=2, column=0, sticky="we", padx=5, pady=(0, 5))
        ttk.Button(subj_frame, text="Adicionar", command=self._add_subject).grid(
            row=2, column=1, padx=5, pady=(0, 5)
        )
        ttk.Button(
            subj_frame, text="Excluir selecionada", command=self._delete_subject
        ).grid(row=3, column=0, columnspan=2, padx=5, pady=(0, 5))

        self.lb_projects.bind("<<ListboxSelect>>", lambda e: self._load_subjects())

    def _handle_close(self):
        if self.on_close:
            self.on_close()
        self.destroy()

    def _load_projects(self):
        self.lb_projects.delete(0, tk.END)
        for pid, name in self.db.get_projects():
            self.lb_projects.insert(tk.END, f"{name} (id={pid})")
        self._load_subjects()

    def _get_selected_project_id(self) -> Optional[int]:
        sel = self.lb_projects.curselection()
        if not sel:
            return None
        text = self.lb_projects.get(sel[0])
        if "(id=" in text:
            try:
                pid = int(text.split("(id=")[1].split(")")[0])
                return pid
            except Exception:
                return None
        return None

    def _get_selected_subject_id(self) -> Optional[int]:
        sel = self.lb_subjects.curselection()
        if not sel:
            return None
        text = self.lb_subjects.get(sel[0])
        if "(id=" in text:
            try:
                sid = int(text.split("(id=")[1].split(")")[0])
                return sid
            except Exception:
                return None
        return None

    def _load_subjects(self):
        self.lb_subjects.delete(0, tk.END)
        project_id = self._get_selected_project_id()
        if project_id is None:
            return
        for sid, name in self.db.get_subjects(project_id):
            self.lb_subjects.insert(tk.END, f"{name} (id={sid})")

    def _add_project(self):
        name = self.ent_project.get().strip()
        if not name:
            messagebox.showwarning("Aviso", "Informe um nome de projeto.")
            return
        try:
            self.db.add_project(name)
            self.ent_project.delete(0, tk.END)
            self._load_projects()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível adicionar o projeto:\n{e}")

    def _delete_project(self):
        project_id = self._get_selected_project_id()
        if project_id is None:
            messagebox.showwarning("Aviso", "Selecione um projeto.")
            return
        if messagebox.askyesno(
            "Confirmar", "Excluir o projeto selecionado (e suas matérias/logs)?"
        ):
            self.db.delete_project(project_id)
            self._load_projects()

    def _add_subject(self):
        project_id = self._get_selected_project_id()
        if project_id is None:
            messagebox.showwarning(
                "Aviso", "Selecione um projeto antes de adicionar a matéria."
            )
            return
        name = self.ent_subject.get().strip()
        if not name:
            messagebox.showwarning("Aviso", "Informe o nome da matéria.")
            return
        try:
            self.db.add_subject(project_id, name)
            self.ent_subject.delete(0, tk.END)
            self._load_subjects()
        except Exception as e:
            messagebox.showerror(
                "Erro", f"Não foi possível adicionar a matéria:\n{e}"
            )

    def _delete_subject(self):
        subject_id = self._get_selected_subject_id()
        if subject_id is None:
            messagebox.showwarning("Aviso", "Selecione uma matéria.")
            return
        if messagebox.f(
            "Confirmar", "Excluir a matéria selecionada (e seus logs)?"
        ):
            self.db.delete_subject(subject_id)
            self._load_subjects()


class DailyDetailsWindow(tk.Toplevel):
    def __init__(self, master, db: Database, day_iso: str):
        super().__init__(master)
        self.db = db
        self.day_iso = day_iso
        self.title(f"Detalhes do dia {day_iso}")
        self.resizable(True, True)
        self.grab_set()
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)

        cols = ("id", "projeto", "matéria", "início", "fim", "duração_min")
        self.tv = ttk.Treeview(main, columns=cols, show="headings")
        for col in cols:
            self.tv.heading(col, text=col.capitalize())
        self.tv.column("id", width=40, anchor="e")
        self.tv.column("projeto", width=120)
        self.tv.column("matéria", width=120)
        self.tv.column("início", width=130)
        self.tv.column("fim", width=130)
        self.tv.column("duração_min", width=90, anchor="e")
        self.tv.pack(fill="both", expand=True)

    def _load_data(self):
        for it in self.tv.get_children():
            self.tv.delete(it)
        logs = self.db.get_logs_day(self.day_iso)
        for log in logs:
            lid, proj, subj, start_iso, end_iso, dur_sec = log
            mins = int(round(dur_sec / 60))
            self.tv.insert(
                "",
                "end",
                values=(lid, proj or "-", subj or "-", start_iso, end_iso, mins)
            )


class WeekAgendaWindow(tk.Toplevel):
    def __init__(self, master, db: Database):
        super().__init__(master)
        self.db = db
        self.title("Agenda Semanal")
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)

        if not TKCALENDAR_AVAILABLE:
            ttk.Label(
                main,
                text="tkcalendar não encontrado.\nInstale com: pip install tkcalendar",
                foreground="red",
            ).pack()
            return

        today = dt.date.today()

        self.cal = Calendar(
            main,
            selectmode="day",
            year=today.year,
            month=today.month,
            day=today.day,
            date_pattern="yyyy-mm-dd",
        )
        self.cal.grid(row=0, column=0, columnspan=2, pady=(0, 10))

        ttk.Label(main, text="Selecione uma data. A semana (seg-dom) será usada:").grid(
            row=1, column=0, columnspan=2, pady=(0, 5)
        )

        ttk.Button(main, text="Ver Dashboard semana", command=self._open_dashboard).grid(
            row=2, column=0, padx=5, pady=5
        )
        ttk.Button(main, text="Exportar PDF semana", command=self._export_pdf_week).grid(
            row=2, column=1, padx=5, pady=5
        )

    def _get_week_range(self) -> Tuple[str, str]:
        selected = self.cal.get_date()  # yyyy-mm-dd
        day = dt.datetime.strptime(selected, "%Y-%m-%d").date()
        start = day - dt.timedelta(days=day.weekday())  # segunda
        end = start + dt.timedelta(days=6)
        return start.isoformat(), end.isoformat()

    def _open_dashboard(self):
        start_iso, end_iso = self._get_week_range()
        DashboardWindow(self, self.db, start_iso, end_iso)

    def _export_pdf_week(self):
        start_iso, end_iso = self._get_week_range()
        export_week_pdf(self, self.db, start_iso, end_iso)


class DashboardWindow(tk.Toplevel):
    def __init__(self, master, db: Database, start_iso: str, end_iso: str):
        super().__init__(master)
        self.db = db
        self.start_iso = start_iso
        self.end_iso = end_iso

        self.title(f"Dashboard {start_iso} até {end_iso}")
        self.resizable(True, True)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)

        if not MATPLOTLIB_AVAILABLE:
            ttk.Label(
                main,
                text="matplotlib não encontrado.\nInstale com: pip install matplotlib",
                foreground="red",
            ).pack()
            return

        # Notebook com 2 abas: por matéria e por dia
        nb = ttk.Notebook(main)
        nb.pack(fill="both", expand=True)

        frame_subj = ttk.Frame(nb)
        frame_day = ttk.Frame(nb)
        nb.add(frame_subj, text="Por matéria")
        nb.add(frame_day, text="Por dia")

        # Dados
        subj_data = self.db.summary_by_subject_range(
            self.start_iso, self.end_iso
        )  # (nome, total_sec)
        day_data = self.db.summary_by_day(self.start_iso, self.end_iso)  # (dia, total_sec)

        # Gráfico por matéria
        if subj_data:
            fig1 = Figure(figsize=(6, 4))
            ax1 = fig1.add_subplot(111)
            labels = [name if len(name) <= 20 else name[:17] + "..." for name, _ in subj_data]
            mins = [sec / 60 for _, sec in subj_data]
            ax1.bar(labels, mins)
            ax1.set_ylabel("Minutos")
            ax1.set_title("Tempo por matéria")
            ax1.tick_params(axis="x", rotation=45)
            fig1.tight_layout()

            canvas1 = FigureCanvasTkAgg(fig1, master=frame_subj)
            canvas1.draw()
            canvas1.get_tk_widget().pack(fill="both", expand=True)
        else:
            ttk.Label(frame_subj, text="Sem registros no período.").pack(pady=20)

        # Gráfico por dia
        if day_data:
            fig2 = Figure(figsize=(6, 4))
            ax2 = fig2.add_subplot(111)
            labels = [dia for dia, _ in day_data]
            mins = [sec / 60 for _, sec in day_data]
            ax2.plot(labels, mins, marker="o")
            ax2.set_ylabel("Minutos")
            ax2.set_title("Tempo por dia")
            ax2.tick_params(axis="x", rotation=45)
            fig2.tight_layout()

            canvas2 = FigureCanvasTkAgg(fig2, master=frame_day)
            canvas2.draw()
            canvas2.get_tk_widget().pack(fill="both", expand=True)
        else:
            ttk.Label(frame_day, text="Sem registros no período.").pack(pady=20)


# ==============================
# Exportações PDF
# ==============================

def export_day_pdf(parent, db: Database, day_iso: str) -> None:
    if not REPORTLAB_AVAILABLE:
        messagebox.showwarning(
            "ReportLab",
            "Biblioteca reportlab não encontrada.\nInstale com: pip install reportlab",
            parent=parent,
        )
        return

    logs = db.get_logs_day(day_iso)
    if not logs:
        messagebox.showinfo(
            "Sem dados", "Não há registros para este dia.", parent=parent
        )
        return

    filename = filedialog.asksaveasfilename(
        parent=parent,
        title="Salvar PDF do dia",
        defaultextension=".pdf",
        filetypes=[("PDF", "*.pdf")],
        initialfile=f"gestao_tempo_{day_iso}.pdf",
    )
    if not filename:
        return

    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()
    elems = []

    elems.append(Paragraph(f"Relatório Gestão de Tempo - Dia {day_iso}", styles["Title"]))
    elems.append(Spacer(1, 12))

    # Tabela com logs
    data = [["ID", "Projeto", "Matéria", "Início", "Fim", "Duração (min)"]]
    total_sec = 0
    for lid, proj, subj, start_iso, end_iso, dur_sec in logs:
        total_sec += dur_sec
        mins = int(round(dur_sec / 60))
        data.append(
            [
                str(lid),
                proj or "-",
                subj or "-",
                start_iso,
                end_iso,
                str(mins),
            ]
        )

    tbl = Table(data, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elems.append(tbl)
    elems.append(Spacer(1, 12))

    total_min = int(round(total_sec / 60))
    elems.append(Paragraph(f"Total de minutos no dia: {total_min}", styles["Normal"]))

    doc.build(elems)
    messagebox.showinfo("PDF", "PDF gerado com sucesso!", parent=parent)


def export_week_pdf(parent, db: Database, start_iso: str, end_iso: str) -> None:
    if not REPORTLAB_AVAILABLE:
        messagebox.showwarning(
            "ReportLab",
            "Biblioteca reportlab não encontrada.\nInstale com: pip install reportlab",
            parent=parent,
        )
        return

    subj_data = db.summary_by_subject_range(start_iso, end_iso)
    day_data = db.summary_by_day(start_iso, end_iso)
    if not subj_data and not day_data:
        messagebox.showinfo(
            "Sem dados", "Não há registros neste período.", parent=parent
        )
        return

    filename = filedialog.asksaveasfilename(
        parent=parent,
        title="Salvar PDF da semana",
        defaultextension=".pdf",
        filetypes=[("PDF", "*.pdf")],
        initialfile=f"gestao_tempo_{start_iso}_a_{end_iso}.pdf",
    )
    if not filename:
        return

    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()
    elems = []

    elems.append(
        Paragraph(
            f"Relatório Gestão de Tempo - Período {start_iso} até {end_iso}",
            styles["Title"],
        )
    )
    elems.append(Spacer(1, 12))

    total_semana_sec = 0

    # Por matéria
    if subj_data:
        elems.append(Paragraph("Resumo por matéria", styles["Heading2"]))
        data = [["Matéria", "Total (min)"]]
        for name, sec in subj_data:
            total_semana_sec += sec
            data.append([name, str(int(round(sec / 60)))])
        tbl = Table(data, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]
            )
        )
        elems.append(tbl)
        elems.append(Spacer(1, 12))

    # Por dia
    if day_data:
        elems.append(Paragraph("Resumo por dia", styles["Heading2"]))
        data = [["Dia", "Total (min)"]]
        for dia, sec in day_data:
            data.append([dia, str(int(round(sec / 60)))])
        tbl = Table(data, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]
            )
        )
        elems.append(tbl)
        elems.append(Spacer(1, 12))

    total_semana_min = int(round(total_semana_sec / 60))
    elems.append(
        Paragraph(f"Total de minutos no período: {total_semana_min}", styles["Normal"])
    )

    doc.build(elems)
    messagebox.showinfo("PDF", "PDF gerado com sucesso!", parent=parent)


def export_week_pdf_from_calendar(parent, db: Database, day_iso: str) -> None:
    """Mantém compatibilidade com uso direto de um dia (calcula semana)."""
    day = dt.datetime.strptime(day_iso, "%Y-%m-%d").date()
    start = day - dt.timedelta(days=day.weekday())
    end = start + dt.timedelta(days=6)
    export_week_pdf(parent, db, start.isoformat(), end.isoformat())


# ==============================
# Aplicação principal
# ==============================

class PomodoroApp(tk.Tk):  # nome da classe mantido, mas a UI é "Gestão de Tempo"
    def __init__(self, db: Database):
        super().__init__()
        self.db = db

        self.title("Gestão de Tempo")
        self.resizable(False, False)

        # Timer
        self.work_minutes = tk.IntVar(value=25)
        self.short_break_minutes = tk.IntVar(value=5)
        self.long_break_minutes = tk.IntVar(value=15)
        self.cycles_for_long_break = tk.IntVar(value=4)

        self.session = "Idle"  # "Work", "ShortBreak", "LongBreak"
        self.remaining = self.work_minutes.get() * 60
        self.completed_cycles = 0

        self.current_start: Optional[dt.datetime] = None
        self.current_project_id: Optional[int] = None
        self.current_subject_id: Optional[int] = None

        self.is_running = False
        self.after_id = None

        self._build_ui()
        self._load_projects()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI ----------
    def _build_ui(self):
        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)

        # Linha 1: seleção projeto/matéria
        proj_frame = ttk.Frame(main)
        proj_frame.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, 10))
        proj_frame.columnconfigure(1, weight=1)
        proj_frame.columnconfigure(3, weight=1)

        ttk.Label(proj_frame, text="Projeto:").grid(row=0, column=0, sticky="w")
        self.cb_project = ttk.Combobox(proj_frame, state="readonly")
        self.cb_project.grid(row=0, column=1, sticky="we", padx=(0, 10))
        self.cb_project.bind("<<ComboboxSelected>>", lambda e: self._load_subjects())

        ttk.Label(proj_frame, text="Matéria:").grid(row=0, column=2, sticky="w")
        self.cb_subject = ttk.Combobox(proj_frame, state="readonly")
        self.cb_subject.grid(row=0, column=3, sticky="we")

        ttk.Button(
            proj_frame,
            text="Gerenciar...",
            command=self._open_manager,
            width=12,
        ).grid(row=0, column=4, padx=(10, 0))

        # Linha 2: configurações de sessões
        config_frame = ttk.LabelFrame(main, text="Configuração de sessões")
        config_frame.grid(row=1, column=0, columnspan=2, sticky="we", pady=(0, 10))
        for i in range(8):
            config_frame.columnconfigure(i, weight=1)

        ttk.Label(config_frame, text="Trabalho (min):").grid(row=0, column=0, sticky="e")
        ttk.Spinbox(
            config_frame,
            from_=1,
            to=120,
            textvariable=self.work_minutes,
            width=5,
        ).grid(row=0, column=1, sticky="w", padx=(0, 10))

        ttk.Label(config_frame, text="Pausa curta (min):").grid(
            row=0, column=2, sticky="e"
        )
        ttk.Spinbox(
            config_frame,
            from_=1,
            to=60,
            textvariable=self.short_break_minutes,
            width=5,
        ).grid(row=0, column=3, sticky="w", padx=(0, 10))

        ttk.Label(config_frame, text="Pausa longa (min):").grid(
            row=0, column=4, sticky="e"
        )
        ttk.Spinbox(
            config_frame,
            from_=1,
            to=60,
            textvariable=self.long_break_minutes,
            width=5,
        ).grid(row=0, column=5, sticky="w", padx=(0, 10))

        ttk.Label(config_frame, text="Ciclos p/ pausa longa:").grid(
            row=0, column=6, sticky="e"
        )
        ttk.Spinbox(
            config_frame,
            from_=1,
            to=10,
            textvariable=self.cycles_for_long_break,
            width=5,
        ).grid(row=0, column=7, sticky="w")

        # Linha 3: timer
        timer_frame = ttk.Frame(main)
        timer_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))

        self.time_label = ttk.Label(
            timer_frame,
            text=self._format_time(self.remaining),
            font=("Helvetica", 32, "bold"),
        )
        self.time_label.pack()

        self.session_label = ttk.Label(timer_frame, text="Sessão: Idle")
        self.session_label.pack()

        # Linha 4: botões
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=3, column=0, columnspan=2, sticky="we", pady=(0, 10))

        self.btn_start = ttk.Button(btn_frame, text="Iniciar", command=self.start)
        self.btn_start.grid(row=0, column=0, padx=5)

        self.btn_pause = ttk.Button(
            btn_frame, text="Pausar", command=self.pause, state="disabled"
        )
        self.btn_pause.grid(row=0, column=1, padx=5)

        self.btn_reset = ttk.Button(btn_frame, text="Resetar", command=self.reset_timer)
        self.btn_reset.grid(row=0, column=2, padx=5)

        ttk.Button(
            btn_frame,
            text="Agenda semanal",
            command=self._open_week_agenda,
        ).grid(row=0, column=3, padx=5)

        ttk.Button(
            btn_frame,
            text="Dashboard período",
            command=self._open_range_dashboard,
        ).grid(row=0, column=4, padx=5)

        ttk.Button(
            btn_frame,
            text="PDF dia de hoje",
            command=self._export_today_pdf,
        ).grid(row=0, column=5, padx=5)

        # Linha 5: lista simples do dia
        logs_frame = ttk.LabelFrame(main, text="Resumo do dia atual")
        logs_frame.grid(row=4, column=0, columnspan=2, sticky="nsew")

        cols = ("id", "projeto", "matéria", "início", "fim", "duração_min")
        self.tv_today = ttk.Treeview(logs_frame, columns=cols, show="headings", height=8)
        for col in cols:
            self.tv_today.heading(col, text=col.capitalize())
        self.tv_today.column("id", width=40, anchor="e")
        self.tv_today.column("projeto", width=120)
        self.tv_today.column("matéria", width=120)
        self.tv_today.column("início", width=120)
        self.tv_today.column("fim", width=120)
        self.tv_today.column("duração_min", width=90, anchor="e")
        self.tv_today.grid(row=0, column=0, sticky="nsew")

        logs_frame.rowconfigure(0, weight=1)
        logs_frame.columnconfigure(0, weight=1)

        self.tv_today.bind("<Double-1>", lambda e: self._open_today_details())

        self._refresh_today_logs()

    # ---------- Utilidades ----------
    @staticmethod
    def _format_time(seconds: int) -> str:
        m, s = divmod(seconds, 60)
        return f"{m:02d}:{s:02d}"

    def _load_projects(self):
        projects = self.db.get_projects()
        if not projects:
            # garante pelo menos um projeto/matéria padrão
            pid = self.db.add_project("Default")
            self.db.add_subject(pid, "Geral")
            projects = self.db.get_projects()

        self._projects = {name: pid for pid, name in projects}
        self.cb_project["values"] = list(self._projects.keys())
        if projects:
            self.cb_project.current(0)
            self._load_subjects()

    def _load_subjects(self):
        name = self.cb_project.get()
        project_id = self._projects.get(name)
        self.current_project_id = project_id
        if project_id is None:
            self.cb_subject["values"] = []
            self.current_subject_id = None
            return
        subjects = self.db.get_subjects(project_id)
        self._subjects = {name: sid for sid, name in subjects}
        self.cb_subject["values"] = list(self._subjects.keys())
        if subjects:
            self.cb_subject.current(0)
            self.current_subject_id = subjects[0][0]
        else:
            self.current_subject_id = None

    def _open_manager(self):
        ManagerWindow(self, self.db, on_close=self._load_projects)

    def _open_today_details(self):
        today_iso = dt.date.today().isoformat()
        DailyDetailsWindow(self, self.db, today_iso)

    def _open_week_agenda(self):
        WeekAgendaWindow(self, self.db)

    def _ask_range(self) -> Optional[Tuple[str, str]]:
        """Pergunta data inicial/final em um simples diálogo."""
        top = tk.Toplevel(self)
        top.title("Período")
        top.resizable(False, False)
        top.grab_set()

        ttk.Label(top, text="Data inicial (YYYY-MM-DD):").grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 0)
        )
        ent_start = ttk.Entry(top, width=12)
        ent_start.grid(row=0, column=1, padx=10, pady=(10, 0))
        ent_start.insert(0, dt.date.today().isoformat())

        ttk.Label(top, text="Data final (YYYY-MM-DD):").grid(
            row=1, column=0, sticky="w", padx=10
        )
        ent_end = ttk.Entry(top, width=12)
        ent_end.grid(row=1, column=1, padx=10, pady=(0, 10))
        ent_end.insert(0, dt.date.today().isoformat())

        result: dict = {"range": None}

        def ok():
            s = ent_start.get().strip()
            e = ent_end.get().strip()
            try:
                d1 = dt.datetime.strptime(s, "%Y-%m-%d").date()
                d2 = dt.datetime.strptime(e, "%Y-%m-%d").date()
            except ValueError:
                messagebox.showwarning(
                    "Formato inválido",
                    "Use o formato YYYY-MM-DD.",
                    parent=top,
                )
                return
            if d1 > d2:
                messagebox.showwarning(
                    "Período inválido",
                    "Data inicial não pode ser maior que a final.",
                    parent=top,
                )
                return
            result["range"] = (d1.isoformat(), d2.isoformat())
            top.destroy()

        def cancelar():
            result["range"] = None
            top.destroy()

        btn_frame = ttk.Frame(top)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btn_frame, text="OK", command=ok).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=cancelar).grid(
            row=0, column=1, padx=5
        )

        top.wait_window()
        return result["range"]

    def _open_range_dashboard(self):
        r = self._ask_range()
        if not r:
            return
        start_iso, end_iso = r
        DashboardWindow(self, self.db, start_iso, end_iso)

    def _export_today_pdf(self):
        today_iso = dt.date.today().isoformat()
        export_day_pdf(self, self.db, today_iso)

    def _refresh_today_logs(self):
        for it in self.tv_today.get_children():
            self.tv_today.delete(it)
        today_iso = dt.date.today().isoformat()
        logs = self.db.get_logs_day(today_iso)
        for log in logs:
            lid, proj, subj, start_iso, end_iso, dur_sec = log
            mins = int(round(dur_sec / 60))
            self.tv_today.insert(
                "",
                "end",
                values=(lid, proj or "-", subj or "-", start_iso, end_iso, mins),
            )

    # ---------- Timer ----------
    def _update_session_label(self):
        self.session_label.config(
            text=f"Sessão: {self.session} | Ciclos concluídos: {self.completed_cycles}"
        )

    def start(self):
        if self.is_running:
            return

        # precisa de projeto/matéria
        project_name = self.cb_project.get()
        subject_name = self.cb_subject.get()
        if not project_name or not subject_name:
            messagebox.showwarning(
                "Seleção necessária",
                "Selecione um projeto e uma matéria antes de iniciar.",
                parent=self,
            )
            return

        self.current_project_id = self._projects.get(project_name)
        self.current_subject_id = self._subjects.get(subject_name)

        if self.session == "Idle":
            # inicia nova sessão de trabalho
            self.session = "Work"
            self.remaining = self.work_minutes.get() * 60
            self.completed_cycles = 0

        self.current_start = dt.datetime.now()
        self.is_running = True
        self.btn_pause.config(state="normal")
        self._update_session_label()
        self._tick()

    def _tick(self):
        if not self.is_running:
            return
        if self.remaining <= 0:
            self._finish_session()
            return
        self.remaining -= 1
        self.time_label.config(text=self._format_time(self.remaining))
        self.after_id = self.after(1000, self._tick)

    def _alert_next_session(self, title: str, message: str) -> bool:
        """
        Traz a janela para frente, toca o som de alerta e mostra o diálogo
        perguntando se deve iniciar a próxima sessão.
        Retorna True se o usuário clicar em 'Sim', False caso contrário.
        """
        # Garante que a janela apareça na frente de tudo
        try:
            self.deiconify()          # caso esteja minimizada
        except Exception:
            pass

        try:
            self.lift()
            self.attributes("-topmost", True)
            self.update_idletasks()
        except Exception:
            pass

        # Toca o som de alerta
        play_alert_sound()

        # Mostra o diálogo
        try:
            result = messagebox.askyesno(title, message, parent=self)
        finally:
            # Remove o topmost para não atrapalhar depois
            try:
                self.attributes("-topmost", False)
                self.focus_force()
            except Exception:
                pass

        return result


    def _finish_session(self):
        self.is_running = False
        self.btn_pause.config(state="disabled")

        end_time = dt.datetime.now()
        if self.current_start and self.session == "Work":
            duration = int((end_time - self.current_start).total_seconds())
            if duration > 0 and self.current_project_id and self.current_subject_id:
                self.db.add_log(
                    self.current_project_id,
                    self.current_subject_id,
                    self.current_start.isoformat(timespec="seconds"),
                    end_time.isoformat(timespec="seconds"),
                    duration,
                )
        self.current_start = None
        self._refresh_today_logs()

        # Decide próxima sessão
        if self.session == "Work":
            self.completed_cycles += 1
            if self.completed_cycles >= self.cycles_for_long_break.get():
                self.session = "LongBreak"
                self.remaining = self.long_break_minutes.get() * 60
                self.completed_cycles = 0
            else:
                self.session = "ShortBreak"
                self.remaining = self.short_break_minutes.get() * 60
        else:
            self.session = "Work"
            self.remaining = self.work_minutes.get() * 60

        self._update_session_label()
        self.time_label.config(text=self._format_time(self.remaining))

        # pergunta se quer iniciar automaticamente a próxima sessão
        if self._alert_next_session(
            "Próxima sessão",
            f"Sessão {self.session} pronta.\nDeseja iniciar agora?",
        ):
            self.start()

    def pause(self):
        if not self.is_running:
            return
        self.is_running = False
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None

        end_time = dt.datetime.now()
        if self.current_start and self.session == "Work":
            # registra log parcial
            duration = int((end_time - self.current_start).total_seconds())
            if duration > 0 and self.current_project_id and self.current_subject_id:
                self.db.add_log(
                    self.current_project_id,
                    self.current_subject_id,
                    self.current_start.isoformat(timespec="seconds"),
                    end_time.isoformat(timespec="seconds"),
                    duration,
                )
        self.current_start = None
        self._refresh_today_logs()
        self.btn_pause.config(state="disabled")

    def reset_timer(self):
        self.is_running = False
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        self.session = "Idle"
        self.completed_cycles = 0
        self.remaining = self.work_minutes.get() * 60
        self.current_start = None
        self.time_label.config(text=self._format_time(self.remaining))
        self._update_session_label()
        self.btn_pause.config(state="disabled")

    def _on_close(self):
        if self.is_running and not messagebox.askyesno(
            "Sair",
            "Um timer está em andamento. Tem certeza de que deseja sair?",
            parent=self,
        ):
            return
        self.db.close()
        self.destroy()


# ==============================
# main
# ==============================

def main():
    db = Database(DB_FILE)
    # garante pelo menos um projeto/matéria
    if not db.get_projects():
        pid = db.add_project("Default")
        db.add_subject(pid, "Geral")

    app = PomodoroApp(db)
    app.mainloop()


if __name__ == "__main__":
    main()
