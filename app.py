"""Интерфейс и уведомления. Запуск: py -3 app.py."""

import sqlite3
import tkinter as tk
from collections import deque
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from database import CANCELLED, DONE, OVERDUE, STATUSES, WAITING, ReminderDatabase


DATE_FORMAT = "%d.%m.%Y %H:%M"
ALL_STATUSES = "Все статусы"


def display_date(value):
    return datetime.fromisoformat(value).strftime(DATE_FORMAT)


class ReminderApp:
    def __init__(self, root, database):
        self.root = root
        self.database = database
        self.rows = {}
        self.notification_queue = deque()
        self.announced = set()
        self.popup = None
        self.popup_id = None
        self.timer_id = None
        self.closing = False
        self.filter_var = tk.StringVar(value=ALL_STATUSES)
        self.message_var = tk.StringVar()

        root.title("Напоминалка")
        root.geometry("960x640")
        root.minsize(720, 480)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.build_interface()
        self.tick()

    def build_interface(self):
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)
        toolbar = ttk.Frame(container)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="Добавить", command=self.open_add_dialog).pack(side="left")
        ttk.Label(toolbar, text="Статус:").pack(side="left", padx=(24, 6))
        selector = ttk.Combobox(
            toolbar, textvariable=self.filter_var,
            values=(ALL_STATUSES,) + STATUSES, state="readonly", width=18,
        )
        selector.pack(side="left")
        selector.bind("<<ComboboxSelected>>", lambda event: self.safe_refresh())

        table_frame = ttk.Frame(container)
        table_frame.pack(fill="both", expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.table = ttk.Treeview(
            table_frame, columns=("title", "due_at", "status"),
            show="headings", selectmode="browse",
        )
        for name, title, width in (
            ("title", "Заголовок", 420),
            ("due_at", "Дата и время", 160),
            ("status", "Статус", 130),
        ):
            self.table.heading(name, text=title)
            self.table.column(name, width=width, minwidth=100)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.table.tag_configure(OVERDUE, foreground="#a12622")
        self.table.bind("<<TreeviewSelect>>", lambda event: self.show_description())

        ttk.Label(container, text="Описание выбранного напоминания:").pack(
            anchor="w", pady=(10, 4)
        )
        self.description = tk.Text(container, height=5, wrap="word", state="disabled")
        self.description.pack(fill="x")
        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=10)
        for text, command in (
            ("Готово", lambda: self.change_selected_status(DONE)),
            ("Отменено", lambda: self.change_selected_status(CANCELLED)),
            ("Удалить", self.delete_selected),
        ):
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=(0, 8))
        ttk.Label(container, textvariable=self.message_var, wraplength=880).pack(anchor="w")

    def refresh(self):
        status = self.filter_var.get()
        records = self.database.get_all_reminders(None if status == ALL_STATUSES else status)
        new_rows = {str(row["id"]): dict(row) for row in records}
        if new_rows != self.rows:
            selected = self.table.selection()
            old_children = self.table.get_children()
            if old_children:
                self.table.delete(*old_children)
            self.rows = new_rows
            for key, row in self.rows.items():
                self.table.insert(
                    "", "end", iid=key,
                    values=(row["title"], display_date(row["due_at"]), row["status"]),
                    tags=(row["status"],),
                )
            if selected and selected[0] in self.rows:
                self.table.selection_set(selected[0])
            self.show_description()
        self.message_var.set(f"В списке: {len(records)}. Уведомления работают, пока приложение запущено.")

    def safe_refresh(self):
        try:
            self.refresh()
        except sqlite3.Error as error:
            self.show_database_error(error)

    def show_description(self):
        selected = self.table.selection()
        row = self.rows.get(selected[0]) if selected else None
        self.description.configure(state="normal")
        self.description.delete("1.0", "end")
        if row:
            self.description.insert("1.0", row["description"] or "Описание не указано.")
        self.description.configure(state="disabled")

    def selected_id(self):
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo("Выбор напоминания", "Выберите напоминание в списке.", parent=self.root)
            return None
        return int(selected[0])

    def show_database_error(self, error, parent=None):
        messagebox.showerror(
            "Ошибка базы данных", f"Не удалось выполнить операцию:\n{error}",
            parent=parent or self.root,
        )

    def open_add_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Новое напоминание")
        dialog.geometry("520x390")
        dialog.minsize(440, 360)
        dialog.transient(self.root)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Заголовок *").pack(anchor="w")
        title = ttk.Entry(frame)
        title.pack(fill="x", pady=(4, 12))
        ttk.Label(frame, text="Описание").pack(anchor="w")
        description = tk.Text(frame, height=6, wrap="word")
        description.pack(fill="both", expand=True, pady=(4, 12))
        ttk.Label(frame, text="Дата и время * — ДД.ММ.ГГГГ ЧЧ:ММ (местное время)").pack(anchor="w")
        due = ttk.Entry(frame)
        due.insert(0, (datetime.now() + timedelta(hours=1)).strftime(DATE_FORMAT))
        due.pack(fill="x", pady=(4, 12))

        def save():
            heading = title.get().strip()
            if not heading:
                messagebox.showerror("Проверьте данные", "Укажите заголовок.", parent=dialog)
                title.focus_set()
                return
            try:
                due_at = datetime.strptime(due.get().strip(), DATE_FORMAT)
            except ValueError:
                messagebox.showerror(
                    "Проверьте дату", "Введите существующую дату в формате ДД.ММ.ГГГГ ЧЧ:ММ.",
                    parent=dialog,
                )
                return
            if due_at <= datetime.now():
                messagebox.showerror("Проверьте дату", "Укажите время в будущем.", parent=dialog)
                return
            try:
                self.database.add_reminder(heading, description.get("1.0", "end-1c"), due_at)
            except sqlite3.Error as error:
                self.show_database_error(error, dialog)
                return
            dialog.destroy()
            self.safe_refresh()

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Сохранить", command=save).pack(side="right")
        ttk.Button(buttons, text="Отмена", command=dialog.destroy).pack(side="right", padx=8)
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        title.focus_set()
        dialog.grab_set()

    def change_selected_status(self, status):
        reminder_id = self.selected_id()
        if reminder_id is not None:
            self.change_status(reminder_id, status)

    def change_status(self, reminder_id, status):
        try:
            self.database.update_status(reminder_id, status)
        except sqlite3.Error as error:
            self.show_database_error(error, self.popup)
            return
        if self.popup_id == reminder_id:
            self.dismiss_popup()
        self.safe_refresh()

    def delete_selected(self):
        reminder_id = self.selected_id()
        if reminder_id is None:
            return
        if not messagebox.askyesno(
            "Удаление", "Удалить выбранное напоминание? Восстановить его будет нельзя.", parent=self.root
        ):
            return
        try:
            self.database.delete_reminder(reminder_id)
        except sqlite3.Error as error:
            self.show_database_error(error)
            return
        if self.popup_id == reminder_id:
            self.dismiss_popup()
        self.safe_refresh()

    def tick(self):
        if self.closing:
            return
        try:
            self.database.mark_overdue()
            due = self.database.get_due_reminders() + self.database.get_all_reminders(OVERDUE)
            for row in sorted(due, key=lambda item: (item["due_at"], item["id"])):
                if row["id"] not in self.announced:
                    self.notification_queue.append(row["id"])
                    self.announced.add(row["id"])
            self.refresh()
            self.show_next_popup()
        except sqlite3.Error as error:
            # Ошибка видна в окне; следующая проверка повторится без потока диалогов.
            self.message_var.set(f"Не удалось проверить напоминания: {error}. Повтор через секунду.")
        finally:
            if not self.closing:
                self.timer_id = self.root.after(1000, self.tick)

    def show_next_popup(self):
        if self.popup is not None or self.closing:
            return
        # Не перебиваем заполнение формы: время и статусы продолжают проверяться.
        if self.root.grab_current() is not None:
            return
        while self.notification_queue:
            reminder_id = self.notification_queue[0]
            row = self.database.get_reminder_by_id(reminder_id)
            self.notification_queue.popleft()
            if row is not None and row["status"] in (WAITING, OVERDUE):
                break
        else:
            return

        # Без transient(root): окно должно появляться и при свёрнутом главном окне.
        popup = tk.Toplevel(self.root)
        self.popup = popup
        self.popup_id = reminder_id
        popup.title("Пора выполнить напоминание")
        popup.attributes("-topmost", True)
        popup.geometry("500x330")
        popup.minsize(420, 300)
        popup.protocol("WM_DELETE_WINDOW", self.dismiss_popup)
        frame = ttk.Frame(popup, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=row["title"], font=("Segoe UI", 14, "bold"), wraplength=450).pack(anchor="w")
        ttk.Label(frame, text=f"Срок: {display_date(row['due_at'])}").pack(anchor="w", pady=(8, 12))
        details = tk.Text(frame, height=6, wrap="word")
        details.insert("1.0", row["description"] or "Описание не указано.")
        details.configure(state="disabled")
        details.pack(fill="both", expand=True)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="Готово", command=lambda: self.change_status(reminder_id, DONE)).pack(side="left")
        ttk.Button(buttons, text="Отменено", command=lambda: self.change_status(reminder_id, CANCELLED)).pack(side="left", padx=8)
        ttk.Button(buttons, text="Закрыть", command=self.dismiss_popup).pack(side="right")
        popup.deiconify()
        popup.lift()
        popup.bell()

    def dismiss_popup(self):
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
            self.popup_id = None
        # Следующее уведомление покажет очередная проверка таймера.

    def close(self):
        if not messagebox.askokcancel(
            "Закрыть приложение?",
            "После закрытия уведомления прекратятся. Чтобы получать их, сверните окно.\n\nЗакрыть приложение?",
            parent=self.root,
        ):
            return
        self.closing = True
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
        self.database.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        database = ReminderDatabase()
    except sqlite3.Error as error:
        root.withdraw()
        messagebox.showerror("Ошибка запуска", f"Не удалось открыть базу данных:\n{error}", parent=root)
        root.destroy()
        return 1
    ReminderApp(root, database)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
