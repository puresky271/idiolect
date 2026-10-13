"""精确检验的唯一实现（标准库，无 scipy）。

`tools/gates/accept_check.py` 的锚点密度合并泊松检验与 `multiturn_probe` 的漂移判定
都从这里取实现；family 级配对的符号检验是同一个条件二项检验在曝光量相等时的特例
（p0 = 0.5），所以也走这里，不另写第二套口径。
"""
from __future__ import annotations

from math import comb


def poisson_decrease_pvalue(hits_b: int, chars_b: int, hits_a: int, chars_a: int) -> float:
    """单侧精确检验：after 的率是否显著低于 before。

    条件检验（两泊松率比较的标准精确做法）：零假设两臂率相同，
    给定总命中 N = hits_a + hits_b，after 的命中数 ~ Binomial(N, p0)，
    p0 = chars_a / (chars_a + chars_b)（按曝光量加权）。
    """
    n = hits_a + hits_b
    if n == 0 or not chars_a or not chars_b:
        return 1.0
    p0 = chars_a / (chars_a + chars_b)
    return sum(comb(n, k) * p0 ** k * (1 - p0) ** (n - k) for k in range(hits_a + 1))


def critical_drop(hits_b: int, chars_b: int, chars_a: int, alpha: float) -> float | None:
    """当前样本量下能判退化的最小相对降幅；任何降幅都不显著时返回 None（无结论）。"""
    rate_b = hits_b / chars_b if chars_b else 0.0
    if not rate_b:
        return None
    best: int | None = None
    for k in range(hits_b + 1):
        if poisson_decrease_pvalue(hits_b, chars_b, k, chars_a) < alpha:
            best = k
        else:
            break
    if best is None:
        return None
    return 1.0 - (best / chars_a) / rate_b


def sign_test(improved: int, regressed: int, alpha: float = 0.05) -> dict:
    """family 级配对符号检验（单侧：after 是否显著更差 / 更好）。

    平局不进 N。返回两个方向的 p 值、当前 N 下能判显著所需的最少同向 family 数，
    以及 `conclusive`：N 太小（任何结果都不可能显著）时为 False，调用方必须报
    「无结论」而不是 PASS。
    """
    n = improved + regressed
    # P(Bin(n, 0.5) <= improved)：退化方向；对称地 P(Bin <= regressed)：改善方向
    p_regression = poisson_decrease_pvalue(regressed, 1, improved, 1) if n else 1.0
    p_improvement = poisson_decrease_pvalue(improved, 1, regressed, 1) if n else 1.0
    min_n = 0
    while min_n < 64:
        min_n += 1
        if poisson_decrease_pvalue(min_n, 1, 0, 1) < alpha:   # 全部同向时的 p = 0.5^n
            break
    return {"n": n, "improved": improved, "regressed": regressed,
            "p_regression": p_regression, "p_improvement": p_improvement,
            "min_families_for_significance": min_n,
            "conclusive": n >= min_n, "alpha": alpha}


__all__ = ["critical_drop", "poisson_decrease_pvalue", "sign_test"]
