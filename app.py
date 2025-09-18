# app.py
# 発芽試験データのインタラクティブ集計（Streamlit）
# 追加: CSVアップロード対応（列名が異なる場合も列マッピングで対応）
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from io import StringIO

st.set_page_config(page_title="発芽試験の集計（CSVアップロード対応）", layout="wide")
# 通常の st.title ではなく st.markdown を使う
st.markdown(
    "<h3 style='text-align: center; color: green;'>🌱 信大雑草研専用・発芽試験の集計 / Germination Metrics (CSV upload ready)</h3>",
    unsafe_allow_html=True
)

st.markdown("""
**使い方 / How to use**
1. 左の **CSVアップロード** でファイルを読み込む（列名が違っても列選択で割り当て可能）  
   - 想定列: `t`（日数）, `n`（日別発芽数）  
   - 例: `t,n` / `day,count` などでもOK（画面でマッピング）  
2. CSVがない場合は下の **編集可能な表** で直接入力（行の追加・削除可）  
3. サイドバーで **供試種子数 N** を設定  
4. 指標とグラフが自動更新されます
""")

# -----------------------------
# サイドバー（設定）
# -----------------------------
with st.sidebar:
    st.header("📥 CSVアップロード / Upload CSV")
    uploaded = st.file_uploader("CSVファイルを選択 / Choose a CSV file", type=["csv"])
    st.caption("想定フォーマット例（UTF-8, ヘッダあり）: `t,n`")

    st.markdown("---")
    st.header("⚙️ 設定 / Settings")
    N_total = st.number_input("供試種子数 N (Total seeds)", min_value=1, value=50, step=1)
    show_reference_unweighted = st.checkbox(
        "斉一発芽係数の参考：非重み付き(mean(t)基準)も表示 / Show 'unweighted' reference",
        value=False
    )
    st.markdown("---")
    # テンプレCSVのダウンロード
    sample = pd.DataFrame({"t":[1,2,3,4,5,6,7,8,9,10,11,12],
                           "n":[0,2,5,12,15,5,4,0,1,0,0,0]})
    st.download_button(
        "テンプレCSVをダウンロード（t,n）",
        data=sample.to_csv(index=False).encode("utf-8"),
        file_name="germination_template.csv",
        mime="text/csv",
        use_container_width=True
    )
    st.caption("列名が違っても後で割り当てできます / You can map columns later.")

# -----------------------------
# 入力データの取得
# -----------------------------
uploaded_df = None
if uploaded is not None:
    try:
        # pandasで読み込み（自動エンコーディング検出は行わずUTF-8想定）
        uploaded_df = pd.read_csv(uploaded)
    except Exception as e:
        st.error(f"CSVの読み込みに失敗しました: {e}")

# 列マッピングUI（CSVに2列以上ある・列名が異なる場合の対応）
if uploaded_df is not None and not uploaded_df.empty:
    st.subheader("🗂️ CSVプレビュー / CSV Preview")
    st.dataframe(uploaded_df.head(), use_container_width=True)

    cols = list(uploaded_df.columns)
    st.markdown("**列を割り当ててください / Map columns to fields**")
    c1, c2 = st.columns(2)
    with c1:
        col_t = st.selectbox("日数 t に対応する列 / Column for t (days)", options=cols, index=0)
    with c2:
        col_n = st.selectbox("日別発芽数 n に対応する列 / Column for n (counts)", options=cols, index=min(1, len(cols)-1))

    df_raw = uploaded_df[[col_t, col_n]].copy()
    df_raw.columns = ["t(日数)", "n(日別発芽数)"]

else:
    # CSVがない場合は編集表の初期値を表示
    st.subheader("✍️ データ入力 / Data Entry (編集可能)")
    st.caption("表を直接編集／行追加／行削除できます。CSVがあれば左からアップロードしてください。")
    default_t = list(range(1, 13))
    default_n = [0, 2, 5, 12, 15, 5, 4, 0, 1, 0, 0, 0]
    init_df = pd.DataFrame({"t(日数)": default_t, "n(日別発芽数)": default_n})

    df_raw = st.data_editor(
        init_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="data_editor",
        column_config={
            "t(日数)": st.column_config.NumberColumn(step=1, min_value=0),
            "n(日別発芽数)": st.column_config.NumberColumn(step=1, min_value=0),
        }
    )

# -----------------------------
# 前処理・検証
# -----------------------------
df = df_raw.copy()

# 数値化＆NaN除去
for col in df.columns:
    df[col] = pd.to_numeric(df[col], errors="coerce")
df = df.dropna()

# t で昇順ソート（ユーザーが順不同で入力してもOK）
if not df.empty:
    df = df.sort_values("t(日数)", kind="mergesort").reset_index(drop=True)

# 整数丸め（必要なら）
if not df.empty:
    df["t(日数)"] = df["t(日数)"].round().astype(int)
    df["n(日別発芽数)"] = df["n(日別発芽数)"].round().astype(int)
    df["n(日別発芽数)"] = df["n(日別発芽数)"].clip(lower=0)

# -----------------------------
# 計算
# -----------------------------
if df.empty or df["n(日別発芽数)"].sum() == 0:
    st.warning("有効なデータがありません。n の合計が 0 でないように入力・アップロードしてください。 / No valid data. Please ensure sum(n) > 0.")
else:
    t = df["t(日数)"].to_numpy(dtype=float)
    n = df["n(日別発芽数)"].to_numpy(dtype=float)

    germinated = n.sum()
    cum_counts = np.cumsum(n)
    cum_pct_series = 100.0 * cum_counts / N_total
    cum_germ_pct_final = 100.0 * germinated / N_total

    # 平均発芽日数 (MDG) = Σ(t*n) / Σn
    MDG = (t * n).sum() / germinated

    # 平均発芽速度 (MGS) = Σn / Σ(t*n) = 1 / MDG
    MGS = germinated / (t * n).sum()

    # 斉一発芽係数（重み付き）
    var_w = ((t - MDG) ** 2 * n).sum() / germinated
    UGC_weighted = np.inf if var_w == 0 else 1.0 / var_w

    # 参考：非重み付き（Rの mean(t) 再現）
    mean_unw = t.mean()
    var_unw = ((t - mean_unw) ** 2 * n).sum() / germinated
    UGC_unweighted = np.inf if var_unw == 0 else 1.0 / var_unw

    # -----------------------------
    # メトリクス表示
    # -----------------------------
    st.subheader("📊 指標 / Metrics")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("最終累積発芽率 (%)", f"{cum_germ_pct_final:.2f}")
    c2.metric("平均発芽日数 MDG (days)", f"{MDG:.3f}")
    c3.metric("平均発芽速度 MGS (1/days)", f"{MGS:.6f}")
    c4.metric("斉一発芽係数（重み付き）", f"{UGC_weighted:.6f}")

    if show_reference_unweighted:
        st.caption(f"参考：斉一発芽係数（**非重み付き** / mean(t) 基準）= **{UGC_unweighted:.6f}**")

    if germinated > N_total:
        st.warning(
            f"注意：Σn = {int(germinated)} が N = {N_total} を超えています。"
            " 供試種子数 N を再確認するか、n の合計を見直してください。"
        )

    # -----------------------------
    # グラフ
    # -----------------------------
    st.subheader("📈 グラフ / Charts")
    gc1, gc2 = st.columns(2)

    with gc1:
        fig1, ax1 = plt.subplots()
        ax1.bar(t, n, edgecolor="black")
        ax1.set_xlabel("日数 t / Days")
        ax1.set_ylabel("日別発芽数 n / Daily germination")
        ax1.set_title("日別発芽数 / Daily counts")
        ax1.grid(True, alpha=0.3)
        st.pyplot(fig1, use_container_width=True)

    with gc2:
        fig2, ax2 = plt.subplots()
        ax2.plot(t, cum_pct_series, marker="o")
        ax2.set_xlabel("日数 t / Days")
        ax2.set_ylabel("累積発芽率 (%) / Cumulative (%)")
        ax2.set_ylim(0, 100)
        ax2.set_title("累積発芽率の推移 / Cumulative germination (%)")
        ax2.grid(True, alpha=0.3)
        st.pyplot(fig2, use_container_width=True)

    # -----------------------------
    # 出力（ダウンロード）
    # -----------------------------
    st.subheader("💾 ダウンロード / Download")
    out = df.copy()
    out["累積発芽数 cum"] = cum_counts
    out["累積発芽率 (%) cum%"] = cum_pct_series
    st.download_button(
        "CSVとして保存 / Download CSV",
        data=out.to_csv(index=False).encode("utf-8"),
        file_name="germination_table.csv",
        mime="text/csv",
        use_container_width=True
    )

    st.text_area(
        "結果の要約 / Summary (copy-ready)",
        value=(
            f"Σn={int(germinated)}, N={N_total}, 最終累積発芽率={cum_germ_pct_final:.2f}%\n"
            f"MDG={MDG:.3f} 日, MGS={MGS:.6f} 1/日\n"
            f"斉一発芽係数（重み付き）={UGC_weighted:.6f}（分散={var_w:.6f}）\n"
            + (f"参考：非重み付き={UGC_unweighted:.6f}（分散={var_unw:.6f}）" if show_reference_unweighted else "")
        ),
        height=130
    )


