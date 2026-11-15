"""
GUI для расчёта нейтронного Монте-Карло.

Вкладки:
- Расчёт:    параметры и запуск
- Геометрия: конструктор слоёв + визуализация + границы
- Справка:   пояснения
"""

import matplotlib
matplotlib.use("TkAgg")
# backend ДО импорта pyplot (внутри model)

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from .model import (
    Material, Layer, Geometry,
    run_mc, plot_k_history, plot_flux,
)




# текст вкладки «Справка»
HELP_TEXT = """
ПЗ
════════════════════════
Данный код является попыткой описания активной зоны реактора
через представление её в виде одномерной активной гетерогенной зоны.
Проекция рассматривается как половина радиальной развёртки
(влево — аналогичная зона).

Проверка реалистичности расчёта не проводится, поскольку в модели
имеется множество упущений. Однако физичность получаемых результатов
обоснована основными законами переноса нейтронов и взаимодействия
нейтронов с веществом.

════════════════════════
ВКЛАДКА «ГЕОМЕТРИЯ»
════════════════════════

В верхней трети — визуализация зоны: цветные полосы-слои,
ось X подстраивается под полную длину.

Ниже — конструктор слоёв. У каждого слоя задаются:
    name        — название (латиницей)
    L, см       — толщина
    σa          — макроскопическое сечение поглощения, 1/см
    σs          — макроскопическое сечение рассеяния, 1/см
    νΣf         — ν · Σf, произведение выхода на сечение деления
    ν           — среднее число нейтронов на акт деления

Кнопки ↑ и ↓ справа меняют слой местами с соседом сверху/снизу.
Кнопка «+ добавить слой» добавляет слой справа.
Кнопка «Удалить» убирает слой; оставшиеся сдвигаются влево.
Должен остаться хотя бы один слой.

ГРАНИЦЫ ЗОНЫ
    слева  — отражатель (зеркало, синяя линия)
           или вакуум (утечка, красный пунктир)
    справа — отражатель (зеркало, синяя линия)
           или вакуум (утечка, красный пунктир)

    По умолчанию: отражатель слева, вакуум справа.

════════════════════════
ПАРАМЕТРЫ РАСЧЁТА
════════════════════════

N историй
    Сколько нейтронов в каждом поколении.
    Больше N — точнее, но дольше.
    Рекомендуется: 1000–10000.

Батчей
    Сколько поколений прогнать.
    k_eff усредняется по активным.
    Рекомендуется: 50–200.

Неактивных
    Сколько первых батчей отбросить.
    Нужно, чтобы источник сошёлся.
    Рекомендуется: 20–30% от батчей.

Ячеек сетки
    На сколько ячеек бьётся зона.
    Больше — детальнее φ(x), но шумнее.
    Рекомендуется: 100–200.

Seed
    Зерно генератора случайных чисел.
    Один seed — один результат.
    Меняйте для проверки разброса.

════════════════════════
РЕЗУЛЬТАТЫ
════════════════════════

k_eff
    Эффективный коэффициент размножения.
    k > 1 — надкритичная зона.
    k < 1 — подкритичная зона.
    k = 1 — критичная зона.

k_std
    Стандартная ошибка среднего.
    Чем меньше — тем точнее результат.

График k_eff
    Ломаная — k по батчам.
    Красная линия — среднее.
    Серая зона — неактивные батчи.

График φ(x)
    Поток по длине зоны.

════════════════════════
ГЕОМЕТРИЯ ПО УМОЛЧАНИЮ
════════════════════════

    fuel-weak   — топливо       (15 см)
    moderator   — замедлитель   (10 см)
    absorber    — поглотитель   ( 1 см)
    fuel-strong — топливо       (80 см)
"""




# ------------------------- состояние геометрии -------------------------

geometry_state = {
    "layers": [],
    "layer_vars": [],
    "left_reflective": True,
    "right_reflective": False,
}




# общее состояние расчёта
state = {
    "result": None,
    "running": False,
    "geom": None,
    "inactive_used": 30,     # ИСПРАВЛЕНИЕ: с каким inactive считали
}




# ------------------------- данные по умолчанию -------------------------

def default_layers_data():
    return [
    {"name": "VVER-UO2",    "length": 100.0, "sigma_a": 1.06,   "sigma_s": 0.30,  "nu_sigma_f": 1.62, "nu": 2.43},
    {"name": "H2O",         "length": 30.0,  "sigma_a": 0.0222, "sigma_s": 6.0,   "nu_sigma_f": 0.0,  "nu": 2.43},
    {"name": "Fe",   "length": 10.0,  "sigma_a": 0.216,  "sigma_s": 0.185, "nu_sigma_f": 0.0,  "nu": 2.43},
]




def build_geometry_from_state():
    """Собрать объект Geometry из текущего состояния слоёв."""
    layers = []
    for d in geometry_state["layers"]:
        mat = Material(
            name=d["name"],
            sigma_a=d["sigma_a"],
            sigma_s=d["sigma_s"],
            nu_sigma_f=d["nu_sigma_f"],
            nu=d["nu"],
        )
        layers.append(Layer(d["name"], mat, d["length"]))

    return Geometry(
        layers,
        left_reflective=geometry_state["left_reflective"],
        right_reflective=geometry_state["right_reflective"],
    )




def save_geometry_from_vars():
    """Считать значения из полей ввода и обновить geometry_state['layers']."""
    for i, vars_this in enumerate(geometry_state["layer_vars"]):
        if i >= len(geometry_state["layers"]):
            break
        layer = geometry_state["layers"][i]

        try:
            name = vars_this["name"].get()
            if name:
                layer["name"] = name
        except Exception:
            pass

        for key in ["length", "sigma_a", "sigma_s", "nu_sigma_f", "nu"]:
            try:
                layer[key] = float(vars_this[key].get())
            except (ValueError, KeyError):
                pass









# ------------------------- чтение параметров расчёта -------------------------

def read_params():
    params = {}
    try:
        params["N"]        = int(n_entry.get())
        params["batches"]  = int(batches_entry.get())
        params["inactive"] = int(inactive_entry.get())
        params["mesh"]     = int(mesh_entry.get())
        params["seed"]     = int(seed_entry.get())
    except ValueError:
        messagebox.showerror("Ошибка", "Введите целые числа")
        return None

    if params["N"] <= 0:
        messagebox.showerror("Ошибка", "N должно быть > 0")
        return None
    if params["batches"] <= 0:
        messagebox.showerror("Ошибка", "batches должно быть > 0")
        return None
    if params["inactive"] < 0:
        messagebox.showerror("Ошибка", "inactive ≥ 0")
        return None
    if params["inactive"] >= params["batches"]:
        messagebox.showerror("Ошибка", "inactive < batches")
        return None
    if params["mesh"] <= 0:
        messagebox.showerror("Ошибка", "mesh должно быть > 0")
        return None
    return params









# ------------------------- расчёт в фоне -------------------------

def run_worker(params):
    t0 = time.time()

    def on_progress(current, total):
        try:
            root.after(0, lambda: on_progress_ui(current, total))
        except tk.TclError:
            return

    k_eff, k_std, k_hist, flux, mesh_edges = run_mc(
        state["geom"],
        N=params["N"],
        batches=params["batches"],
        inactive=params["inactive"],
        mesh=params["mesh"],
        seed=params["seed"],
        progress_callback=on_progress,
    )

    dt = time.time() - t0
    state["result"] = (k_eff, k_std, k_hist, flux, mesh_edges)

    try:
        root.after(0, lambda: on_run_done(k_eff, k_std, dt))
    except tk.TclError:
        return




def on_run_click():
    if state["running"]:
        return

    save_geometry_from_vars()
    try:
        state["geom"] = build_geometry_from_state()
    except Exception as e:
        messagebox.showerror("Геометрия", f"Некорректная геометрия: {e}")
        return

    params = read_params()
    if params is None:
        return

    # ИСПРАВЛЕНИЕ: запоминаем, с каким inactive считаем
    state["inactive_used"] = params["inactive"]

    state["running"] = True
    run_button.config(state="disabled")
    plots_button.config(state="disabled")

    progress_bar["value"] = 0
    progress_bar["maximum"] = params["batches"]
    progress_label.config(text=f"0 / {params['batches']}")

    status_label.config(text="Считаем...", foreground="blue")
    result_label.config(text="")

    th = threading.Thread(target=run_worker, args=(params,), daemon=True)
    th.start()




def on_progress_ui(current, total):
    progress_bar["value"] = current
    progress_bar["maximum"] = total
    progress_label.config(text=f"{current} / {total}")




def on_run_done(k_eff, k_std, dt):
    state["running"] = False
    run_button.config(state="normal")
    plots_button.config(state="normal")
    status_label.config(text="Готово", foreground="green")
    result_label.config(
        text=f"k_eff = {k_eff:.5f} ± {k_std:.5f}\nВремя: {dt:.2f} с"
    )









# ------------------------- показ графиков -------------------------

def show_in_window(fig, title):
    win = tk.Toplevel(root)
    win.title(title)
    win.geometry("900x500")
    win.minsize(600, 400)

    canvas = FigureCanvasTkAgg(fig, master=win)

    toolbar = NavigationToolbar2Tk(canvas, win)
    toolbar.update()

    canvas.get_tk_widget().pack(fill="both", expand=True)
    win.after(100, canvas.draw)




def on_plots_click():
    if state["result"] is None:
        messagebox.showinfo("Графики", "Сначала посчитайте k_eff")
        return

    k_eff, k_std, k_hist, flux, mesh_edges = state["result"]

    # ИСПРАВЛЕНИЕ: серая зона — до того inactive, с которым считали
    fig1 = plot_k_history(k_hist, k_eff, k_std,
                          inactive=state["inactive_used"], show=False)
    fig2 = plot_flux(state["geom"], flux, mesh_edges, show=False)

    show_in_window(fig1, "История k_eff")
    show_in_window(fig2, "Поток φ(x)")









# ------------------------- вкладка «Расчёт» -------------------------

def build_run_tab(notebook):
    main_frame = ttk.Frame(notebook, padding=20)
    notebook.add(main_frame, text="Расчёт")

    main_frame.columnconfigure(0, weight=1)
    main_frame.columnconfigure(1, weight=0)
    main_frame.columnconfigure(2, weight=1)
    main_frame.rowconfigure(0, weight=1)
    main_frame.rowconfigure(6, weight=1)

    form = ttk.LabelFrame(main_frame, text="Параметры", padding=15)
    form.grid(row=1, column=1, pady=(0, 10))

    ttk.Label(form, text="N историй:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
    global n_entry
    n_entry = ttk.Entry(form, width=15)
    n_entry.insert(0, "3000")
    n_entry.grid(row=0, column=1, pady=4)

    ttk.Label(form, text="Батчей:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 10))
    global batches_entry
    batches_entry = ttk.Entry(form, width=15)
    batches_entry.insert(0, "100")
    batches_entry.grid(row=1, column=1, pady=4)

    ttk.Label(form, text="Неактивных:").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 10))
    global inactive_entry
    inactive_entry = ttk.Entry(form, width=15)
    inactive_entry.insert(0, "30")
    inactive_entry.grid(row=2, column=1, pady=4)

    ttk.Label(form, text="Ячеек сетки:").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 10))
    global mesh_entry
    mesh_entry = ttk.Entry(form, width=15)
    mesh_entry.insert(0, "120")
    mesh_entry.grid(row=3, column=1, pady=4)

    ttk.Label(form, text="Seed:").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 10))
    global seed_entry
    seed_entry = ttk.Entry(form, width=15)
    seed_entry.insert(0, "42")
    seed_entry.grid(row=4, column=1, pady=4)

    progress_frame = ttk.Frame(main_frame)
    progress_frame.grid(row=2, column=1, pady=(10, 10))

    global progress_bar, progress_label
    progress_bar = ttk.Progressbar(progress_frame, orient="horizontal",
                                   mode="determinate", length=280)
    progress_bar.grid(row=0, column=0)
    progress_label = ttk.Label(progress_frame, text="0 / 0", width=10)
    progress_label.grid(row=0, column=1, padx=(8, 0))

    buttons_frame = ttk.Frame(main_frame)
    buttons_frame.grid(row=3, column=1, pady=(10, 10))

    global run_button, plots_button
    run_button = ttk.Button(buttons_frame, text="Запустить расчёт",
                            command=on_run_click, width=25)
    run_button.grid(row=0, column=0, pady=4)

    plots_button = ttk.Button(buttons_frame, text="Показать графики",
                              command=on_plots_click, width=25)
    plots_button.grid(row=1, column=0, pady=4)

    global status_label, result_label
    status_label = ttk.Label(main_frame, text="Готов к запуску",
                             foreground="gray")
    status_label.grid(row=4, column=1, pady=(10, 4))

    result_label = ttk.Label(main_frame, text="", justify="center")
    result_label.grid(row=5, column=1, pady=4)









# ------------------------- вкладка «Геометрия» -------------------------

def build_geometry_tab(notebook):
    geom_frame = ttk.Frame(notebook, padding=10)
    notebook.add(geom_frame, text="Геометрия")

    geom_frame.rowconfigure(0, weight=1)
    geom_frame.rowconfigure(1, weight=2)
    geom_frame.columnconfigure(0, weight=1)

    # ---------- верх: визуализация ----------
    viz_frame = ttk.LabelFrame(geom_frame, text="Визуализация зоны", padding=5)
    viz_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
    viz_frame.rowconfigure(0, weight=1)
    viz_frame.columnconfigure(0, weight=1)

    global geom_fig, geom_ax, geom_canvas
    geom_fig = Figure(figsize=(8, 2))
    geom_ax = geom_fig.add_subplot(111)
    geom_fig.subplots_adjust(left=0.05, right=0.98, top=0.88, bottom=0.2)

    geom_canvas = FigureCanvasTkAgg(geom_fig, master=viz_frame)
    geom_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    # ---------- низ: конструктор ----------
    layers_outer = ttk.LabelFrame(geom_frame, text="Слои", padding=5)
    layers_outer.grid(row=1, column=0, sticky="nsew")
    layers_outer.rowconfigure(2, weight=1)
    layers_outer.columnconfigure(0, weight=1)

    top_bar = ttk.Frame(layers_outer)
    top_bar.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, 3))
    ttk.Button(top_bar, text="+ добавить слой",
               command=on_add_layer).pack(side="left")

    bounds_bar = ttk.LabelFrame(layers_outer, text="Границы зоны", padding=5)
    bounds_bar.grid(row=1, column=0, columnspan=2, sticky="we", pady=(0, 5))

    global left_refl_var, right_refl_var
    left_refl_var = tk.BooleanVar(value=geometry_state["left_reflective"])
    right_refl_var = tk.BooleanVar(value=geometry_state["right_reflective"])

    ttk.Checkbutton(bounds_bar, text="слева — отражатель",
                    variable=left_refl_var,
                    command=on_boundary_changed).pack(side="left", padx=(5, 25))
    ttk.Checkbutton(bounds_bar, text="справа — отражатель",
                    variable=right_refl_var,
                    command=on_boundary_changed).pack(side="left", padx=5)

    canvas = tk.Canvas(layers_outer, highlightthickness=0)
    scrollbar = ttk.Scrollbar(layers_outer, orient="vertical", command=canvas.yview)
    canvas.grid(row=2, column=0, sticky="nsew")
    scrollbar.grid(row=2, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set)

    global layers_container
    layers_container = ttk.Frame(canvas)
    canvas_window = canvas.create_window((0, 0), window=layers_container, anchor="nw")

    canvas.bind("<Configure>",
                lambda e: canvas.itemconfig(canvas_window, width=e.width))
    layers_container.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    render_geometry_layers()
    draw_geometry_viz()




def render_geometry_layers():
    """Перерисовать список слоёв."""
    for widget in layers_container.winfo_children():
        widget.destroy()
    geometry_state["layer_vars"] = []

    if not geometry_state["layers"]:
        ttk.Label(layers_container,
                  text="Нет слоёв. Нажмите «+ добавить слой»").pack(pady=20)
        return

    for i, layer_data in enumerate(geometry_state["layers"]):
        build_layer_row(i, layer_data)




def build_layer_row(index, layer_data):
    """Одна строка-редактор для слоя."""
    row = ttk.LabelFrame(layers_container, text=f"Слой {index+1}")
    row.pack(fill="x", pady=3, padx=3)

    # две колонки: контент слева, стрелки справа
    row.columnconfigure(0, weight=1)
    row.columnconfigure(1, weight=0)
    row.rowconfigure(0, weight=1)

    vars_this = {}

    # ---------- ЛЕВАЯ КОЛОНКА: поля ----------
    content = ttk.Frame(row)
    content.grid(row=0, column=0, sticky="nsew")

    # --- строка 0: name, L, Удалить ---
    row0 = ttk.Frame(content)
    row0.pack(fill="x", pady=2)

    ttk.Label(row0, text="name:").pack(side="left", padx=(5, 2))
    vars_this["name"] = tk.StringVar(value=layer_data["name"])
    name_entry = ttk.Entry(row0, textvariable=vars_this["name"], width=14)
    name_entry.pack(side="left", padx=2)
    name_entry.bind("<FocusOut>", lambda e: on_length_changed())
    name_entry.bind("<Return>", lambda e: on_length_changed())

    ttk.Label(row0, text="L, см:").pack(side="left", padx=(10, 2))
    vars_this["length"] = tk.StringVar(value=str(layer_data["length"]))
    length_entry = ttk.Entry(row0, textvariable=vars_this["length"], width=8)
    length_entry.pack(side="left", padx=2)
    length_entry.bind("<FocusOut>", lambda e: on_length_changed())
    length_entry.bind("<Return>", lambda e: on_length_changed())

    ttk.Button(row0, text="Удалить",
               command=lambda: on_delete_layer(index)).pack(side="left", padx=(15, 5))

    # --- строка 1: σa, σs, νΣf, ν ---
    row1 = ttk.Frame(content)
    row1.pack(fill="x", pady=2)

    ttk.Label(row1, text="σa:").pack(side="left", padx=(5, 2))
    vars_this["sigma_a"] = tk.StringVar(value=str(layer_data["sigma_a"]))
    ttk.Entry(row1, textvariable=vars_this["sigma_a"], width=8).pack(side="left", padx=2)

    ttk.Label(row1, text="σs:").pack(side="left", padx=(10, 2))
    vars_this["sigma_s"] = tk.StringVar(value=str(layer_data["sigma_s"]))
    ttk.Entry(row1, textvariable=vars_this["sigma_s"], width=8).pack(side="left", padx=2)

    ttk.Label(row1, text="νΣf:").pack(side="left", padx=(10, 2))
    vars_this["nu_sigma_f"] = tk.StringVar(value=str(layer_data["nu_sigma_f"]))
    ttk.Entry(row1, textvariable=vars_this["nu_sigma_f"], width=8).pack(side="left", padx=2)

    ttk.Label(row1, text="ν:").pack(side="left", padx=(10, 2))
    vars_this["nu"] = tk.StringVar(value=str(layer_data["nu"]))
    ttk.Entry(row1, textvariable=vars_this["nu"], width=8).pack(side="left", padx=2)

    # ---------- ПРАВАЯ КОЛОНКА: стрелки ----------
    arrows = tk.Frame(row, bg="white", bd=1, relief="groove")
    arrows.grid(row=0, column=1, sticky="ns", padx=(10, 5), pady=2)

    btn_up = tk.Button(
        arrows, text="↑", font=("Arial", 16, "bold"),
        width=2, height=1, bd=0, relief="flat",
        bg="white", activebackground="#e0e0e0",
        command=lambda: on_move_layer(index, -1),
    )
    btn_up.pack(side="top", fill="both", expand=True)

    btn_down = tk.Button(
        arrows, text="↓", font=("Arial", 16, "bold"),
        width=2, height=1, bd=0, relief="flat",
        bg="white", activebackground="#e0e0e0",
        command=lambda: on_move_layer(index, +1),
    )
    btn_down.pack(side="top", fill="both", expand=True)

    # крайние стрелки неактивны
    if index == 0:
        btn_up.config(state="disabled", disabledforeground="#aaaaaa")
    if index == len(geometry_state["layers"]) - 1:
        btn_down.config(state="disabled", disabledforeground="#aaaaaa")

    geometry_state["layer_vars"].append(vars_this)




def on_add_layer():
    save_geometry_from_vars()
    n = len(geometry_state["layers"]) + 1
    geometry_state["layers"].append({
        "name": f"layer-{n}",
        "length": 10.0,
        "sigma_a": 0.01,
        "sigma_s": 0.1,
        "nu_sigma_f": 0.0,
        "nu": 2.5,
    })
    render_geometry_layers()
    draw_geometry_viz()




def on_delete_layer(index):
    save_geometry_from_vars()

    if len(geometry_state["layers"]) <= 1:
        messagebox.showwarning("Геометрия",
                               "Должен остаться хотя бы один слой")
        return

    if 0 <= index < len(geometry_state["layers"]):
        del geometry_state["layers"][index]

    render_geometry_layers()
    draw_geometry_viz()




def on_move_layer(index, direction):
    """Поменять слой местами с соседом. direction: -1 = вверх, +1 = вниз."""
    save_geometry_from_vars()

    new_index = index + direction
    if new_index < 0 or new_index >= len(geometry_state["layers"]):
        return

    layers = geometry_state["layers"]
    layers[index], layers[new_index] = layers[new_index], layers[index]

    render_geometry_layers()
    draw_geometry_viz()




def on_length_changed():
    save_geometry_from_vars()
    draw_geometry_viz()




def on_boundary_changed():
    """Переключение чекбокса границы."""
    geometry_state["left_reflective"] = left_refl_var.get()
    geometry_state["right_reflective"] = right_refl_var.get()
    draw_geometry_viz()




def draw_geometry_viz():
    """Перерисовать визуализацию зоны и границ."""
    geom_ax.clear()

    layers = geometry_state["layers"]
    if not layers:
        geom_ax.set_xlim(0, 1)
        geom_ax.set_ylim(-0.05, 1.25)
        geom_ax.set_yticks([])
        geom_ax.set_xlabel("Длина зоны, см")
        geom_canvas.draw()
        return

    colors = plt_colors()
    x = 0.0
    for i, layer in enumerate(layers):
        L = layer["length"]
        color = colors[i % len(colors)]

        rect = Rectangle((x, 0), L, 1, facecolor=color, alpha=0.65,
                         edgecolor="black", linewidth=0.6)
        geom_ax.add_patch(rect)

        if L < 5.0:
            fs, rot = 7, 90
        else:
            fs, rot = 9, 0
        geom_ax.text(x + L / 2, 0.5, layer["name"],
                     ha="center", va="center",
                     fontsize=fs, rotation=rot)

        x += L

    L_total = x

    if geometry_state["left_reflective"]:
        geom_ax.plot([0, 0], [0, 1], color="blue", linewidth=3.5)
        geom_ax.text(0, 1.06, "отражатель", ha="left", va="bottom",
                     fontsize=8, color="blue")
    else:
        geom_ax.plot([0, 0], [0, 1], color="red", linewidth=1.8,
                     linestyle="--")
        geom_ax.text(0, 1.06, "вакуум", ha="left", va="bottom",
                     fontsize=8, color="red")

    if geometry_state["right_reflective"]:
        geom_ax.plot([L_total, L_total], [0, 1], color="blue", linewidth=3.5)
        geom_ax.text(L_total, 1.06, "отражатель", ha="right", va="bottom",
                     fontsize=8, color="blue")
    else:
        geom_ax.plot([L_total, L_total], [0, 1], color="red", linewidth=1.8,
                     linestyle="--")
        geom_ax.text(L_total, 1.06, "вакуум", ha="right", va="bottom",
                     fontsize=8, color="red")

    pad = max(1.0, L_total * 0.03)
    geom_ax.set_xlim(-pad, L_total + pad)
    geom_ax.set_ylim(-0.05, 1.25)
    geom_ax.set_yticks([])
    geom_ax.set_xlabel("Длина зоны, см")
    geom_ax.set_title(f"Полная длина: {L_total:.1f} см")

    geom_canvas.draw()




def plt_colors():
    """Палитра для слоёв."""
    import matplotlib.pyplot as plt
    return plt.cm.tab20.colors









# ------------------------- вкладка «Справка» -------------------------

def build_help_tab(notebook):
    help_frame = ttk.Frame(notebook, padding=10)
    notebook.add(help_frame, text="Справка")

    help_frame.rowconfigure(0, weight=1)
    help_frame.columnconfigure(0, weight=1)

    text = tk.Text(help_frame, wrap="word", padx=15, pady=15,
                   font=("Consolas", 10))
    text.grid(row=0, column=0, sticky="nsew")

    scroll = ttk.Scrollbar(help_frame, orient="vertical", command=text.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    text.config(yscrollcommand=scroll.set)

    text.insert("end", HELP_TEXT)
    text.config(state="disabled")









# ------------------------- главное окно -------------------------

def main():
    global root

    geometry_state["layers"] = default_layers_data()
    state["geom"] = build_geometry_from_state()

    root = tk.Tk()
    root.title("Нейтронный Монте-Карло")
    root.geometry("760x720")
    root.minsize(620, 560)

    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)

    notebook = ttk.Notebook(root)
    notebook.grid(row=0, column=0, sticky="nsew")

    build_run_tab(notebook)
    build_geometry_tab(notebook)
    build_help_tab(notebook)

    root.mainloop()









if __name__ == "__main__":
    main()