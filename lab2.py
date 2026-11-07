"""
Экспертная система подбора автомобиля
Лабораторная работа №2
Графический интерфейс на базе Tkinter
"""

import math
import sys
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import List, Optional


# ============================================================
# КЛАСС БАЗЫ ЗНАНИЙ
# ============================================================
class KnowledgeBase:
    """Класс для представления базы знаний"""

    def __init__(self):
        self.description = ""
        self.questions = []
        self.hypotheses = []
        self.filename = ""

    def load_from_file(self, filename: str) -> bool:
        """Загрузка базы знаний из файла"""
        # Пробуем разные кодировки в правильном порядке
        content = None
        used_encoding = None
        
        # Сначала пробуем UTF-8 (современный стандарт)
        for encoding in ['utf-8-sig', 'utf-8', 'cp1251', 'cp866']:
            try:
                with open(filename, 'r', encoding=encoding) as f:
                    content = f.read()
                
                # Проверяем, что текст читается корректно
                # Если есть кириллица, проверяем что она не "кракозябры"
                if any('\u0400' <= c <= '\u04FF' for c in content):
                    # Проверяем, что нет типичных артефактов неправильной кодировки
                    if 'Р' not in content[:100] or 'СЃ' not in content[:100]:
                        used_encoding = encoding
                        break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if content is None:
            raise ValueError("Не удалось определить кодировку файла. "
                            "Поддерживаются: UTF-8, CP1251, CP866")
        
        print(f"Файл загружен в кодировке: {used_encoding}")  # Для отладки
        
        self.filename = os.path.basename(filename)
        sections = content.split('\n\n')
        
        if len(sections) < 3:
            raise ValueError("Файл должен содержать минимум 3 секции")
        
        # Секция 1: Описание
        self.description = sections[0].strip()
        
        # Секция 2: Вопросы
        self.questions = []
        for line in sections[1].strip().split('\n'):
            line = line.strip()
            if line and not line.lower().startswith('вопросы'):
                # Убираем номер в начале, если есть
                if '.' in line and line.split('.')[0].strip().isdigit():
                    line = line.split('.', 1)[1].strip()
                self.questions.append(line)
        
        # Секция 3: Гипотезы
        self.hypotheses = []
        for line in sections[2].strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 4:
                continue
            
            hypothesis_name = parts[0]
            prior_prob = float(parts[1])
            
            evidences = {}
            i = 2
            while i <= len(parts) - 3:
                try:
                    evidence_idx = int(parts[i])
                    py = float(parts[i + 1])
                    pn = float(parts[i + 2])
                    evidences[evidence_idx] = {'py': py, 'pn': pn}
                    i += 3
                except (ValueError, IndexError):
                    break
            
            self.hypotheses.append({
                'name': hypothesis_name,
                'prior': prior_prob,
                'current': prior_prob,
                'evidences': evidences
            })
        
        return True

    def validate(self) -> List[str]:
        """Проверка корректности базы знаний. Возвращает список предупреждений."""
        warnings = []
        if not self.questions:
            warnings.append("Не найдены вопросы")
        if not self.hypotheses:
            warnings.append("Не найдены гипотезы")

        total_prior = sum(h['prior'] for h in self.hypotheses)
        if abs(total_prior - 1.0) > 0.05:
            warnings.append(
                f"Сумма априорных вероятностей = {total_prior:.3f} (должна быть ~1.0)")

        return warnings


# ============================================================
# КЛАСС ЭКСПЕРТНОЙ СИСТЕМЫ
# ============================================================
class ExpertSystem:
    """Логика экспертной системы"""

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self.answers = {}
        self.history = []

    def calculate_evidence_prob(self, evidence_idx: int) -> float:
        """Расчёт вероятности свидетельства P(E)"""
        prob = 0.0
        for h in self.kb.hypotheses:
            if evidence_idx in h['evidences']:
                prob += h['evidences'][evidence_idx]['py'] * h['current']
        return prob

    def calculate_evidence_cost(self, evidence_idx: int) -> float:
        """Расчёт цены свидетельства (энтропия)"""
        pe = self.calculate_evidence_prob(evidence_idx)
        if pe <= 0 or pe >= 1:
            return 0.0
        pne = 1.0 - pe
        cost = 0.0
        if pe > 0:
            cost -= pe * math.log2(pe)
        if pne > 0:
            cost -= pne * math.log2(pne)
        return cost

    def select_next_question(self) -> Optional[int]:
        """Выбор следующего вопроса с максимальной ценой"""
        max_cost = -1
        best_question = None
        for i in range(1, len(self.kb.questions) + 1):
            if i in self.answers:
                continue
            cost = self.calculate_evidence_cost(i)
            if cost > max_cost:
                max_cost = cost
                best_question = i
        return best_question

    def update_probabilities(self, evidence_idx: int, confidence: int):
        """Обновление вероятностей гипотез по формуле Байеса"""
        if confidence == 0:
            return

        # Преобразование КУ в вероятность
        user_prob = 0.5 + (confidence / 5.0) * 0.5

        # Расчёт P(E) с учётом ответа
        pe = 0.0
        for h in self.kb.hypotheses:
            if evidence_idx in h['evidences']:
                if confidence > 0:
                    py = h['evidences'][evidence_idx]['py']
                    pe += py * h['current']
                else:
                    pn = h['evidences'][evidence_idx]['pn']
                    pe += pn * h['current']

        if pe <= 0:
            return

        # Обновление вероятностей
        for h in self.kb.hypotheses:
            if evidence_idx in h['evidences']:
                if confidence > 0:
                    py = h['evidences'][evidence_idx]['py']
                    h['current'] = (py * h['current']) / pe
                else:
                    pn = h['evidences'][evidence_idx]['pn']
                    h['current'] = (pn * h['current']) / pe

        # Нормализация
        total = sum(h['current'] for h in self.kb.hypotheses)
        if total > 0:
            for h in self.kb.hypotheses:
                h['current'] /= total

    def reset(self):
        """Сброс системы"""
        for h in self.kb.hypotheses:
            h['current'] = h['prior']
        self.answers = {}
        self.history = []

    def undo_last(self):
        """Отмена последнего ответа"""
        if not self.history:
            return False
        # Удаляем последний ответ
        last_evidence = self.history.pop()
        del self.answers[last_evidence['evidence_idx']]
        # Пересчитываем вероятности с нуля
        self.reset_probabilities_only()
        for entry in self.history:
            self.update_probabilities(entry['evidence_idx'], entry['confidence'])
        return True

    def reset_probabilities_only(self):
        """Сброс только вероятностей"""
        for h in self.kb.hypotheses:
            h['current'] = h['prior']


# ============================================================
# ГЛАВНОЕ ОКНО ПРИЛОЖЕНИЯ
# ============================================================
class ExpertSystemApp:
    """Главное окно приложения"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Экспертная система подбора автомобиля")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)

        self.kb = None
        self.es = None
        self.consultation_active = False

        self._create_styles()
        self._create_menu()
        self._create_widgets()
        self._show_welcome()

    def _create_styles(self):
        """Настройка стилей"""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('Title.TLabel', font=('Segoe UI', 14, 'bold'))
        self.style.configure('Header.TLabel', font=('Segoe UI', 11, 'bold'))
        self.style.configure('TButton', padding=5)

    def _create_menu(self):
        """Создание меню"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # --- Файл ---
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Открыть базу знаний...", command=self.open_kb,
                            accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.root.quit,
                            accelerator="Alt+F4")
        menubar.add_cascade(label="Файл", menu=file_menu)

        # --- Консультация ---
        self.consult_menu = tk.Menu(menubar, tearoff=0)
        self.consult_menu.add_command(
            label="Начать консультацию", command=self.start_consultation,
            accelerator="F3", state=tk.DISABLED)
        self.consult_menu.add_command(
            label="Отменить последний ответ", command=self.undo_answer,
            accelerator="Ctrl+Z", state=tk.DISABLED)
        self.consult_menu.add_separator()  # индекс 2
        self.consult_menu.add_command(
            label="Сохранить отчёт...", command=self.save_report,
            state=tk.DISABLED)             # индекс 3
        menubar.add_cascade(label="Консультация", menu=self.consult_menu)

        # --- Справка ---
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="О программе", command=self.show_about)
        menubar.add_cascade(label="Справка", menu=help_menu)

        # --- Горячие клавиши ---
        self.root.bind('<Control-o>', lambda e: self.open_kb())
        self.root.bind('<F3>', lambda e: self.start_consultation())
        self.root.bind('<Control-z>', lambda e: self.undo_answer())

    def _create_widgets(self):
        """Создание виджетов главного окна"""
        # Главный контейнер
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ============ ЛЕВАЯ ПАНЕЛЬ ============
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=2)

        # Информация о БЗ
        info_frame = ttk.LabelFrame(left_frame, text="База знаний", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 5))

        self.lbl_kb_name = ttk.Label(info_frame, text="База знаний не загружена",
                                     style='Title.TLabel', wraplength=500)
        self.lbl_kb_name.pack(anchor=tk.W)

        self.lbl_kb_info = ttk.Label(info_frame, text="", foreground='gray')
        self.lbl_kb_info.pack(anchor=tk.W, pady=(5, 0))

        # Область вопроса
        question_frame = ttk.LabelFrame(left_frame, text="Вопрос", padding=10)
        question_frame.pack(fill=tk.X, pady=5)

        self.lbl_question = ttk.Label(question_frame,
                                      text="Загрузите базу знаний и начните консультацию",
                                      font=('Segoe UI', 11), wraplength=500)
        self.lbl_question.pack(anchor=tk.W)

        # Слайдер КУ
        slider_frame = ttk.Frame(question_frame)
        slider_frame.pack(fill=tk.X, pady=(15, 5))

        ttk.Label(slider_frame, text="Нет (-5)").pack(side=tk.LEFT)
        ttk.Label(slider_frame, text="Да (+5)").pack(side=tk.RIGHT)

        self.confidence_var = tk.IntVar(value=0)
        self.scale = ttk.Scale(slider_frame, from_=-5, to=5,
                               variable=self.confidence_var,
                               orient=tk.HORIZONTAL,
                               command=self._on_scale_change)
        self.scale.pack(fill=tk.X, expand=True, padx=5)

        self.lbl_confidence = ttk.Label(slider_frame, text="КУ: 0 (Не знаю)",
                                        font=('Segoe UI', 10, 'bold'))
        self.lbl_confidence.pack(anchor=tk.CENTER, pady=(5, 0))

        # Кнопки
        btn_frame = ttk.Frame(question_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.btn_open = ttk.Button(btn_frame, text="Открыть БЗ",
                                   command=self.open_kb)
        self.btn_open.pack(side=tk.LEFT, padx=2)

        self.btn_start = ttk.Button(btn_frame, text="Начать консультацию",
                                    command=self.start_consultation, state=tk.DISABLED)
        self.btn_start.pack(side=tk.LEFT, padx=2)

        self.btn_answer = ttk.Button(btn_frame, text="Ответить",
                                     command=self.submit_answer, state=tk.DISABLED)
        self.btn_answer.pack(side=tk.LEFT, padx=2)

        self.btn_undo = ttk.Button(btn_frame, text="Отменить",
                                   command=self.undo_answer, state=tk.DISABLED)
        self.btn_undo.pack(side=tk.LEFT, padx=2)

        # Область результата
        result_frame = ttk.LabelFrame(left_frame, text="Результат", padding=10)
        result_frame.pack(fill=tk.X, pady=5)

        self.lbl_result = ttk.Label(result_frame, text="—",
                                    font=('Segoe UI', 12, 'bold'),
                                    foreground='#2a7f2a', wraplength=500)
        self.lbl_result.pack(anchor=tk.W)

        # ============ ПРАВАЯ ПАНЕЛЬ ============
        right_paned = ttk.PanedWindow(main_paned, orient=tk.VERTICAL)
        main_paned.add(right_paned, weight=1)

        # Вероятности гипотез
        prob_frame = ttk.LabelFrame(right_paned, text="Вероятности гипотез", padding=5)
        right_paned.add(prob_frame, weight=2)

        # Treeview для гипотез
        columns = ('name', 'prior', 'current')
        self.tree = ttk.Treeview(prob_frame, columns=columns, show='headings',
                                 height=15)
        self.tree.heading('name', text='Гипотеза')
        self.tree.heading('prior', text='Априорная')
        self.tree.heading('current', text='Текущая')
        self.tree.column('name', width=200)
        self.tree.column('prior', width=80, anchor=tk.CENTER)
        self.tree.column('current', width=80, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(prob_frame, orient=tk.VERTICAL,
                                  command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # История ответов
        history_frame = ttk.LabelFrame(right_paned, text="История ответов", padding=5)
        right_paned.add(history_frame, weight=1)

        self.history_text = scrolledtext.ScrolledText(history_frame, height=8,
                                                      font=('Consolas', 9),
                                                      state=tk.DISABLED)
        self.history_text.pack(fill=tk.BOTH, expand=True)

    def _show_welcome(self):
        """Показ приветственного сообщения"""
        self.lbl_kb_name.config(text="Добро пожаловать!")
        self.lbl_kb_info.config(text="Откройте файл базы знаний для начала работы")

    def _on_scale_change(self, value):
        """Обработчик изменения слайдера"""
        v = int(float(value))
        self.confidence_var.set(v)
        if v == 0:
            text = "КУ: 0 (Не знаю)"
        elif v > 0:
            text = f"КУ: +{v} (Да)"
        else:
            text = f"КУ: {v} (Нет)"
        self.lbl_confidence.config(text=text)

    # ============ ДЕЙСТВИЯ ============
    def open_kb(self):
        """Открытие базы знаний"""
        filename = filedialog.askopenfilename(
            title="Открыть базу знаний",
            filetypes=[("Файл базы знаний", "*.mkb"), ("Все файлы", "*.*")],
            initialdir=os.getcwd()
        )
        if not filename:
            return

        try:
            self.kb = KnowledgeBase()
            self.kb.load_from_file(filename)
            warnings = self.kb.validate()

            self.es = ExpertSystem(self.kb)

            # Обновление интерфейса
            self.lbl_kb_name.config(text=self.kb.description.split('\n')[0])
            info_text = (f"Файл: {self.kb.filename} | "
                         f"Вопросов: {len(self.kb.questions)} | "
                         f"Гипотез: {len(self.kb.hypotheses)}")
            self.lbl_kb_info.config(text=info_text)

            # Заполнение таблицы
            self._refresh_tree()

            # Активация кнопок
            self.btn_start.config(state=tk.NORMAL)
            self.lbl_question.config(text="База знаний загружена. Нажмите «Начать консультацию»")
            self.lbl_result.config(text="—", foreground='#2a7f2a')

            if warnings:
                messagebox.showwarning("Предупреждения",
                                       "\n".join(warnings))
            else:
                messagebox.showinfo("Успех",
                                    f"База знаний успешно загружена!\n"
                                    f"Вопросов: {len(self.kb.questions)}\n"
                                    f"Гипотез: {len(self.kb.hypotheses)}")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить базу знаний:\n{e}")

    def _refresh_tree(self):
        """Обновление таблицы гипотез"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        sorted_h = sorted(self.kb.hypotheses,
                          key=lambda h: h['current'], reverse=True)
        for h in sorted_h:
            self.tree.insert('', tk.END, values=(
                h['name'],
                f"{h['prior']:.3f}",
                f"{h['current']:.3f}"
            ))

    def start_consultation(self):
        """Начало консультации"""
        if not self.es:
            messagebox.showwarning("Внимание", "Сначала загрузите базу знаний")
            return

        self.es.reset()
        self.consultation_active = True
        self.history_text.config(state=tk.NORMAL)
        self.history_text.delete('1.0', tk.END)
        self.history_text.config(state=tk.DISABLED)

        self.btn_start.config(state=tk.DISABLED)
        self.btn_answer.config(state=tk.NORMAL)
        self.btn_undo.config(state=tk.DISABLED)
        self.lbl_result.config(text="Консультация начата", foreground='#2a7f2a')

        self._show_next_question()

    def _show_next_question(self):
        """Показ следующего вопроса"""
        next_q = self.es.select_next_question()

        if next_q is None:
            self._finish_consultation()
            return

        question_text = self.kb.questions[next_q - 1]
        self.lbl_question.config(text=f"Вопрос {next_q}: {question_text}")
        self.current_question = next_q
        self.confidence_var.set(0)
        self._on_scale_change(0)

    def submit_answer(self):
        """Отправка ответа"""
        if not self.consultation_active:
            return

        confidence = self.confidence_var.get()
        self.es.answers[self.current_question] = confidence
        self.es.history.append({
            'evidence_idx': self.current_question,
            'confidence': confidence,
            'question': self.kb.questions[self.current_question - 1]
        })

        # Запись в историю
        if confidence > 0:
            ans_text = "Да"
        elif confidence < 0:
            ans_text = "Нет"
        else:
            ans_text = "Не знаю"

        self.history_text.config(state=tk.NORMAL)
        self.history_text.insert(tk.END,
                                 f"• {self.kb.questions[self.current_question - 1]}\n"
                                 f"  Ответ: {ans_text} (КУ = {confidence:+d})\n\n")
        self.history_text.config(state=tk.DISABLED)
        self.history_text.see(tk.END)

        # Обновление вероятностей
        self.es.update_probabilities(self.current_question, confidence)
        self._refresh_tree()
        self.btn_undo.config(state=tk.NORMAL)

        # Следующий вопрос
        self._show_next_question()

    def undo_answer(self):
        """Отмена последнего ответа"""
        if not self.es or not self.es.undo_last():
            messagebox.showinfo("Информация", "Нечего отменять")
            return

        self._refresh_tree()
        self._rebuild_history_text()

        if not self.es.history:
            self.btn_undo.config(state=tk.DISABLED)

        self._show_next_question()

    def _rebuild_history_text(self):
        """Перестроение текста истории"""
        self.history_text.config(state=tk.NORMAL)
        self.history_text.delete('1.0', tk.END)
        for entry in self.es.history:
            if entry['confidence'] > 0:
                ans_text = "Да"
            elif entry['confidence'] < 0:
                ans_text = "Нет"
            else:
                ans_text = "Не знаю"
            self.history_text.insert(tk.END,
                                     f"• {entry['question']}\n"
                                     f"  Ответ: {ans_text} (КУ = {entry['confidence']:+d})\n\n")
        self.history_text.config(state=tk.DISABLED)

    def _finish_consultation(self):
        """Завершение консультации"""
        self.consultation_active = False
        self.btn_answer.config(state=tk.DISABLED)
        self.btn_start.config(state=tk.NORMAL)
        self.btn_start.config(text="Новая консультация")

        sorted_h = sorted(self.kb.hypotheses,
                          key=lambda h: h['current'], reverse=True)
        top = sorted_h[0]
        self.lbl_question.config(text="Консультация завершена")
        self.lbl_result.config(
            text=f"Рекомендация: {top['name']} ({top['current']*100:.1f}%)",
            foreground='#2a7f2a')
        messagebox.showinfo("Результат",
                            f"Рекомендация: {top['name']}\n"
                            f"Вероятность: {top['current']*100:.2f}%")

    def save_report(self):
        """Сохранение отчёта о консультации"""
        if not self.es:
            return
        filename = filedialog.asksaveasfilename(
            title="Сохранить отчёт",
            defaultextension=".txt",
            filetypes=[("Текстовые файлы", "*.txt")]
        )
        if not filename:
            return

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("ОТЧЁТ О КОНСУЛЬТАЦИИ\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"База знаний: {self.kb.filename}\n")
                f.write(f"Описание: {self.kb.description}\n\n")
                f.write("ИСТОРИЯ ОТВЕТОВ:\n" + "-" * 60 + "\n")
                for entry in self.es.history:
                    if entry['confidence'] > 0:
                        ans = "Да"
                    elif entry['confidence'] < 0:
                        ans = "Нет"
                    else:
                        ans = "Не знаю"
                    f.write(f"• {entry['question']}\n")
                    f.write(f"  Ответ: {ans} (КУ = {entry['confidence']:+d})\n\n")

                f.write("\nИТОГОВЫЕ ВЕРОЯТНОСТИ:\n" + "-" * 60 + "\n")
                sorted_h = sorted(self.kb.hypotheses,
                                  key=lambda h: h['current'], reverse=True)
                for h in sorted_h:
                    f.write(f"  {h['name']}: {h['current']*100:.2f}%\n")

                f.write("\n" + "=" * 60 + "\n")
                f.write(f"РЕКОМЕНДАЦИЯ: {sorted_h[0]['name']} "
                        f"({sorted_h[0]['current']*100:.2f}%)\n")

            messagebox.showinfo("Успех", f"Отчёт сохранён:\n{filename}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить отчёт:\n{e}")

    def show_about(self):
        """Окно «О программе»"""
        messagebox.showinfo(
            "О программе",
            "Экспертная система подбора автомобиля\n"
            "Лабораторная работа №2\n\n"
            "Реализация байесовского вывода\n"
            "с расчётом цены свидетельств.\n\n"
            "© 2026"
        )


# ============================================================
# ТОЧКА ВХОДА
# ============================================================
def main():
    # Настройка кодировки для консоли (на всякий случай)
    try:
        if sys.stdout:
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    root = tk.Tk()
    app = ExpertSystemApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()