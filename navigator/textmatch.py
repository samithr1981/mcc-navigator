"""Text matching: score a free-text business description against every MCC definition.

Two signals are blended:
  * entry match: how closely a phrase looks like the MCC title or one of its "included" merchant types
    (character n-grams, so plurals and small typos still match);
  * description match: word-level similarity to the MCC definition text.
Scores are match strengths between 0 and 1. They are not probabilities.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer, TfidfVectorizer

from . import kb
from .synonyms import expand

BOILERPLATE = [
    r"merchants? classified with this mcc( are| provide| sell| engage in| operate)?", r"entities classified with this mcc( are)?",
    r"this mcc (also )?includes?", r"also included in this (mcc|category)( are)?", r"these merchants", r"merchants that", r"\(not elsewhere classified\)",
]
EXTRA_STOP = {"mcc", "merchant", "merchants", "classified", "include", "includes", "included", "provide", "provides", "sell", "sells",
              "engaged", "services", "service", "including", "such", "may", "also", "used", "use", "etc", "stores", "store", "shops", "shop",
              "business", "businesses", "elsewhere", "primarily", "chain", "chains", "outlet", "outlets", "shop", "various", "variety", "general", "public", "persons", "products", "product"}
STOPSET = set(ENGLISH_STOP_WORDS) | EXTRA_STOP
STOP = sorted(STOPSET)
ENTRY_WEIGHT = {"title": 1.0, "included": 1.0, "title_part": 0.9}


def fold(s: str) -> str:
    s = re.sub(r"['’]s\b", "s", s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("jewellery", "jewelry").replace("cheque", "check").replace("petrol", "gasoline petrol")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9&/+ -]", " ", s)).strip()


def clean_desc(s: str) -> str:
    s = s.lower()
    for b in BOILERPLATE:
        s = re.sub(b, " ", s)
    return fold(s)


def stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def stems(text: str) -> list[str]:
    return [stem(t) for t in re.findall(r"[a-z][a-z0-9&+]+", text) if t not in STOPSET]


def phrases(text: str) -> list[str]:
    """Split a free-text description into short phrases (items separated by commas, semicolons, 'and', new lines)."""
    parts = re.split(r"[\n;,/|•]+|\band\b|\bwith\b|\bplus\b|\balso\b|\bas well as\b|\.\s", text)
    out = [fold(p) for p in parts]
    return [p for p in out if len(p) >= 3][:30]


@dataclass
class Match:
    code: str
    score: float
    entry_score: float
    desc_score: float
    best_entry: str
    best_phrase: str


class Index:
    def __init__(self, mccs: dict[str, kb.MCC] | None = None):
        self.mccs = mccs or kb.load()
        self.codes = list(self.mccs)
        self.code_idx = {c: i for i, c in enumerate(self.codes)}
        entries = []  # (mcc index, text, kind)
        docs = []
        for i, c in enumerate(self.codes):
            m = self.mccs[c]
            title = fold(re.sub(r"\(.*?\)", " ", m.title))
            entries.append((i, title, "title"))
            parts = [p for p in re.split(r"[–,]| and | including ", m.title) if len(p.strip()) > 3]
            if len(parts) > 1:
                for p in parts:
                    entries.append((i, fold(re.sub(r"\(.*?\)", " ", p)), "title_part"))
            for inc in m.included:
                entries.append((i, fold(inc), "included"))
            docs.append(fold(f"{m.title} {m.title} {' '.join(m.included)} {' '.join(m.included)}") + " " + clean_desc(m.description))
        self.entries = entries
        self.entry_mcc = np.array([e[0] for e in entries])
        self.entry_w = np.array([ENTRY_WEIGHT[e[2]] for e in entries])
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        self.X_char = self.char.fit_transform([e[1] for e in entries])
        self.tok = CountVectorizer(analyzer=stems, binary=True)
        E = self.tok.fit_transform([e[1] for e in entries]).astype(float)
        df = np.asarray((E > 0).sum(axis=0)).ravel()
        self.tok_idf = np.log((1 + E.shape[0]) / (1 + df)) + 1.0
        self.E_tok = E.tocsr()
        self.E_wsum = np.asarray(E.multiply(self.tok_idf[None, :]).sum(axis=1)).ravel() + 1e-9
        self.word = TfidfVectorizer(ngram_range=(1, 2), stop_words=STOP, sublinear_tf=True, token_pattern=r"(?u)\b[a-z][a-z0-9&+-]+\b")
        self.X_word = self.word.fit_transform(docs)
        self.docs = docs

    # ------------------------------------------------------------------ scoring
    def entry_scores(self, phrase_list: list[str], drop_entry: int | None = None):
        if not phrase_list:
            return np.zeros((0, len(self.codes))), [[""] * len(self.codes)]
        Q = self.char.transform(phrase_list)
        S = (Q @ self.X_char.T).toarray() * self.entry_w[None, :]
        if drop_entry is not None:
            S[:, drop_entry] = 0
        # word-level match: how much of the phrase is covered by the entry, and how much of the entry by the phrase
        Qt = self.tok.transform(phrase_list).astype(float)
        Qw = Qt.multiply(self.tok_idf[None, :]).tocsr()
        q_sum = np.asarray(Qw.sum(axis=1)).ravel() + 1e-9
        overlap = (Qw @ self.E_tok.T).toarray()
        qcov = overlap / q_sum[:, None]
        ecov = overlap / self.E_wsum[None, :]
        T = (qcov * ecov) / (0.65 * qcov + 0.35 * ecov + 1e-9)
        S = np.maximum(S, 0.0) * 0.5 + T * 0.5 * self.entry_w[None, :] * (S > 0)
        if drop_entry is not None:
            S[:, drop_entry] = 0
        per = np.zeros((len(phrase_list), len(self.codes)))
        arg = np.zeros((len(phrase_list), len(self.codes)), dtype=int)
        for j in range(len(self.codes)):
            cols = np.where(self.entry_mcc == j)[0]
            sub = S[:, cols]
            per[:, j] = sub.max(axis=1)
            arg[:, j] = cols[sub.argmax(axis=1)]
        return per, arg

    def rank(self, text: str, extra_terms: str = "", top: int = 12, doc_override: dict[int, str] | None = None,
             drop_entry: int | None = None) -> list[Match]:
        text = fold(expand(text) + " " + extra_terms)
        ph = phrases(text)
        whole = [text] if text else []
        plist = list(dict.fromkeys(ph + whole))
        if not plist:
            return []
        per, arg = self.entry_scores(plist, drop_entry)
        Qw = self.word.transform(plist)
        Xw = self.X_word
        if doc_override:
            Xw = Xw.tolil(copy=True)
            for j, d in doc_override.items():
                Xw[j] = self.word.transform([d])
            Xw = Xw.tocsr()
        Dw = (Qw @ Xw.T).toarray()
        ent = per.max(axis=0)
        best_p = per.argmax(axis=0)
        desc = Dw.max(axis=0)
        # a phrase that is the whole text counts a bit less than a single clean phrase
        score = 0.58 * ent + 0.42 * np.minimum(1.0, desc * 1.6)
        order = np.argsort(-score)[:top]
        out = []
        for j in order:
            e_idx = int(arg[best_p[j], j])
            out.append(Match(self.codes[j], float(score[j]), float(ent[j]), float(desc[j]), self.entries[e_idx][1], plist[int(best_p[j])]))
        return out
