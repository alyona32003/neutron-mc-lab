"""
Валидация нейтронной MC-модели.

Каждый тест проверяет одно физическое утверждение:
    1. k_inf однородной среды с отражателями = νΣf / Σa
    2. чистый поглотитель → k = 0
    3. чистый рассеиватель без деления → k = 0
    4. деление без рассеяния → k = νΣf / Σa (проверка p_fission)
    5. тонкий слой без отражателей → k_eff < k_inf (утечка)

Запуск:
    python -m neutron_mc.validation
"""

import numpy as np
from .model import Material, Layer, Geometry, run_mc




# ------------------------- общие параметры -------------------------

N_NEUTRONS   = 1000       # нейтронов в поколении
BATCHES      = 50         # всего поколений
INACTIVE     = 15         # неактивных батчей
SEEDS        = [1, 2, 3, 4, 5]
NU_DEFAULT   = 2.5









# ------------------------- вспомогательные -------------------------

def run_one_case(material, length, left_refl, right_refl, seed):
    """Один прогон run_mc с одним seed, возвращает k_eff."""
    lay = Layer("test", material, length)
    geom = Geometry([lay],
                    left_reflective=left_refl,
                    right_reflective=right_refl)
    k_eff, k_std, k_hist, flux, mesh_edges = run_mc(
        geom,
        N=N_NEUTRONS,
        batches=BATCHES,
        inactive=INACTIVE,
        mesh=30,
        seed=seed,
    )
    return k_eff




def run_multi_seed(material, length, left_refl, right_refl):
    """Прогон по всем seeds, возвращает (mean, err) с честной ошибкой по seeds."""
    ks = []
    for s in SEEDS:
        ks.append(run_one_case(material, length, left_refl, right_refl, s))

    arr = np.array(ks)
    mean = arr.mean()
    std = arr.std(ddof=1) if len(arr) > 1 else 0.0
    err = std / (len(arr) ** 0.5)
    return mean, err, arr









# ------------------------- тесты -------------------------

def test_1_k_inf_uniform():
    """
    Однородная среда, оба отражателя, толстый слой.
    Теория: k_inf = νΣf / Σa.
    """
    print()
    print("=" * 78)
    print("ТЕСТ 1: k_inf однородной среды с отражателями")
    print("=" * 78)
    print(f"{'материал':15s}  {'k_theory':>10s}  {'k_mc':>10s}  {'±':>8s}  {'diff':>9s}  {'ok':>4s}")
    print("-" * 78)

    cases = [
        ("fuel-weak",   0.03,  0.30, 0.015),
        ("fuel-strong", 0.03,  0.30, 0.06),
        ("moderator",   0.001, 0.60, 0.0),
        ("absorber",    0.20,  0.05, 0.0),
    ]

    L = 300.0
    all_ok = True

    for name, sa, ss, nsf in cases:
        m = Material(name=name, sigma_a=sa, sigma_s=ss, nu_sigma_f=nsf, nu=NU_DEFAULT)
        k_theory = nsf / sa if sa > 0 else 0.0

        k_mc, k_err, _ = run_multi_seed(m, L, True, True)

        tol = max(3.0 * k_err, 0.05 * abs(k_theory), 0.02)
        ok = abs(k_mc - k_theory) < tol
        if not ok:
            all_ok = False

        status = "OK" if ok else "FAIL"
        print(f"{name:15s}  {k_theory:>10.4f}  {k_mc:>10.4f}  {k_err:>8.4f}  {k_mc - k_theory:>+9.4f}  {status:>4s}")

    return all_ok




def test_2_pure_absorber():
    """
    Чистый поглотитель (νΣf = 0). Теория: k = 0.
    """
    print()
    print("=" * 78)
    print("ТЕСТ 2: чистый поглотитель → k = 0")
    print("=" * 78)

    m = Material(name="absorber", sigma_a=0.2, sigma_s=0.05,
                 nu_sigma_f=0.0, nu=NU_DEFAULT)
    k_mc, k_err, ks = run_multi_seed(m, 50.0, True, True)

    ok = abs(k_mc) < 0.01
    status = "OK" if ok else "FAIL"
    print(f"k_mc = {k_mc:.4f} ± {k_err:.4f}, ожидание 0.0  [{status}]")
    print(f"   значения по seeds: {[round(float(v), 4) for v in ks]}")
    return ok




def test_3_pure_scatterer():
    """
    Чистый рассеиватель без деления. Теория: k = 0.
    """
    print()
    print("=" * 78)
    print("ТЕСТ 3: чистый рассеиватель → k = 0")
    print("=" * 78)

    m = Material(name="scatterer", sigma_a=0.001, sigma_s=0.6,
                 nu_sigma_f=0.0, nu=NU_DEFAULT)
    k_mc, k_err, ks = run_multi_seed(m, 50.0, True, True)

    ok = abs(k_mc) < 0.01
    status = "OK" if ok else "FAIL"
    print(f"k_mc = {k_mc:.4f} ± {k_err:.4f}, ожидание 0.0  [{status}]")
    return ok




def test_4_no_scattering():
    """
    Делящаяся среда без рассеяния (Σs = 0).
    Каждый нейтрон поглощается в точке рождения.
    p_fission = (νΣf / ν) / Σa = Σf / Σa.
    Теория: k_inf = νΣf / Σa.
    """
    print()
    print("=" * 78)
    print("ТЕСТ 4: деление без рассеяния → k = νΣf / Σa (проверка p_fission)")
    print("=" * 78)

    sa = 0.03
    nsf = 0.06
    m = Material(name="fissile-no-scat",
                 sigma_a=sa, sigma_s=0.0,
                 nu_sigma_f=nsf, nu=NU_DEFAULT)

    k_theory = nsf / sa
    print(f"p_fission = Σf/Σa = {m.p_fission:.4f}")
    print(f"k_theory  = νΣf/Σa = {k_theory:.4f}")

    k_mc, k_err, _ = run_multi_seed(m, 100.0, True, True)

    tol = max(3.0 * k_err, 0.05 * abs(k_theory), 0.03)
    ok = abs(k_mc - k_theory) < tol
    status = "OK" if ok else "FAIL"
    print(f"k_mc      = {k_mc:.4f} ± {k_err:.4f}  [{status}]")
    return ok




def test_5_leakage():
    """
    Тонкий слой без отражателей → k_eff < k_inf из-за утечки.
    """
    print()
    print("=" * 78)
    print("ТЕСТ 5: тонкий слой без отражателей → k_eff < k_inf")
    print("=" * 78)

    sa = 0.03
    nsf = 0.06
    m = Material(name="fuel-strong", sigma_a=sa, sigma_s=0.30,
                 nu_sigma_f=nsf, nu=NU_DEFAULT)
    k_inf = nsf / sa

    k_bare, k_err, _ = run_multi_seed(m, 30.0, False, False)

    ok = k_bare < (k_inf - 0.1)
    status = "OK" if ok else "FAIL"
    print(f"k_inf (теория)     = {k_inf:.4f}")
    print(f"k_eff (bare 30 см) = {k_bare:.4f} ± {k_err:.4f}  [{status}]")
    return ok









# ------------------------- main -------------------------

def main():
    print()
    print("#" * 78)
    print("# ВАЛИДАЦИЯ НЕЙТРОННОЙ MC-МОДЕЛИ")
    print("#" * 78)
    print(f"# Параметры: N={N_NEUTRONS}, batches={BATCHES}, "
          f"inactive={INACTIVE}, seeds={SEEDS}")

    results = {}
    results["1. k_inf однородной среды"]        = test_1_k_inf_uniform()
    results["2. чистый поглотитель"]            = test_2_pure_absorber()
    results["3. чистый рассеиватель"]           = test_3_pure_scatterer()
    results["4. деление без рассеяния"]         = test_4_no_scattering()
    results["5. утечка из тонкого слоя"]        = test_5_leakage()

    print()
    print("=" * 78)
    print("ИТОГ")
    print("=" * 78)

    passed = 0
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {name:35s}  {status}")
        if ok:
            passed += 1

    total = len(results)
    print()
    print(f"  Пройдено {passed} из {total}")
    print()


if __name__ == "__main__":
    main()