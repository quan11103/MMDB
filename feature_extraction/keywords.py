"""
Từ khóa đại diện — từ điển chung toàn dataset.

1. Gộp ứng viên của mọi file, sắp theo tần suất toàn dataset (giới hạn MAX_CANDIDATES).
2. Embedding ứng viên bằng Sentence Transformer, khoảng cách cosine.
3. Agglomerative clustering (average/complete linkage), cắt cây tại 1 - KEYWORD_SIM_THRESHOLD.
4. Mỗi nhóm chọn từ đại diện = thành viên có tần suất toàn dataset cao nhất (bằng nhau -> ngắn hơn).
5. Mỗi file: TF = tổng số lần xuất hiện của các thành viên nhóm; TF-IDF trên từ đại diện.
"""
import math
from collections import Counter

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

import config
from content_text import _is_foreign, load_stopwords

_STOPWORDS = None


def collect(item_candidates: dict) -> tuple:
    """item_candidates: {item_id: {term: count}} -> (danh sách term, tần suất toàn dataset, số term bị cắt)."""
    total = Counter()
    for cand in item_candidates.values():
        total.update(cand)
    terms = [t for t, _ in total.most_common()]
    dropped = max(0, len(terms) - config.MAX_CANDIDATES)
    return terms[:config.MAX_CANDIDATES], total, dropped


def cluster_tree(E: np.ndarray):
    """E: embedding đã chuẩn hóa L2, (n, d). Trả về linkage matrix (dùng lại cho nhiều ngưỡng)."""
    D = np.nan_to_num(pdist(E.astype(np.float64), metric="cosine"), nan=1.0)  # vector 0 -> xa nhất
    return linkage(D, method=config.KEYWORD_LINKAGE)


def cut(Z, n_terms: int, threshold: float) -> np.ndarray:
    if n_terms == 1:
        return np.array([1])
    return fcluster(Z, t=1.0 - threshold, criterion="distance")


def _is_vi_monosyllable(term: str) -> bool:
    """Từ tiếng Việt 1 âm tiết. Ứng viên trùng từ dừng (vd. 'ai') chỉ có thể lọt vào danh sách ứng viên
    khi là từ viết tắt viết hoa (AI), nên không bị coi là từ 1 âm tiết tiếng Việt."""
    global _STOPWORDS
    if _STOPWORDS is None:
        _STOPWORDS = load_stopwords()
    return " " not in term and not _is_foreign(term) and term not in _STOPWORDS


def make_groups(terms: list, labels, total) -> list:
    """Gom chỉ số term theo nhãn cụm, rồi áp dụng quy tắc từ 1 âm tiết:
    cụm từ nhiều âm tiết / từ nước ngoài giữ nguyên nhóm theo embedding; từ tiếng Việt 1 âm tiết
    chỉ ở lại nhóm khi nó là một âm tiết của một cụm từ trong cùng nhóm (vd. 'phim' với 'phim ảnh'),
    ngược lại tách thành nhóm riêng.
    Trả về danh sách nhóm (mỗi nhóm là list chỉ số), sắp theo tổng tần suất giảm dần;
    trong mỗi nhóm, thành viên sắp theo (tần suất giảm dần, độ dài tăng dần) -> phần tử đầu là từ đại diện."""
    by_label = {}
    for idx, lab in enumerate(labels):
        by_label.setdefault(int(lab), []).append(idx)
    groups = []
    for ids in by_label.values():
        if not config.SPLIT_MONOSYLLABLE_GROUPS or len(ids) == 1:
            groups.append(ids)
            continue
        multi = [i for i in ids if not _is_vi_monosyllable(terms[i])]
        syllables = {s for i in multi for s in terms[i].split()}
        kept = multi + [i for i in ids if _is_vi_monosyllable(terms[i]) and terms[i] in syllables]
        if kept:
            groups.append(kept)
        groups += [[i] for i in ids if i not in kept]
    groups = [sorted(g, key=lambda i: (-total[terms[i]], len(terms[i]))) for g in groups]
    return sorted(groups, key=lambda g: -sum(total[terms[i]] for i in g))


def build_dictionary(item_candidates: dict, encoder, threshold: float = None) -> dict:
    threshold = config.KEYWORD_SIM_THRESHOLD if threshold is None else threshold
    terms, total, dropped = collect(item_candidates)
    if not terms:
        raise ValueError("Không có ứng viên từ khóa nào")
    E = encoder.encode(terms, normalize=True)
    labels = cut(cluster_tree(E), len(terms), threshold)

    # Nhóm và chọn từ đại diện
    groups, term2gid, centroids = [], {}, []
    for gid, ids in enumerate(make_groups(terms, labels, total)):
        members = [{"term": terms[i], "freq": int(total[terms[i]])} for i in ids]
        c = E[ids].mean(axis=0)
        centroids.append(c / (np.linalg.norm(c) + 1e-12))
        for i in ids:
            term2gid[terms[i]] = gid
        groups.append({"group_id": gid, "keyword": terms[ids[0]], "members": members})

    # IDF theo nhóm: idf = ln((1 + N) / (1 + df)) + 1
    n_docs = len(item_candidates)
    df = Counter()
    for cand in item_candidates.values():
        df.update({term2gid[t] for t in cand if t in term2gid})
    for g in groups:
        g["df"] = int(df[g["group_id"]])
        g["idf"] = math.log((1 + n_docs) / (1 + g["df"])) + 1.0

    return {
        "threshold": threshold, "linkage": config.KEYWORD_LINKAGE, "model": config.ST_MODEL,
        "n_docs": n_docs, "n_terms": len(terms), "n_terms_dropped": dropped,
        "groups": groups, "term2gid": term2gid,
        "centroids": np.vstack(centroids).astype(np.float32),
    }


def item_keywords(cand: dict, dictionary: dict) -> list:
    """Từ khóa đại diện của một file trong CSDL: [{group_id, keyword, tf, tfidf}] giảm dần theo TF-IDF."""
    tf = Counter()
    for t, c in cand.items():
        gid = dictionary["term2gid"].get(t)
        if gid is not None:
            tf[gid] += c
    groups = dictionary["groups"]
    rows = [{"group_id": gid, "keyword": groups[gid]["keyword"], "tf": int(c),
             "tfidf": c * groups[gid]["idf"]} for gid, c in tf.items()]
    return sorted(rows, key=lambda r: -r["tfidf"])


def map_query(cand: dict, dictionary: dict, encoder) -> list:
    """Dùng cho file truy vấn (nội dung 4): ứng viên đã có trong từ điển -> nhóm của nó;
    ứng viên mới -> nhóm có centroid gần nhất nếu cosine >= ngưỡng; nếu không giữ làm từ khóa mới."""
    tf, new_terms = Counter(), Counter()
    unknown = [t for t in cand if t not in dictionary["term2gid"]]
    for t, c in cand.items():
        if t in dictionary["term2gid"]:
            tf[dictionary["term2gid"][t]] += c
    if unknown:
        sims = encoder.encode(unknown, normalize=True) @ dictionary["centroids"].T
        for t, row in zip(unknown, sims):
            j = int(np.argmax(row))
            if row[j] >= dictionary["threshold"]:
                tf[j] += cand[t]
            else:
                new_terms[t] += cand[t]
    groups = dictionary["groups"]
    idf_new = math.log((1 + dictionary["n_docs"]) / 1) + 1.0
    rows = [{"group_id": gid, "keyword": groups[gid]["keyword"], "tf": int(c),
             "tfidf": c * groups[gid]["idf"]} for gid, c in tf.items()]
    rows += [{"group_id": None, "keyword": t, "tf": int(c), "tfidf": c * idf_new}
             for t, c in new_terms.items()]
    return sorted(rows, key=lambda r: -r["tfidf"])
