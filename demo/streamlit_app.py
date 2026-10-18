"""Knowledge Assistant: public demo.

Live: role-scoped hybrid retrieval and the evidence gate, over the synthetic corpus.
Recorded: answers produced by the real system (see demo/recorded_answers.json).
No API key is used and no question typed here is sent to any model.
"""
import json
import re
from pathlib import Path

import streamlit as st

import demo_search as ds

HERE = Path(__file__).resolve().parent
REPO = "https://github.com/hamazmubashar/knowledge-assistant"

st.set_page_config(page_title="Knowledge Assistant: demo", page_icon="🔎", layout="wide")

# Static styling only. Document and model text is never passed through unsafe HTML.
st.markdown("""<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
div[data-testid="stMetricValue"] {font-size: 1.6rem;}
.small-note {color: #5d736c; font-size: 0.9rem;}
</style>""", unsafe_allow_html=True)

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$])")


def esc(text) -> str:
    """Escape markdown so corpus or model text renders as plain text."""
    return _MD_SPECIAL.sub(r"\\\1", str(text))


@st.cache_resource(show_spinner="Loading the embedding model (first visit only)…")
def get_index() -> ds.Index:
    from fastembed import TextEmbedding
    model = TextEmbedding(model_name=ds.EMBEDDING_MODEL)
    return ds.Index(lambda texts: list(model.embed(texts)),
                    lambda q: next(iter(model.embed([q]))))


@st.cache_data
def load_recordings() -> dict:
    path = HERE / "recorded_answers.json"
    if not path.exists():
        return {"records": [], "missing": True}
    return json.loads(path.read_text(encoding="utf-8"))


def page_text(title: str, page: int) -> str | None:
    for c in ds.build_chunks():
        if c.document_title == title and c.page_number == page:
            return c.page_text
    return None


# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Sign in as")
    role = st.radio("Role", list(ds.ROLE_GROUPS), format_func=ds.ROLE_LABEL.get,
                    label_visibility="collapsed")
    readable = ", ".join(ds.GROUP_LABEL[g] for g in ds.ROLE_GROUPS[role])
    st.caption(f"Can read: **{readable}** documents. Everything else is filtered out "
               "before ranking, so it can never be retrieved or quoted.")
    st.divider()
    rec = load_recordings()
    st.markdown("**About this demo**")
    st.caption(
        "Synthetic documents only. Retrieval and the evidence gate run live here. Answers are "
        "recordings of the real system, not generated on this page, so no question you type is "
        "sent to any model and no API key is used."
        + (f" Recorded {rec.get('recorded_at', '')[:10]} at commit `{rec.get('commit', '')}`."
           if rec.get("records") else ""))
    st.markdown(f"[Source code and evaluation reports]({REPO})")

st.title("Internal knowledge assistant")
st.markdown("Answers come only from documents your role may read. Every sentence is quoted "
            "word for word from a cited page, and questions the documents don't cover are "
            "declined instead of guessed.")

tab_ask, tab_search, tab_docs, tab_eval, tab_how = st.tabs(
    ["Ask", "Search live", "Documents", "Evaluation", "How it works"])


# ---------------- Ask (recorded answers) ----------------
def show_answer(item: dict):
    r = item["result"]
    st.markdown(f"**Question:** {esc(item['question'])}")
    st.caption(f"Scenario: {item['shows']}")

    if r.get("status") != "answered" or not r.get("sentences"):
        reason = {"weak_evidence": "no passage you can access was close enough to the question "
                                   "(evidence gate), so no model was called",
                  "model_declined": "the model found the evidence did not answer the question",
                  "unsupported_answer": "the checker could not confirm the drafted sentences "
                                        "against their quotes, so the answer was withheld",
                  }.get(r.get("refusal_reason"), r.get("refusal_reason") or "not answerable")
        st.warning(f"**No answer found in your documents.**\n\n{esc(r.get('answer') or '')}\n\n"
                   f"Why: {esc(reason)}.")
    else:
        cites, key_to_n, nums = [], {}, []
        for s in r["sentences"]:
            c = s["citation"]
            key = (c["version_id"], c["page_number"], c["quote"])
            if key not in key_to_n:
                key_to_n[key] = len(cites) + 1
                cites.append(c)
            nums.append(key_to_n[key])
        if r.get("conflict"):
            if r.get("dropped_sentences"):
                st.warning("**The documents disagree.** The verifier removed part of the answer "
                           "because its quote could not be confirmed, so only one version is shown. "
                           "Check the sources and confirm with the document owner before acting.")
            else:
                st.warning("**The documents disagree.** Both versions are shown with their sources. "
                           "Confirm with the document owner before acting.")
        with st.container(border=True):
            st.markdown(" ".join(f"{esc(s['text'])} **[{n}]**"
                                 for s, n in zip(r["sentences"], nums)))
            st.caption("✓ Each sentence is backed by a passage found word for word on the cited page.")

        st.markdown("##### Sources")
        for n, c in enumerate(cites, start=1):
            with st.container(border=True):
                st.markdown(f"**[{n}] {esc(c['document_title'])}** · v{c['version_number']} · "
                            f"page {c['page_number']}")
                st.markdown(f"> {esc(c['quote'])}")
                if c.get("low_confidence"):
                    st.info("Scanned page: this text was read by OCR. Check the original.")
                text = page_text(c["document_title"], c["page_number"])
                if text:
                    with st.expander(f"Show page {c['page_number']}"):
                        st.code(text, language=None)

    cols = st.columns(4)
    bd = r.get("best_distance")
    cols[0].metric("Best distance", f"{bd:.3f}" if isinstance(bd, (int, float)) else "–",
                   help=f"Cosine distance of the closest passage; must be ≤ {ds.MAX_DISTANCE}.")
    ms = sum(r.get(k) or 0 for k in ("retrieval_ms", "generation_ms", "judge_ms"))
    cols[1].metric("Time (recorded)", f"{ms / 1000:.1f} s" if ms else "< 0.1 s")
    cols[2].metric("Injected lines removed", r.get("redacted_sentences", 0))
    cols[3].metric("Sentences dropped", len(r.get("dropped_sentences") or []),
                   help="Draft sentences removed because their quote was not on the page or the "
                        "checker found the quote did not support them.")
    if r.get("model"):
        st.caption(f"Answer model: {r['model']} · checker: {r.get('judge') or '–'}")


with tab_ask:
    rec = load_recordings()
    items = [x for x in rec.get("records", []) if x["role"] == role and "result" in x]
    if rec.get("missing") or not items:
        st.info("No recorded answers for this role yet. Use **Search live** to try retrieval.")
    else:
        st.caption("Pick a question. These answers were recorded from the real system; switch "
                   "role in the sidebar to see how access changes the result.")
        labels = [f"{x['question']}  ·  {x['shows']}" for x in items]
        choice = st.selectbox("Question", range(len(items)), format_func=labels.__getitem__)
        show_answer(items[choice])


# ---------------- Search live ----------------
with tab_search:
    st.caption("Type anything. This runs the retrieval step and the evidence gate live, with "
               "your role's access filter. It does not generate an answer.")
    q = st.text_input("Search the documents you can access", max_chars=300,
                      placeholder="e.g. How long is the warranty on hardware?")
    if q.strip():
        results = get_index().search(q.strip(), role)
        ok, best = ds.gate(results)
        if ok:
            st.success(f"Evidence gate passed (best distance {best:.3f} ≤ {ds.MAX_DISTANCE}). "
                       "The real system would now draft an answer from these passages and "
                       "verify every quote.")
        else:
            st.warning("Evidence gate failed"
                       + (f" (best distance {best:.3f} > {ds.MAX_DISTANCE})" if best else "")
                       + ". The real system would decline without calling a model.")
        for i, r in enumerate(results, start=1):
            c = r["chunk"]
            with st.container(border=True):
                st.markdown(f"**{i}. {esc(c.document_title)}** · page {c.page_number} · "
                            f"{ds.GROUP_LABEL[c.group]}")
                st.code(c.text, language=None)
                st.caption(f"distance {r['distance'] if r['distance'] is not None else '–'} · "
                           f"vector rank {r['vector_rank'] or '–'} · "
                           f"keyword rank {r['keyword_rank'] or '–'} · RRF {r['score']}")


# ---------------- Documents ----------------
with tab_docs:
    groups = set(ds.ROLE_GROUPS[role])
    docs = ds.documents()
    st.caption(f"Synthetic corpus version {ds.CORPUS_VERSION}: {len(docs)} documents. "
               f"As {ds.ROLE_LABEL[role]} you can search "
               f"{sum(d['group'] in groups for d in docs)} of them.")
    st.dataframe(
        [{"Document": d["title"], "Group": ds.GROUP_LABEL[d["group"]],
          "Pages": d["pages"], "You can read": "Yes" if d["group"] in groups else "No",
          "Notes": ", ".join(n for n, on in (("scanned", d["scanned"]),
                                              ("older version superseded", d["superseded_version"]))
                             if on)}
         for d in docs],
        hide_index=True, use_container_width=True)


# ---------------- Evaluation ----------------
with tab_eval:
    st.markdown("Measured on the frozen configuration (tag `v1-acceptance-freeze`) with "
                "synthetic development questions. **Diagnostic, not acceptance evidence:** the "
                "independent acceptance run is still pending.")
    c = st.columns(4)
    c[0].metric("Correct page ranked first", "96.9%")
    c[1].metric("Correct page in top 5", "100%")
    c[2].metric("Permission leaks", "0")
    c[3].metric("Automated tests", "100 passed")
    st.markdown("##### Answers (Gemini 3.8 Flash, frozen configuration)")
    st.dataframe([
        {"Metric": "Answer correctness", "Target": "≥ 85%", "Result": "92.9%", "Met": "Yes"},
        {"Metric": "Citation accuracy", "Target": "≥ 95%", "Result": "92.9%", "Met": "No"},
        {"Metric": "Unsupported answers", "Target": "≤ 5%", "Result": "0.0%", "Met": "Yes"},
        {"Metric": "Over-refusal", "Target": "≤ 10%", "Result": "7.1%", "Met": "Yes"},
        {"Metric": "Access leaks", "Target": "0", "Result": "0", "Met": "Yes"},
        {"Metric": "Correct refusals", "Target": "all", "Result": "6/6", "Met": "Yes"},
        {"Metric": "Prompt injections resisted", "Target": "all", "Result": "3/3", "Met": "Yes"},
        {"Metric": "Conflicts handled", "Target": "all", "Result": "1/1", "Met": "Yes"},
    ], hide_index=True, use_container_width=True)
    st.caption("Citation accuracy misses its target because of an occasional extra off-topic "
               "sentence. Median latency was about 62 s on the provider's free tier; "
               "production latency has not been measured.")
    st.markdown(f"Reports: [answer evaluation]({REPO}/blob/main/eval/reports/"
                f"answers-dev-20261013-223938.md) · [retrieval evaluation]({REPO}/blob/main/eval/"
                f"reports/dev-20261014-101216.md)")


# ---------------- How it works ----------------
with tab_how:
    st.markdown("""
1. **Access filter first.** The user's role decides which document groups are searched. Other groups are excluded inside the query, before ranking.
2. **Hybrid search.** Vector similarity (BAAI/bge-small-en-v1.5) and keyword search, combined with reciprocal rank fusion (k = 60).
3. **Evidence gate.** If no passage is within cosine distance 0.35, the system declines without calling a model.
4. **Injection screening.** Instruction-like lines inside documents are removed before the model sees them.
5. **Draft with quotes.** The model must give, for every sentence, a quote copied exactly from a numbered source.
6. **Verification.** Quotes not found word for word on the page are dropped; a separate checker model confirms each quote supports its sentence and is on topic.
7. **Answer or decline.** If too little survives verification, the system declines.

**Stack:** FastAPI, PostgreSQL with pgvector, background worker, S3-compatible storage, Docker Compose with a pinned base image and locked dependencies, local Ollama model, Gemini as checker.

**This page** re-implements step 2 in memory for hosting; production uses PostgreSQL. See `demo/demo_search.py` for the exact differences.
""")
