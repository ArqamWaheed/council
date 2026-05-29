"""app.py — Streamlit fallback UI for Council.

Plainer than the designed index.html (run `python server.py` for that), but a
functional one-file alternative if the clock forces it.
"""
import streamlit as st

from run_council import run

st.set_page_config(page_title="Council", page_icon="\u2696\ufe0f", layout="centered")
st.title("\u2696\ufe0f The Council")
st.caption("Don't trust one model. Convene a jury \u2014 then let Hermes be the judge. (3 models \u00b7 1 verdict \u00b7 $0)")

q = st.text_input("Put a judgment call to the council",
                  placeholder="Should a 3-person startup use microservices or a monolith?")

if st.button("Convene", type="primary") and q:
    with st.spinner("The jurors are deliberating\u2026"):
        out = run(q)

    c1, c2 = st.columns([3, 1])
    c1.subheader(out["verdict"])
    c2.metric("Confidence", f"{int(out['confidence']*100)}%", f"split {out['split']}")

    st.divider()
    cols = st.columns(len(out["jurors"]))
    for col, j in zip(cols, out["jurors"]):
        with col:
            st.markdown(f"**{j['name']}**")
            st.caption(j["model"])
            st.markdown(f"### {j['position']}")
            for r in j["reasons"]:
                st.markdown(f"- {r}")

    with st.expander(f"Why they {'agreed' if out['unanimous'] else 'disagreed'}", expanded=True):
        if out["dissents"]:
            st.markdown("**Where they split**")
            for d in out["dissents"]:
                st.markdown(f"> {d}")
        else:
            st.markdown("> No dissent \u2014 the jurors were unanimous.")
        if out["agreements"]:
            st.markdown("**What they agreed on**")
            for a in out["agreements"]:
                st.markdown(f"- {a}")

    if any(j["mocked"] for j in out["jurors"]):
        st.info("Offline mock mode \u2014 add a free OpenRouter key to `.env` to convene real models.")
