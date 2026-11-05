"""Tareas Recurrentes: aplicación local y portable para Windows."""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QSettings, QTime, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QCalendarWidget, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QMenu, QPlainTextEdit, QProgressBar, QScrollArea, QSpinBox, QStackedWidget, QSystemTrayIcon, QTimeEdit,
    QVBoxLayout, QWidget,
)

APP_NAME = "Tareas Recurrentes"
WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
CATEGORIES = ["General", "Idea", "Comida", "Trabajo", "Deporte", "Música"]
CATEGORY_ICONS = {"General": "✓", "Idea": "💡", "Comida": "☕", "Trabajo": "▣", "Deporte": "⚽", "Música": "♫"}
THEMES = {
    "Violeta / Lavanda": ("#9e62e6", "#f0e2fa", "#7548a9", "#e9d9f8"),
    "Celeste": ("#4aabd4", "#dff4fb", "#287b9d", "#d7f0fa"),
    "León": ("#9b1b30", "#f5dfb3", "#7b1828", "#f5e2bd"),
    "Serpiente": ("#087a52", "#e3e8e5", "#525d5a", "#d8e2dd"),
    "Cuervo": ("#0b4f8a", "#e7d5c0", "#7a4d29", "#d9e7f3"),
    "Tejón": ("#151515", "#f4d06a", "#8a6508", "#f5e7b4"),
}


def app_data_dir() -> Path:
    """Mantiene la base junto al .exe para que la aplicación sea portable."""
    root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    folder = root / "data"
    folder.mkdir(exist_ok=True)
    return folder


class Database:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(app_data_dir() / "tareas.db")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
              id INTEGER PRIMARY KEY, title TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
              weekdays TEXT NOT NULL DEFAULT '', interval_days INTEGER NOT NULL DEFAULT 0,
              start_date TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS completions (
              task_id INTEGER NOT NULL, day TEXT NOT NULL, completed_at TEXT NOT NULL,
              PRIMARY KEY (task_id, day), FOREIGN KEY(task_id) REFERENCES tasks(id)
            );
            CREATE TABLE IF NOT EXISTS pomodoro_sessions (
              id INTEGER PRIMARY KEY, title TEXT NOT NULL, task_title TEXT NOT NULL DEFAULT '',
              work_minutes INTEGER NOT NULL, break_minutes INTEGER NOT NULL, cycles INTEGER NOT NULL,
              completed_at TEXT NOT NULL
            );
        """)
        # Migración segura de las instalaciones creadas antes de estas funciones.
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(tasks)")}
        for name, definition in {
            "category": "TEXT NOT NULL DEFAULT 'General'", "description": "TEXT NOT NULL DEFAULT ''",
            "start_time": "TEXT NOT NULL DEFAULT ''", "end_time": "TEXT NOT NULL DEFAULT ''",
            "one_time": "INTEGER NOT NULL DEFAULT 0", "end_date": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if name not in columns:
                self.conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")
        self.conn.commit()

    def tasks_for(self, target: date):
        rows = self.conn.execute("""
            SELECT * FROM tasks WHERE active = 1
            ORDER BY CASE WHEN start_time = '' THEN 1 ELSE 0 END, start_time, title COLLATE NOCASE
        """).fetchall()
        result = []
        for row in rows:
            start = date.fromisoformat(row["start_date"])
            if target < start:
                continue
            if row["end_date"] and target > date.fromisoformat(row["end_date"]):
                continue
            weekly = str(target.weekday()) in row["weekdays"].split(",")
            interval = row["interval_days"]
            periodic = interval > 0 and (target - start).days % interval == 0
            if weekly or periodic:
                result.append(row)
        return result

    def completed(self, task_id: int, target: date) -> bool:
        return self.conn.execute("SELECT 1 FROM completions WHERE task_id=? AND day=?", (task_id, target.isoformat())).fetchone() is not None

    def set_completed(self, task_id: int, target: date, value: bool) -> None:
        if value:
            self.conn.execute("INSERT OR REPLACE INTO completions VALUES (?, ?, ?)", (task_id, target.isoformat(), datetime.now().isoformat(timespec="seconds")))
        else:
            self.conn.execute("DELETE FROM completions WHERE task_id=? AND day=?", (task_id, target.isoformat()))
        self.conn.commit()

    def save_task(self, title: str, description: str, category: str, start_time: str, end_time: str, end_date: str, weekdays: list[int], interval: int, start: date, task_id: int | None = None) -> None:
        values = (title.strip(), description.strip(), category, start_time, end_time, end_date, ",".join(map(str, weekdays)), interval, start.isoformat())
        if task_id is None:
            self.conn.execute("INSERT INTO tasks(title, description, category, start_time, end_time, end_date, weekdays, interval_days, start_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (*values, datetime.now().isoformat(timespec="seconds")))
        else:
            self.conn.execute("UPDATE tasks SET title=?, description=?, category=?, start_time=?, end_time=?, end_date=?, weekdays=?, interval_days=?, start_date=? WHERE id=?", (*values, task_id))
        self.conn.commit()

    def archive(self, task_id: int) -> None:
        self.conn.execute("UPDATE tasks SET active=0 WHERE id=?", (task_id,))
        self.conn.commit()

    def history(self, days: int = 14):
        return self.conn.execute("""
            SELECT c.day, t.title, c.completed_at FROM completions c
            JOIN tasks t ON t.id = c.task_id
            WHERE c.day >= ? ORDER BY c.day DESC, t.title COLLATE NOCASE
        """, ((date.today() - timedelta(days=days - 1)).isoformat(),)).fetchall()

    def category_counts(self):
        return dict(self.conn.execute("SELECT category, COUNT(*) FROM tasks WHERE active=1 GROUP BY category"))

    def pomodoro_count_today(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM pomodoro_sessions WHERE date(completed_at)=?", (date.today().isoformat(),)).fetchone()[0]

    def record_pomodoro(self, title: str, task_title: str, work: int, rest: int, cycles: int) -> None:
        self.conn.execute("INSERT INTO pomodoro_sessions(title,task_title,work_minutes,break_minutes,cycles,completed_at) VALUES (?,?,?,?,?,?)", (title, task_title, work, rest, cycles, datetime.now().isoformat(timespec="seconds")))
        self.conn.commit()


class TaskDialog(QDialog):
    def __init__(self, parent=None, task=None, category=None):
        super().__init__(parent)
        self.setWindowTitle("Nueva tarea" if task is None else "Editar tarea")
        self.setMinimumWidth(390)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit(task["title"] if task else "")
        self.category = QComboBox()
        for category in CATEGORIES:
            self.category.addItem(f"{CATEGORY_ICONS[category]}  {category}", category)
        selected_category = task["category"] if task else (category or "General")
        self.category.setCurrentIndex(self.category.findData(selected_category))
        self.description = QPlainTextEdit(task["description"] if task else ""); self.description.setPlaceholderText("Describe brevemente la tarea (opcional)"); self.description.setFixedHeight(62)
        self.start = QDateEdit()
        self.start.setCalendarPopup(True)
        initial = datetime.strptime(task["start_date"], "%Y-%m-%d").date() if task else date.today()
        self.start.setDate(QDate(initial.year, initial.month, initial.day))
        self.interval = QSpinBox(); self.interval.setRange(0, 3650); self.interval.setSuffix(" días (0 = no usar)")
        self.interval.setValue(task["interval_days"] if task else 0)
        self.has_end_date = QCheckBox("Finaliza el:")
        self.has_end_date.setChecked(bool(task and task["end_date"]))
        self.end_date = QDateEdit(); self.end_date.setCalendarPopup(True)
        end = date.fromisoformat(task["end_date"]) if task and task["end_date"] else initial
        self.end_date.setDate(QDate(end.year, end.month, end.day))
        self.has_time = QCheckBox("Definir horario")
        self.has_time.setChecked(bool(task and task["start_time"]))
        self.start_time = QTimeEdit(); self.start_time.setDisplayFormat("HH:mm"); self.start_time.setTime(QTime.fromString(task["start_time"], "HH:mm") if task and task["start_time"] else QTime(9, 0))
        self.end_time = QTimeEdit(); self.end_time.setDisplayFormat("HH:mm"); self.end_time.setTime(QTime.fromString(task["end_time"], "HH:mm") if task and task["end_time"] else QTime(10, 0))
        self.has_time.toggled.connect(self.start_time.setEnabled); self.has_time.toggled.connect(self.end_time.setEnabled)
        self.start_time.setEnabled(self.has_time.isChecked()); self.end_time.setEnabled(self.has_time.isChecked())
        form.addRow("Tarea:", self.title)
        form.addRow("Categoría:", self.category)
        form.addRow("Descripción:", self.description)
        form.addRow("Desde:", self.start)
        form.addRow("Horario:", self.has_time)
        times = QHBoxLayout(); times.addWidget(self.start_time); times.addWidget(QLabel("a")); times.addWidget(self.end_time); form.addRow("", times)
        end_row = QHBoxLayout(); end_row.addWidget(self.has_end_date); end_row.addWidget(self.end_date); form.addRow("Repetición:", end_row)
        form.addRow("Repetir cada:", self.interval)
        layout.addLayout(form)
        layout.addWidget(QLabel("Días de la semana (puedes combinar con la periodicidad):"))
        days = QHBoxLayout(); self.day_boxes = []
        chosen = task["weekdays"].split(",") if task else []
        for i, name in enumerate(WEEKDAYS):
            box = QCheckBox(name); box.setChecked(str(i) in chosen); self.day_boxes.append(box); days.addWidget(box)
        layout.addLayout(days)
        self.has_end_date.toggled.connect(self.end_date.setEnabled)
        self.end_date.setEnabled(self.has_end_date.isChecked())
        note = QLabel("Puedes limitar la repetición con una fecha de término.")
        note.setStyleSheet("color:#657080;")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate(self):
        if not self.title.text().strip():
            QMessageBox.warning(self, APP_NAME, "Escribe un nombre para la tarea."); return
        if not any(b.isChecked() for b in self.day_boxes) and self.interval.value() == 0:
            QMessageBox.warning(self, APP_NAME, "Elige un día de la semana o una periodicidad."); return
        if self.has_end_date.isChecked() and self.end_date.date() < self.start.date():
            QMessageBox.warning(self, APP_NAME, "La fecha de término debe ser igual o posterior a la fecha de inicio."); return
        self.accept()

    def values(self):
        start_time = self.start_time.time().toString("HH:mm") if self.has_time.isChecked() else ""
        end_time = self.end_time.time().toString("HH:mm") if self.has_time.isChecked() else ""
        end_date = self.end_date.date().toString("yyyy-MM-dd") if self.has_end_date.isChecked() else ""
        return (self.title.text(), self.description.toPlainText(), self.category.currentData(), start_time, end_time,
                end_date, [i for i, b in enumerate(self.day_boxes) if b.isChecked()], self.interval.value(), self.start.date().toPython())


class CategoryDialog(QDialog):
    """Pantalla de selección de actividad, equivalente a la segunda vista del mockup."""
    def __init__(self, db, parent=None):
        super().__init__(parent); self.selected_category = None
        self.setWindowTitle("Crear tarea"); self.resize(460, 560)
        layout = QVBoxLayout(self); layout.setContentsMargins(30, 26, 30, 26); layout.setSpacing(14)
        heading = QLabel("Elige una actividad"); heading.setStyleSheet("font-size:25px; font-weight:800; color:#1f1a24;"); layout.addWidget(heading)
        hint = QLabel("La categoría ayuda a ordenar y reconocer tus tareas."); hint.setStyleSheet("color:#7548a9;"); layout.addWidget(hint)
        counts = db.category_counts()
        for category in CATEGORIES:
            button = QPushButton(f"{CATEGORY_ICONS[category]}    {category}\n       {counts.get(category, 0)} tarea(s)")
            button.setMinimumHeight(68); button.setStyleSheet("QPushButton { text-align:left; font-size:16px; color:#4d2779; background:#f0e2fa; border-radius:12px; padding:12px; } QPushButton:hover { background:#dfc3f5; }")
            button.clicked.connect(lambda _, value=category: self.select_category(value)); layout.addWidget(button)
        layout.addStretch()
        cancel = QPushButton("Cancelar"); cancel.clicked.connect(self.reject); layout.addWidget(cancel)

    def select_category(self, category):
        self.selected_category = category; self.accept()


class PomodoroDialog(QDialog):
    """Temporizador local configurable, asociado opcionalmente a una tarea."""
    def __init__(self, db, parent=None):
        super().__init__(parent); self.db = db; self.setWindowTitle("Pomodoro"); self.setMinimumWidth(390)
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.remaining = 0; self.cycle = 1; self.breaking = False; self.title_for_session = ""
        layout = QVBoxLayout(self); layout.setSpacing(12)
        title = QLabel("Pomodoro"); title.setStyleSheet("font-size:27px;font-weight:800;"); layout.addWidget(title)
        layout.addWidget(QLabel("Tarea guardada (opcional)")); self.task = QComboBox(); self.task.addItem("Sin tarea asociada", "")
        for task in db.conn.execute("SELECT id,title FROM tasks WHERE active=1 ORDER BY title COLLATE NOCASE"):
            self.task.addItem(task["title"], task["title"])
        layout.addWidget(self.task)
        self.custom_title = QLineEdit(); self.custom_title.setPlaceholderText("O escribe un nombre"); layout.addWidget(self.custom_title)
        settings = QFormLayout(); self.work = QSpinBox(); self.work.setRange(1, 180); self.work.setValue(25); self.work.setSuffix(" min")
        self.rest = QSpinBox(); self.rest.setRange(1, 90); self.rest.setValue(5); self.rest.setSuffix(" min")
        self.cycles = QSpinBox(); self.cycles.setRange(1, 12); self.cycles.setValue(4)
        settings.addRow("Trabajo:", self.work); settings.addRow("Descanso:", self.rest); settings.addRow("Ciclos:", self.cycles); layout.addLayout(settings)
        self.label = QLabel("Listo para comenzar"); self.label.setAlignment(Qt.AlignCenter); self.label.setStyleSheet("font-size:22px;font-weight:800;"); layout.addWidget(self.label)
        self.progress = QProgressBar(); self.progress.setTextVisible(False); layout.addWidget(self.progress)
        self.start_button = QPushButton("Iniciar Pomodoro"); self.start_button.setObjectName("primaryButton"); self.start_button.clicked.connect(self.start); layout.addWidget(self.start_button)
        close = QPushButton("Cerrar"); close.clicked.connect(self.reject); layout.addWidget(close)

    def session_name(self):
        return self.title_for_session or self.custom_title.text().strip() or self.task.currentData() or f"Ciclo Pomodoro {self.db.pomodoro_count_today() + 1}"

    def start(self):
        self.cycle = 1; self.breaking = False; self.title_for_session = self.custom_title.text().strip() or self.task.currentData() or f"Ciclo Pomodoro {self.db.pomodoro_count_today() + 1}"; self.begin_phase()

    def begin_phase(self):
        minutes = self.rest.value() if self.breaking else self.work.value(); self.remaining = minutes * 60
        self.progress.setRange(0, self.remaining); self.progress.setValue(self.remaining)
        phase = "Descanso" if self.breaking else self.session_name()
        self.label.setText(f"{phase} · ciclo {self.cycle}/{self.cycles.value()}"); self.start_button.setText("En curso…")
        self.timer.start(1000)

    def tick(self):
        self.remaining -= 1; self.progress.setValue(max(0, self.remaining))
        mins, secs = divmod(max(0, self.remaining), 60); self.start_button.setText(f"{mins:02d}:{secs:02d}")
        if self.remaining > 0: return
        self.timer.stop()
        if not self.breaking:
            self.parent().notify("Pomodoro", f"Terminaste: {self.session_name()}.")
            if self.cycle >= self.cycles.value():
                self.db.record_pomodoro(self.session_name(), self.task.currentData(), self.work.value(), self.rest.value(), self.cycles.value())
                self.label.setText("¡Pomodoro completado!"); self.start_button.setText("Iniciar nuevamente"); return
            self.breaking = True; self.begin_phase(); return
        self.breaking = False; self.cycle += 1; self.parent().notify("Pomodoro", "Descanso terminado. Comienza el siguiente ciclo."); self.begin_phase()

    def reject(self):
        self.timer.stop(); super().reject()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database(); self.current_day = date.today(); self.settings = QSettings("Tareitas", "Tareitas")
        self.theme_name = self.settings.value("theme", "Violeta / Lavanda"); self.dark_mode = self.settings.value("dark", False, type=bool)
        self.notification_minutes = self.settings.value("notification_minutes", 120, type=int)
        self.setWindowTitle(APP_NAME); self.resize(540, 840); self.setMinimumSize(500, 760)
        self.build_ui(); self.setup_tray(); self.apply_theme(); self.refresh()
        self.timer = QTimer(self); self.timer.timeout.connect(self.check_pending); self.schedule_notifications()

    def build_ui(self):
        self.pages = QStackedWidget(); self.setCentralWidget(self.pages)
        self.pages.addWidget(self.build_home_page())
        self.pages.addWidget(self.build_categories_page())
        self.pages.addWidget(self.build_form_page())
        self.pages.addWidget(self.build_calendar_page())
        self.setStyleSheet("""
          QMainWindow { background:#e9d9f8; color:#1f1a24; }
          QLabel#heading { color:#ffffff; font-size:29px; font-weight:800; }
          QLabel#subheading { color:#f7efff; font-weight:500; }
          QLabel#date { color:#ffffff; font-size:18px; font-weight:700; }
          QLabel#summary { color:#6f3fc0; background:#ffffff; border-radius:10px; padding:10px 14px; font-weight:800; }
          QPushButton { border:0; border-radius:9px; padding:9px 13px; font-weight:700; color:#1f1a24; background:#efe1fa; }
          QPushButton:hover { background:#e1c8f5; }
          QPushButton#primaryButton { color:#ffffff; background:#9e62e6; border:1px solid #ffffff; padding:10px 16px; }
          QPushButton#primaryButton:hover { background:#8447d2; }
          QPushButton#secondaryButton { color:#7d47c9; background:#ffffff; }
          QPushButton#secondaryButton:hover { background:#f7efff; }
          QPushButton#navButton { color:#7140b5; background:#ffffff; font-size:20px; padding:5px; }
          QPushButton#navButton:hover { background:#efe1fa; }
          QPushButton#todayButton { color:#ffffff; background:#8f51dc; }
          QPushButton#todayButton:hover { background:#7d40c7; }
          QPushButton#fab { color:#ffffff; background:#9e62e6; font-size:30px; min-width:58px; min-height:58px; border-radius:16px; padding:0; }
          QPushButton#fab:hover { background:#8447d2; }
          QCheckBox { color:#1f1a24; font-size:15px; font-weight:650; }
          QCheckBox::indicator { width:20px; height:20px; border:2px solid #aa74e7; border-radius:6px; background:#ffffff; }
          QCheckBox::indicator:checked { background:#9e62e6; border-color:#9e62e6; }
          QFrame#card { background:#f0e2fa; border:1px solid #ead7f8; border-radius:13px; }
          QFrame#card:hover { border:2px solid #9e62e6; background:#f7eeff; }
          QScrollArea { background:#ffffff; border-radius:18px; padding:10px; }
          QScrollArea > QWidget > QWidget { background:#ffffff; }
          QDialog { background:#ffffff; color:#1f1a24; }
          QDialog QLabel { color:#1f1a24; font-weight:650; }
          QPushButton#quickDate { background:#efe1fa; color:#1f1a24; min-width:64px; padding:8px; }
          QPushButton#quickDate:checked { background:#9e62e6; color:#ffffff; }
          QLineEdit, QDateEdit, QSpinBox, QTimeEdit, QComboBox, QPlainTextEdit { background:#ffffff; border:1px solid #d6b8f0; border-radius:7px; padding:7px; color:#1f1a24; }
          QLineEdit:focus, QDateEdit:focus, QSpinBox:focus, QTimeEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border:2px solid #9e62e6; }
          QComboBox QAbstractItemView { background:#ffffff; color:#1f1a24; border:1px solid #9e62e6; selection-background-color:#9e62e6; selection-color:#ffffff; outline:0; }
          QComboBox QAbstractItemView::item { min-height:30px; padding:4px 10px; }
        """)

    def build_home_page(self):
        page = QWidget(); page.setObjectName("home"); outer = QVBoxLayout(page); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        header = QFrame(); header.setObjectName("hero"); header.setFixedHeight(230); head = QVBoxLayout(header); head.setContentsMargins(32, 24, 32, 22)
        top = QHBoxLayout(); menu = QPushButton("🎨"); menu.setObjectName("headerIcon"); menu.setToolTip("Apariencia y avisos"); menu.clicked.connect(self.show_appearance_menu); self.day_label = QLabel(); self.day_label.setObjectName("date"); clock = QPushButton("◴"); clock.setObjectName("headerIcon"); clock.clicked.connect(self.show_history); top.addWidget(menu); top.addStretch(); top.addWidget(self.day_label); top.addStretch(); top.addWidget(clock); head.addLayout(top); head.addStretch()
        row = QHBoxLayout(); words = QVBoxLayout(); title = QLabel("Hoy"); title.setObjectName("heading"); self.subtitle = QLabel(); self.subtitle.setObjectName("subheading"); words.addWidget(title); words.addWidget(self.subtitle); row.addLayout(words); row.addStretch(); head.addLayout(row); outer.addWidget(header)
        content = QFrame(); content.setObjectName("content"); content.setStyleSheet("QFrame#content { background:#ffffff; border-top-left-radius:26px; border-top-right-radius:26px; }"); layout = QVBoxLayout(content); layout.setContentsMargins(30, 20, 30, 18); layout.setSpacing(16)
        self.quick_days = QHBoxLayout(); self.quick_days.setSpacing(12); layout.addLayout(self.quick_days)
        label = QLabel("Mis tareas"); label.setStyleSheet("font-size:24px; font-weight:800; color:#1f1a24;"); layout.addWidget(label)
        self.summary = QLabel(); self.summary.setObjectName("summary"); layout.addWidget(self.summary)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame); self.list_widget = QWidget(); self.list_layout = QVBoxLayout(self.list_widget); self.list_layout.setAlignment(Qt.AlignTop); self.list_layout.setSpacing(10); self.scroll.setWidget(self.list_widget); layout.addWidget(self.scroll)
        bottom = QHBoxLayout(); calendar = QPushButton("Calendario"); calendar.setObjectName("secondaryButton"); calendar.clicked.connect(lambda: self.pages.setCurrentIndex(3)); bottom.addWidget(calendar); pomodoro = QPushButton("Pomodoro"); pomodoro.setObjectName("secondaryButton"); pomodoro.clicked.connect(self.open_pomodoro); bottom.addWidget(pomodoro); bottom.addStretch(); history = QPushButton("Historial"); history.setObjectName("secondaryButton"); history.clicked.connect(self.show_history); bottom.addWidget(history); add = QPushButton("+"); add.setObjectName("fab"); add.setToolTip("Crear tarea"); add.clicked.connect(self.add_task); bottom.addWidget(add); layout.addLayout(bottom); outer.addWidget(content); return page

    def build_categories_page(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(30, 28, 30, 25); layout.setSpacing(14)
        top = QHBoxLayout(); back = QPushButton("‹"); back.setObjectName("navButton"); back.clicked.connect(lambda: self.pages.setCurrentIndex(0)); top.addWidget(back); top.addStretch(); text = QLabel("Crear tarea"); text.setStyleSheet("font-size:25px;font-weight:800;"); top.addWidget(text); top.addStretch(); top.addWidget(QLabel("◴")); layout.addLayout(top)
        dates = QLabel("Elige una actividad"); dates.setStyleSheet("font-size:24px;font-weight:800;margin-top:22px;"); layout.addWidget(dates)
        layout.addWidget(QLabel("Selecciona la categoría de la nueva tarea."))
        self.category_buttons = QVBoxLayout(); self.category_buttons.setSpacing(14); layout.addLayout(self.category_buttons); layout.addStretch()
        return page

    def build_form_page(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(30, 28, 30, 25); layout.setSpacing(11)
        top = QHBoxLayout(); back = QPushButton("‹"); back.setObjectName("navButton"); back.clicked.connect(lambda: self.pages.setCurrentIndex(1)); top.addWidget(back); top.addStretch(); self.form_title = QLabel("Crear tarea"); self.form_title.setStyleSheet("font-size:25px;font-weight:800;"); top.addWidget(self.form_title); top.addStretch(); layout.addLayout(top)
        self.form_calendar = QCalendarWidget(); self.form_calendar.setGridVisible(False); self.form_calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader); self.form_calendar.setFixedHeight(185); self.form_calendar.selectionChanged.connect(self.form_calendar_selected); layout.addWidget(self.form_calendar)
        self.form_category = QLabel(); self.form_category.setStyleSheet("background:#f0e2fa;color:#7548a9;font-size:18px;font-weight:800;border-radius:12px;padding:15px;"); layout.addWidget(self.form_category)
        self.form_name = QLineEdit(); self.form_name.setPlaceholderText("Nombre de la tarea"); layout.addWidget(self.form_name)
        self.form_description = QPlainTextEdit(); self.form_description.setPlaceholderText("Descripción (opcional)"); self.form_description.setFixedHeight(72); layout.addWidget(self.form_description)
        dates = QHBoxLayout(); self.form_start = QDateEdit(); self.form_start.setCalendarPopup(True); self.form_end = QDateEdit(); self.form_end.setCalendarPopup(True); self.form_has_end = QCheckBox("Fecha de término"); dates.addWidget(QLabel("Inicio")); dates.addWidget(self.form_start); dates.addWidget(self.form_has_end); dates.addWidget(self.form_end); layout.addLayout(dates); self.form_has_end.toggled.connect(self.form_end.setEnabled)
        time = QHBoxLayout(); self.form_has_time = QCheckBox("Horario"); self.form_start_time = QTimeEdit(QTime(9,0)); self.form_end_time = QTimeEdit(QTime(10,0)); self.form_start_time.setDisplayFormat("HH:mm"); self.form_end_time.setDisplayFormat("HH:mm"); time.addWidget(self.form_has_time); time.addWidget(self.form_start_time); time.addWidget(QLabel("a")); time.addWidget(self.form_end_time); layout.addLayout(time); self.form_has_time.toggled.connect(self.form_start_time.setEnabled); self.form_has_time.toggled.connect(self.form_end_time.setEnabled)
        layout.addWidget(QLabel("Repetir en:")); self.form_days = QHBoxLayout(); self.form_day_boxes=[]
        for i, name in enumerate(WEEKDAYS): box=QCheckBox(name); self.form_day_boxes.append(box); self.form_days.addWidget(box)
        layout.addLayout(self.form_days); self.form_interval = QSpinBox(); self.form_interval.setRange(0,3650); self.form_interval.setSuffix(" días (0 = no usar)"); layout.addWidget(self.form_interval)
        save = QPushButton("Crear tarea"); save.setObjectName("createButton"); save.clicked.connect(self.save_form_task); layout.addWidget(save); layout.addStretch(); return page

    def build_calendar_page(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(30, 28, 30, 25); layout.setSpacing(18)
        top=QHBoxLayout(); back=QPushButton("‹"); back.setObjectName("navButton"); back.clicked.connect(lambda:self.pages.setCurrentIndex(0)); top.addWidget(back); top.addStretch(); label=QLabel("Calendario"); label.setStyleSheet("font-size:25px;font-weight:800;"); top.addWidget(label); top.addStretch(); layout.addLayout(top)
        self.calendar = QCalendarWidget(); self.calendar.setGridVisible(False); self.calendar.selectionChanged.connect(self.calendar_selected); layout.addWidget(self.calendar); layout.addStretch(); return page

    def task_card(self, task):
        card = QFrame(); card.setObjectName("card"); row = QHBoxLayout(card); row.setContentsMargins(16, 12, 12, 12)
        checked = self.db.completed(task["id"], self.current_day)
        main = QVBoxLayout(); title = task["title"]
        if task["start_time"]: title = f"{task['start_time']} – {task['end_time']}    {title}"
        box = QCheckBox(title); box.setChecked(checked); box.setStyleSheet("QCheckBox:checked { color:#64748b; text-decoration: line-through; }")
        box.toggled.connect(lambda value, tid=task["id"]: self.complete(tid, value)); main.addWidget(box)
        caption = task["description"] or task["category"]
        caption_label = QLabel(f"{task['category']}  ·  {caption}" if task["description"] else caption)
        caption_label.setStyleSheet("color:#7548a9; padding-left:27px;"); main.addWidget(caption_label); row.addLayout(main); row.addStretch()
        detail = []
        if task["weekdays"]: detail.append(" · ".join(WEEKDAYS[int(x)] for x in task["weekdays"].split(",")))
        if task["interval_days"]: detail.append(f"cada {task['interval_days']} días")
        hint = QLabel("  |  ".join(detail)); hint.setStyleSheet("color:#7548a9; font-weight:600;"); row.addWidget(hint)
        edit = QPushButton("Editar"); edit.setObjectName("editButton"); edit.setStyleSheet("QPushButton { color:#ffffff; background:#9e62e6; } QPushButton:hover { background:#8447d2; }"); edit.clicked.connect(lambda: self.edit_task(task)); row.addWidget(edit)
        return card

    def refresh(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0); widget = item.widget()
            if widget: widget.deleteLater()
        tasks = self.db.tasks_for(self.current_day); done = sum(self.db.completed(t["id"], self.current_day) for t in tasks)
        while self.quick_days.count():
            item = self.quick_days.takeAt(0); widget = item.widget()
            if widget: widget.deleteLater()
        first = self.current_day - timedelta(days=2)
        for offset in range(5):
            current = first + timedelta(days=offset)
            button = QPushButton(f"{current.day}\n{WEEKDAYS[current.weekday()]}"); button.setObjectName("quickDate"); button.setCheckable(True); button.setChecked(current == self.current_day)
            button.clicked.connect(lambda _, target=current: self.select_day(target)); self.quick_days.addWidget(button)
        self.quick_days.addStretch()
        while self.category_buttons.count():
            item = self.category_buttons.takeAt(0); widget = item.widget()
            if widget: widget.deleteLater()
        counts = self.db.category_counts()
        for category in CATEGORIES:
            button = QPushButton(f"{CATEGORY_ICONS[category]}    {category}\n       {counts.get(category, 0)} tareas")
            button.setMinimumHeight(70); button.setStyleSheet("QPushButton { text-align:left; font-size:16px; color:#4d2779; background:#f0e2fa; border-radius:12px; padding:12px; } QPushButton:hover { background:#dfc3f5; }")
            button.clicked.connect(lambda _, value=category: self.open_form(value)); self.category_buttons.addWidget(button)
        self.day_label.setText(self.current_day.strftime("%d %b"))
        self.subtitle.setText(f"{len(tasks)} tarea(s) para hoy")
        self.summary.setText(f"{done} de {len(tasks)} completadas")
        if tasks:
            for task in tasks: self.list_layout.addWidget(self.task_card(task))
        else:
            empty = QLabel("No hay tareas programadas para este día.\nCrea una nueva o revisa otro día.")
            empty.setAlignment(Qt.AlignCenter); empty.setStyleSheet("color:#7c8798; font-size:16px; padding:50px;"); self.list_layout.addWidget(empty)

    def complete(self, task_id, value): self.db.set_completed(task_id, self.current_day, value); self.refresh()
    def select_day(self, target): self.current_day = target; self.refresh()
    def change_day(self, offset): self.current_day += timedelta(days=offset); self.refresh()
    def go_today(self): self.current_day = date.today(); self.refresh()
    def calendar_selected(self):
        self.select_day(self.calendar.selectedDate().toPython()); self.pages.setCurrentIndex(0)
    def form_calendar_selected(self):
        self.form_start.setDate(self.form_calendar.selectedDate())
    def add_task(self): self.pages.setCurrentIndex(1)
    def open_form(self, category, task=None):
        self.editing_task = task; self.selected_category = category
        self.form_title.setText("Editar tarea" if task else "Crear tarea"); self.form_category.setText(f"{CATEGORY_ICONS[category]}  {category}")
        source = task or {}; current = self.current_day if not task else date.fromisoformat(task["start_date"])
        self.form_name.setText(source["title"] if task else ""); self.form_description.setPlainText(source["description"] if task else "")
        selected_date = QDate(current.year,current.month,current.day); self.form_start.setDate(selected_date); self.form_calendar.setSelectedDate(selected_date); has_end=bool(task and task["end_date"]); self.form_has_end.setChecked(has_end); end=date.fromisoformat(task["end_date"]) if has_end else current; self.form_end.setDate(QDate(end.year,end.month,end.day)); self.form_end.setEnabled(has_end)
        has_time=bool(task and task["start_time"]); self.form_has_time.setChecked(has_time); self.form_start_time.setEnabled(has_time); self.form_end_time.setEnabled(has_time)
        if has_time: self.form_start_time.setTime(QTime.fromString(task["start_time"],"HH:mm")); self.form_end_time.setTime(QTime.fromString(task["end_time"],"HH:mm"))
        chosen=task["weekdays"].split(",") if task else []
        for i,box in enumerate(self.form_day_boxes): box.setChecked(str(i) in chosen)
        self.form_interval.setValue(task["interval_days"] if task else 0); self.pages.setCurrentIndex(2)
    def save_form_task(self):
        if not self.form_name.text().strip(): QMessageBox.warning(self,APP_NAME,"Escribe un nombre para la tarea."); return
        if not any(x.isChecked() for x in self.form_day_boxes) and self.form_interval.value()==0: QMessageBox.warning(self,APP_NAME,"Elige un día o una periodicidad."); return
        if self.form_has_end.isChecked() and self.form_end.date()<self.form_start.date(): QMessageBox.warning(self,APP_NAME,"La fecha de término debe ser posterior al inicio."); return
        start_time=self.form_start_time.time().toString("HH:mm") if self.form_has_time.isChecked() else ""; end_time=self.form_end_time.time().toString("HH:mm") if self.form_has_time.isChecked() else ""; end_date=self.form_end.date().toString("yyyy-MM-dd") if self.form_has_end.isChecked() else ""
        self.db.save_task(self.form_name.text(),self.form_description.toPlainText(),self.selected_category,start_time,end_time,end_date,[i for i,x in enumerate(self.form_day_boxes) if x.isChecked()],self.form_interval.value(),self.form_start.date().toPython(),task_id=self.editing_task["id"] if self.editing_task else None); self.current_day=self.form_start.date().toPython(); self.refresh(); self.pages.setCurrentIndex(0)
    def edit_task(self, task): self.open_form(task["category"], task)

    def show_history(self):
        dialog = QDialog(self); dialog.setWindowTitle("Historial de cumplimiento"); dialog.resize(460, 460)
        layout = QVBoxLayout(dialog); layout.addWidget(QLabel("Tareas completadas en los últimos 14 días"))
        scroll = QScrollArea(); scroll.setWidgetResizable(True); content = QWidget(); rows = QVBoxLayout(content); rows.setAlignment(Qt.AlignTop)
        entries = self.db.history()
        if entries:
            for entry in entries:
                item = QLabel(f"✓  {date.fromisoformat(entry['day']).strftime('%d/%m/%Y')}   {entry['title']}")
                item.setStyleSheet("padding:8px; background:#f6f8fb; border-radius:6px;"); rows.addWidget(item)
        else:
            rows.addWidget(QLabel("Aún no hay tareas completadas."))
        scroll.setWidget(content); layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(dialog.reject); buttons.accepted.connect(dialog.accept); layout.addWidget(buttons)
        dialog.exec()

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        menu = QMenu(self)
        show = QAction("Abrir tareas", self); show.triggered.connect(self.showNormal); menu.addAction(show)
        quit_action = QAction("Salir", self); quit_action.triggered.connect(QApplication.quit); menu.addAction(quit_action)
        self.tray.setContextMenu(menu); self.tray.show()

    def apply_theme(self):
        accent, soft, muted, page = THEMES.get(self.theme_name, THEMES["Violeta / Lavanda"])
        surface, ink = ("#202028", "#f4f0f7") if self.dark_mode else ("#ffffff", "#1f1a24")
        self.setStyleSheet(self.styleSheet() + f"""
          QMainWindow {{ background:{page}; color:{ink}; }} QFrame#hero {{ background:{accent}; }}
          QFrame#content, QScrollArea, QScrollArea > QWidget > QWidget, QDialog {{ background:{surface}; color:{ink}; }}
          QLabel, QDialog QLabel, QCheckBox {{ color:{ink}; }} QLabel#summary {{ color:{muted}; background:{surface}; }}
          QPushButton {{ color:{ink}; background:{soft}; }} QPushButton:hover {{ background:{page}; }}
          QPushButton#primaryButton, QPushButton#todayButton {{ color:#fff; background:{accent}; }}
          QPushButton#secondaryButton {{ color:{muted}; background:{surface}; }} QFrame#card {{ background:{soft}; border-color:{soft}; }}
          QCheckBox::indicator {{ border-color:{accent}; background:{surface}; }} QCheckBox::indicator:checked {{ background:{accent}; border-color:{accent}; }}
          QLineEdit, QDateEdit, QSpinBox, QTimeEdit, QComboBox, QPlainTextEdit {{ background:{surface}; color:{ink}; border-color:{soft}; }}
        """)

    def show_appearance_menu(self):
        menu = QMenu(self)
        themes = menu.addMenu("Paleta de colores")
        for name in THEMES:
            action = themes.addAction(name); action.setCheckable(True); action.setChecked(name == self.theme_name)
            action.triggered.connect(lambda _, value=name: self.set_theme(value))
        dark = menu.addAction("Modo oscuro"); dark.setCheckable(True); dark.setChecked(self.dark_mode); dark.triggered.connect(self.toggle_dark)
        notices = menu.addMenu("Avisos de pendientes")
        for minutes, text in ((60, "Cada 1 hora"), (120, "Cada 2 horas")):
            action = notices.addAction(text); action.setCheckable(True); action.setChecked(minutes == self.notification_minutes)
            action.triggered.connect(lambda _, value=minutes: self.set_notification_frequency(value))
        menu.exec(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

    def set_theme(self, name):
        self.theme_name = name; self.settings.setValue("theme", name); self.apply_theme()

    def toggle_dark(self, enabled):
        self.dark_mode = enabled; self.settings.setValue("dark", enabled); self.apply_theme()

    def set_notification_frequency(self, minutes):
        self.notification_minutes = minutes; self.settings.setValue("notification_minutes", minutes); self.schedule_notifications()

    def schedule_notifications(self):
        self.timer.start(max(60, self.notification_minutes) * 60 * 1000)

    def open_pomodoro(self):
        PomodoroDialog(self.db, self).exec()

    def notify(self, title, message):
        if self.tray.isVisible(): self.tray.showMessage(title, message, QSystemTrayIcon.Information, 8000)

    def check_pending(self):
        if date.today() != self.current_day: self.go_today()
        pending = [t for t in self.db.tasks_for(date.today()) if not self.db.completed(t["id"], date.today())]
        if pending: self.notify(APP_NAME, f"Tienes {len(pending)} tarea(s) pendiente(s) para hoy.")

    def closeEvent(self, event):
        self.tray.hide()
        event.accept()
        QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv); app.setApplicationName(APP_NAME)
    window = MainWindow(); window.show(); sys.exit(app.exec())
