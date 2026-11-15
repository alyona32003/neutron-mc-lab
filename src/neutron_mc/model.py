import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass




@dataclass
class Material:
    name: str
    sigma_a: float
    sigma_s: float
    nu_sigma_f: float = 0.0
    nu: float = 2.5

    @property
    def sigma_t(self):
        # полное сечение
        return self.sigma_a + self.sigma_s

    @property
    def sigma_f(self):
        # сечение деления
        return self.nu_sigma_f / self.nu

    @property
    def p_fission(self):
        # доля деления
        if self.sigma_a <= 0:
            return 0.0
        return min(1.0, self.sigma_f / self.sigma_a)








@dataclass
class Layer:
    name: str
    material: Material
    length: float




@dataclass
class Geometry:
    layers: list
    left_reflective: bool = True
    right_reflective: bool = False

    def __post_init__(self):
        # толщины слоёв
        lengths = []
        for lay in self.layers:
            lengths.append(lay.length)
        self.lengths = np.array(lengths, dtype=float)

        # координаты стыков
        edges = [0.0]
        total = 0.0
        for L in self.lengths:
            total = total + L
            edges.append(total)
        self.x_edges = np.array(edges)
        self.L = self.x_edges[-1]

    def find_layer(self, x):
        # левее домена
        if x <= 0.0:
            return 0
        # правее домена
        if x >= self.L:
            return len(self.layers) - 1
        # ищем слой
        for i in range(len(self.layers)):
            if x < self.x_edges[i + 1]:
                return i
        return len(self.layers) - 1









# #estimator

def tally_track(x0, x1, mesh_edges, tally):


    # неактивный батч
    if tally is None:
        return
    # нулевой пробег
    if x0 == x1:
        return
    # слева направо
    if x0 > x1:
        tmp = x0
        x0 = x1
        x1 = tmp

    # обрезка по домену
    x_max = mesh_edges[-1]
    if x0 < 0.0:
        x0 = 0.0
    if x0 > x_max:
        x0 = x_max
    if x1 < 0.0:
        x1 = 0.0
    if x1 > x_max:
        x1 = x_max
    if x1 <= x0:
        return

    # ячейка старта
    i0 = len(tally) - 1
    for k in range(len(tally)):
        if x0 < mesh_edges[k + 1]:
            i0 = k
            break

    # ячейка финиша
    i1 = len(tally) - 1
    for k in range(len(tally)):
        if x1 <= mesh_edges[k + 1]:
            i1 = k
            break

    # раскладка по ячейкам
    for i in range(i0, i1 + 1):
        cell_left = mesh_edges[i]
        if x0 > cell_left:
            cell_left = x0
        cell_right = mesh_edges[i + 1]
        if x1 < cell_right:
            cell_right = x1
        # трек прошёл ячейку?
        if cell_right > cell_left:
            tally[i] = tally[i] + (cell_right - cell_left)









#Logika neutron

def simulate_neutron(x, mu, geom, rng, fission_bank, flux_tally, mesh_edges):
    # старт нейтрона
    x = float(x)
    if mu >= 0:
        mu = 1
    else:
        mu = -1

    while True:
        # текущий слой
        layer_idx = geom.find_layer(x)
        mat = geom.layers[layer_idx].material
        sigma_t = mat.sigma_a + mat.sigma_s

        x_left = geom.x_edges[layer_idx]
        x_right = geom.x_edges[layer_idx + 1]

        # расстояние до стенки
        if mu > 0:
            dist_to_boundary = x_right - x
            boundary = x_right
        else:
            dist_to_boundary = x - x_left
            boundary = x_left

        # розыгрыш пробега
        if sigma_t > 0.0:
            xi = rng.random()
            free_path = -np.log(xi) / sigma_t
        else:
            # вакуум: летим до стенки
            free_path = np.inf




 # 1: столкновение
        if free_path < dist_to_boundary:
            # долетел до атома
            x_new = x + mu * free_path
            tally_track(x, x_new, mesh_edges, flux_tally)
            x = x_new

            # проверка by рассеяние
            p_scatter = mat.sigma_s / sigma_t
            if rng.random() < p_scatter:
                # отскок ±1
                if rng.random() < 0.5:
                    mu = 1
                else:
                    mu = -1
                # нейтрон жив
                continue

            # поглощение. проверка by деление?
            if rng.random() < mat.p_fission:
                # сколько нейтронов?
                n_floor = int(np.floor(mat.nu))
                nu_fraction = mat.nu - n_floor
                if rng.random() < nu_fraction:
                    n_neutrons = n_floor + 1
                else:
                    n_neutrons = n_floor
                # вылетели новые
                for _ in range(n_neutrons):
                    if rng.random() < 0.5:
                        new_mu = 1
                    else:
                        new_mu = -1
                    fission_bank.append((x, new_mu))
            # нейтрон bad
            return





# 2: долетел до стенки
        else:
            # вылетел из слоя
            tally_track(x, boundary, mesh_edges, flux_tally)
            x = boundary



# левая стенка
            if boundary <= 0.0 and mu < 0:
                if geom.left_reflective:
                    # отскок влево
                    x = 1e-9
                    mu = -mu
                    continue
                else:
                    # утечка влево
                    return




 # правая стенка
            if boundary >= geom.L and mu > 0:
                if geom.right_reflective:
                    # отскок вправо
                    x = geom.L - 1e-9
                    mu = -mu
                    continue
                else:
                    # утечка вправо
                    return

            # внутренняя граница
            x = boundary + mu * 1e-9
            # сдвиг за домен?
            if x < 0.0:
                x = 1e-9
                mu = -mu
            if x > geom.L:
                x = geom.L - 1e-9
                mu = -mu
            # шаг в новый слой
            continue









#M_C

def run_mc(geom, N=3000, batches=100, inactive=30, mesh=120, seed=42, progress_callback=None):
    rng = np.random.default_rng(seed)

    # greeds
    mesh_edges = np.linspace(0.0, geom.L, mesh + 1)
    flux_tally = np.zeros(mesh)

    # fuel
    fissile_indices = []
    for i in range(len(geom.layers)):
        if geom.layers[i].material.nu_sigma_f > 0.0:
            fissile_indices.append(i)

    # нет топлива — все слои
    if len(fissile_indices) == 0:
        for i in range(len(geom.layers)):
            fissile_indices.append(i)

    # веса by L
    fissile_lengths = []
    for i in fissile_indices:
        fissile_lengths.append(geom.layers[i].length)
    total_length = 0.0
    for L in fissile_lengths:
        total_length = total_length + L
    probs = []
    for L in fissile_lengths:
        probs.append(L / total_length)

    # начальный источник
    source = []
    for _ in range(N):
        layer_i = rng.choice(fissile_indices, p=probs)
        x_left = geom.x_edges[layer_i]
        x_right = geom.x_edges[layer_i + 1]
        x = rng.uniform(x_left, x_right)

        # направление
        if rng.random() < 0.5:
            mu = 1
        else:
            mu = -1
        source.append((x, mu))

    k_hist = []
    active_count = 0

    for b in range(batches):
        fission_bank = []

        # неактивный батч (proverka)
        if b >= inactive:
            flux_tally_current = flux_tally
        else:
            flux_tally_current = None

        # прогон поколения
        for (x, mu) in source:
            simulate_neutron(x, mu, geom, rng, fission_bank,
                             flux_tally_current, mesh_edges)

        # K ###
        n_source = 0
        for _ in source:
            n_source = n_source + 1
        n_fission = len(fission_bank)
        k_batch = n_fission / n_source
        k_hist.append(k_batch)

        # активный батч
        if b >= inactive:
            active_count = active_count + 1

        # прогресс
        if progress_callback is not None:
            progress_callback(b + 1, batches)

        # банк (0)
        if n_fission == 0:
            print("Источник деления опустел — расчёт остановлен.")
            break

        # новое поколение
        new_source = []
        for _ in range(N):
            idx = rng.integers(0, n_fission)
            new_source.append(fission_bank[idx])
        source = new_source

    # страховка
    if active_count == 0:
        active_count = 1

    # нормировка
    for i in range(mesh):
        cell_width = mesh_edges[i + 1] - mesh_edges[i]
        flux_tally[i] = flux_tally[i] / (N * active_count * cell_width)

    # активные батчи
    k_active = []
    for b in range(inactive, len(k_hist)):
        k_active.append(k_hist[b])
    # активных нет
    if len(k_active) == 0:
        k_active = k_hist

    # среднее k
    k_eff = 0.0
    if len(k_active) > 0:
        total = 0.0
        for kv in k_active:
            total = total + kv
        k_eff = total / len(k_active)

    # ошибка среднего
    k_std = 0.0
    if len(k_active) > 1:
        total_sq = 0.0
        for kv in k_active:
            total_sq = total_sq + (kv - k_eff) ** 2
        variance = total_sq / (len(k_active) - 1)
        k_std = (variance ** 0.5) / (len(k_active) ** 0.5)

    return k_eff, k_std, k_hist, flux_tally, mesh_edges









def plot_k_history(k_hist, k_eff, k_std, inactive=30, show=True):



    fig, ax = plt.subplots(figsize=(10, 4))



  
    batches_axis = []
    for b in range(len(k_hist)):
        batches_axis.append(b)



    # ломаная k
    ax.plot(batches_axis, k_hist, '.-', label="k по батчам")




    # среднее k
    ax.axhline(k_eff, color='r', ls='--',
               label=f"k_eff = {k_eff:.5f} ± {k_std:.5f}")


    
    # серая зона
    ax.axvspan(0, inactive, color='gray', alpha=0.2,
               label="неактивные батчи")


    
    ax.set_xlabel("батч")
    ax.set_ylabel("k")
    ax.set_title("История k_eff")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    if show:
        plt.show()
    return fig




def plot_flux(geom, flux, mesh_edges, show=True):


    
    fig, ax = plt.subplots(figsize=(10, 4))




   
    colors = plt.cm.tab20.colors
    for i in range(len(geom.layers)):
        lay = geom.layers[i]
        color_i = colors[i % len(colors)]
        ax.axvspan(geom.x_edges[i], geom.x_edges[i + 1],
                   color=color_i, alpha=0.35, label=lay.name)



   
    x_centers = []
    for i in range(len(flux)):
        xc = 0.5 * (mesh_edges[i] + mesh_edges[i + 1])
        x_centers.append(xc)



    # кривая потока
    ax.plot(x_centers, flux, 'k.-', lw=1.2, label="поток")
    ax.set_xlabel("x, см")
    ax.set_ylabel("φ(x), отн. ед.")
    ax.set_title("Пространственное распределение потока")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    if show:
        plt.show()
    return fig









if __name__ == "__main__":

    # --- топливо ВВЭР  ---
    vver_fuel = Material(name="UO2", sigma_a=1.06, sigma_s=0.30, nu_sigma_f=1.62, nu=2.43)

    # --- теплоноситель/замедлитель ---
    water     = Material(name="H2O",      sigma_a=0.0222, sigma_s=6.0, nu_sigma_f=0.0, nu=2.43)

    # --- защита ---
    iron      = Material(name="Fe",       sigma_a=0.216,  sigma_s=0.185, nu_sigma_f=0.0, nu=2.43)

    geom = Geometry(
        [
            Layer("VVER-fuel",   vver_fuel, 100.0),
            Layer("water",       water,      30.0),
            Layer("iron-shield", iron,       10.0),
        ],
        left_reflective=True,
        right_reflective=False
    )

    # расчёт
    k_eff, k_std, k_hist, flux, mesh_edges = run_mc(
        geom, N=3000, batches=100, inactive=30, mesh=120, seed=42
    )

    print(f"\nИТОГ: k_eff = {k_eff:.5f} ± {k_std:.5f}")
    plot_k_history(k_hist, k_eff, k_std, inactive=30)
    plot_flux(geom, flux, mesh_edges)