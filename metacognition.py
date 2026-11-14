"""Equal-variance SDT metrics adapted from the author-provided reference.
Maniscalco and Lau (2012), DOI:10.1016/j.concog.2011.09.021.
AUC-ratio: criterion projection in Rahnev (2025), DOI:10.1038/s41467-025-56117-0.
"""
import numpy as np
from scipy import stats
from scipy.optimize import minimize
from scipy.special import log_ndtr
N_RATINGS = 7
MIN_ABS_D_PRIME = 0.01
META_D_MAX_ITERATIONS = 500

def calculate_d_prime(hits, misses, fas, crs):
    """计算d'（log-linear correction，抗极端正确率）"""
    counts = np.asarray([hits, misses, fas, crs], dtype=float)
    if not np.all(np.isfinite(counts)) or np.any(counts < 0):
        raise ValueError("SDT计数必须为有限非负数")
    if hits + misses == 0 or fas + crs == 0:
        return np.nan
    hit_rate = (hits + 0.5) / (hits + misses + 1)
    fa_rate = (fas + 0.5) / (fas + crs + 1)
    return float(stats.norm.ppf(hit_rate) - stats.norm.ppf(fa_rate))


def calculate_auc2_mannwhitney(confidence, correct):
    """使用Mann-Whitney U统计量计算AUC2（全对/全错时返回NaN）"""
    confidence = np.asarray(confidence, dtype=float)
    correct = np.asarray(correct, dtype=float)
    if confidence.ndim != 1 or correct.shape != confidence.shape:
        raise ValueError("confidence与correct必须为等长一维数组")
    valid = np.isfinite(confidence) & np.isin(correct, [0, 1])
    confidence, correct = confidence[valid], correct[valid].astype(bool)

    correct_conf = confidence[correct]
    incorrect_conf = confidence[~correct]

    # 若没有correct或incorrect样本，AUC2不可定义
    if len(correct_conf) == 0 or len(incorrect_conf) == 0:
        return np.nan

    n_correct = len(correct_conf)
    n_incorrect = len(incorrect_conf)

    all_conf = np.concatenate([correct_conf, incorrect_conf])
    all_correct = np.concatenate([np.ones(n_correct), np.zeros(n_incorrect)])

    ranks = stats.rankdata(all_conf)
    correct_rank_sum = np.sum(ranks[all_correct == 1])

    u_statistic = correct_rank_sum - n_correct * (n_correct + 1) / 2
    auc2 = u_statistic / (n_correct * n_incorrect)

    return auc2


def prepare_SDT_data(stimulus, response, confidence):
    """
    准备SDT分析所需的数据格式（固定信心等级1-7，保留未使用等级为0计数）
    stimulus: 真实状态（ExpectedAnswer，0/1）
    response : 被试反应（UserAnswer，0/1）
    confidence: 1-7
    """
    stimulus = np.asarray(stimulus, dtype=float)
    response = np.asarray(response, dtype=float)
    confidence = np.asarray(confidence, dtype=float)
    if stimulus.ndim != 1 or response.shape != stimulus.shape or confidence.shape != stimulus.shape:
        raise ValueError("刺激、反应与信心必须为等长一维数组")
    if (not np.all(np.isin(stimulus, [0, 1]))
            or not np.all(np.isin(response, [0, 1]))
            or not np.all(np.isin(confidence, np.arange(1, N_RATINGS + 1)))):
        raise ValueError("刺激/反应仅允许0/1，信心仅允许整数1..7")
    # R1: 高信心到低信心；R2: 低信心到高信心。
    indices = np.where(response == 0, N_RATINGS - confidence,
                       N_RATINGS + confidence - 1).astype(int)
    nR_S1 = np.bincount(indices[stimulus == 0], minlength=2 * N_RATINGS).astype(float)
    nR_S2 = np.bincount(indices[stimulus == 1], minlength=2 * N_RATINGS).astype(float)
    return nR_S1, nR_S2


def _validate_sdt_counts(nR_S1, nR_S2):
    a, b = np.asarray(nR_S1, dtype=float), np.asarray(nR_S2, dtype=float)
    if a.ndim != 1 or b.shape != a.shape or len(a) < 4 or len(a) % 2:
        raise ValueError("SDT计数须为两个等长、偶数长度的一维数组，至少两个信心等级")
    if not np.all(np.isfinite([a, b])) or np.any(a < 0) or np.any(b < 0):
        raise ValueError("SDT计数必须为有限非负数")
    return a, b, len(a) // 2


def _correct_incorrect_counts(a, b, nratings):
    """将两种反应均转为信心从低到高，再合并正确/错误计数。"""
    correct = a[:nratings][::-1] + b[nratings:]
    incorrect = b[:nratings][::-1] + a[nratings:]
    return correct, incorrect


def _auc2_from_counts(correct, incorrect):
    if correct.sum() == 0 or incorrect.sum() == 0:
        return np.nan
    lower_incorrect = np.cumsum(incorrect) - incorrect
    return float(np.sum(correct * (lower_incorrect + 0.5 * incorrect))
                 / (correct.sum() * incorrect.sum()))


def _sdt_parameters(a, b, nratings):
    # 每格加1/(2K)，每种反应共加0.5；与d'的Hautus修正一致。
    adjusted_a = a + 1 / (2 * nratings)
    adjusted_b = b + 1 / (2 * nratings)
    far = np.cumsum(adjusted_a[::-1])[::-1][1:] / adjusted_a.sum()
    hr = np.cumsum(adjusted_b[::-1])[::-1][1:] / adjusted_b.sum()
    z_hr, z_far = stats.norm.ppf(hr), stats.norm.ppf(far)
    d_prime = z_hr[nratings - 1] - z_far[nratings - 1]
    criteria = -0.5 * (z_hr + z_far)
    return adjusted_a, adjusted_b, float(d_prime), criteria


def _normal_log_interval(lower, upper):
    """标准正态区间概率的对数，尾部用log-CDF/log-SF避免相减精度损失。"""
    lower, upper = np.broadcast_arrays(lower, upper)
    right_tail = lower > 0
    larger = np.where(right_tail, log_ndtr(-lower), log_ndtr(upper))
    smaller = np.where(right_tail, log_ndtr(-upper), log_ndtr(lower))
    with np.errstate(divide='ignore', invalid='ignore'):
        return larger + np.log(-np.expm1(np.minimum(smaller - larger, 0)))


def _meta_d_negative_log_likelihood(parameters, a, b, nratings, d_prime, criterion):
    """条件于刺激和已经作出的R1/R2选择，拟合全部信心类别的多项似然。"""
    meta_d = parameters[0]
    thresholds = np.r_[-np.inf, parameters[1:nratings], 0,
                       parameters[nratings:], np.inf]
    if np.any(np.diff(thresholds) <= 0):
        return 1e100
    # 固定相对决策阈值c/d'；将meta模型的决策阈值平移到0。
    shift = meta_d * criterion / d_prime
    means = [-meta_d / 2 - shift, meta_d / 2 - shift]
    nll = 0.0
    for counts, mean in zip((a, b), means):
        log_mass = _normal_log_interval(thresholds[:-1] - mean,
                                       thresholds[1:] - mean)
        log_response = np.repeat([log_ndtr(-mean), log_ndtr(mean)], nratings)
        nll -= np.dot(counts, log_mass - log_response)
    return float(nll) if np.isfinite(nll) else 1e100


def fit_meta_d_mle(nR_S1, nR_S2):
    """等方差SDT条件MLE；每组仅优化一次，返回估计与明确的终态。"""
    a, b, nratings = _validate_sdt_counts(nR_S1, nR_S2)
    fit = dict(meta_d=np.nan, m_ratio=np.nan, d_prime=np.nan,
               status='missing_stimulus_class', optimizer_success=False,
               iterations=0, message='', negative_log_likelihood=np.nan)
    if a.sum() == 0 or b.sum() == 0:
        return fit
    adjusted_a, adjusted_b, d_prime, criteria = _sdt_parameters(a, b, nratings)
    fit['d_prime'] = d_prime
    correct, incorrect = _correct_incorrect_counts(a, b, nratings)
    if np.count_nonzero(correct + incorrect) < 2:
        fit['status'] = 'constant_confidence'
        return fit
    if correct.sum() == 0 or incorrect.sum() == 0:
        fit['status'] = 'missing_correctness_class'
        return fit
    if (a[:nratings].sum() + b[:nratings].sum() == 0
            or a[nratings:].sum() + b[nratings:].sum() == 0):
        fit['status'] = 'missing_response_class'
        return fit
    if abs(d_prime) <= MIN_ABS_D_PRIME:
        fit['status'] = 'd_prime_near_zero'
        return fit

    criterion = criteria[nratings - 1]
    relative_criteria = np.delete(criteria, nratings - 1) - criterion
    initial = np.r_[d_prime, relative_criteria]
    bounds = [(-10, 10)] + [(-20, -1e-5)] * (nratings - 1) + [(1e-5, 20)] * (nratings - 1)
    constraints = {'type': 'ineq', 'fun': lambda x: np.diff(x[1:]) - 1e-5}
    optimized = minimize(
        _meta_d_negative_log_likelihood, initial,
        args=(adjusted_a, adjusted_b, nratings, d_prime, criterion),
        method='SLSQP', bounds=bounds, constraints=constraints,
        options={'maxiter': META_D_MAX_ITERATIONS, 'ftol': 1e-9},
    )
    fit.update(optimizer_success=bool(optimized.success), iterations=int(optimized.nit),
               message=str(optimized.message))
    if not optimized.success or not np.isfinite(optimized.fun) or optimized.fun >= 1e99:
        fit['status'] = 'optimizer_failed'
        return fit
    if np.any(constraints['fun'](optimized.x) < -1e-7):
        fit['status'] = 'invalid_threshold_order'
        return fit
    if abs(optimized.x[0]) >= 10 - 1e-4 or np.any(abs(optimized.x[1:]) >= 20 - 1e-4):
        fit['status'] = 'parameter_at_numerical_bound'
        return fit
    fit.update(meta_d=float(optimized.x[0]), m_ratio=float(optimized.x[0] / d_prime),
               status='ok', negative_log_likelihood=float(optimized.fun), criterion=float(criterion), relative_criteria=optimized.x[1:].tolist())
    return fit


def calculate_meta_d_fast(nR_S1, nR_S2):
    """兼容原函数名，使用条件最大似然估计meta-d'。"""
    return fit_meta_d_mle(nR_S1, nR_S2)['meta_d']


def calculate_expected_auc_sdt(nR_S1, nR_S2):
    """由观测d'与全部决策/信心阈值推导七级Type-2 AUC期望。

    采用Rahnev的阈值投影方法，保持原刺激类别比例与信心分箱；
    先计算各刺激下的响应×信心概率，再将其汇总为正确/错误信心分布。
    """
    a, b, nratings = _validate_sdt_counts(nR_S1, nR_S2)
    if a.sum() == 0 or b.sum() == 0:
        return np.nan
    _, _, d_prime, criteria = _sdt_parameters(a, b, nratings)
    edges = np.r_[-np.inf, criteria, np.inf]
    predicted = []
    for mean, total in [(-d_prime / 2, a.sum()), (d_prime / 2, b.sum())]:
        probabilities = np.exp(_normal_log_interval(edges[:-1] - mean, edges[1:] - mean))
        predicted.append(probabilities * total)
    correct, incorrect = _correct_incorrect_counts(*predicted, nratings)
    return _auc2_from_counts(correct, incorrect)


