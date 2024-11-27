from flask import Flask, request, render_template, send_file, redirect, url_for, session
import os
import pandas as pd
from itertools import combinations
import tempfile
import shutil

# Flaskアプリケーションの初期設定
app = Flask(__name__)
app.secret_key = "your_secret_key"  # セッション管理に必要なキー

# 一時ディレクトリの設定
UPLOAD_FOLDER = tempfile.mkdtemp()
OUTPUT_FOLDER = tempfile.mkdtemp()
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER


# ルートページ: ファイルアップロード
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # 前回のファイルをクリーンアップ
        cleanup_files()

        # ファイルアップロード処理
        uploaded_files = request.files.getlist("files")
        saved_files = []

        for file in uploaded_files:
            if file and file.filename:
                file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
                file.save(file_path)
                process_file(file_path, file.filename)
                saved_files.append(file.filename)

        # アップロードファイル情報をセッションに保存
        session["uploaded_files"] = saved_files

        return redirect(url_for("complete"))

    return render_template("index.html")


# ファイル処理関数: 共起行列生成
def process_file(filepath, filename):
    try:
        # CSVファイルの読み込み
        data = pd.read_csv(filepath)
        if "メール" not in data.columns or "キャンペーン名" not in data.columns:
            raise ValueError("CSVに必要な列が含まれていません: 'メール' と 'キャンペーン名'")

        # 共起行列生成
        data = data[["メール", "キャンペーン名"]]
        co_occurrence_counts = {}
        for _, group in data.groupby("メール"):
            campaign_names = group["キャンペーン名"].unique()
            for item1, item2 in combinations(campaign_names, 2):
                if item1 != item2:
                    if (item1, item2) in co_occurrence_counts:
                        co_occurrence_counts[(item1, item2)] += 1
                    elif (item2, item1) in co_occurrence_counts:
                        co_occurrence_counts[(item2, item1)] += 1
                    else:
                        co_occurrence_counts[(item1, item2)] = 1

        # 共起行列データフレームの生成
        campaigns = sorted(data["キャンペーン名"].unique())
        co_occurrence_matrix = pd.DataFrame(0, index=campaigns, columns=campaigns)
        for (item1, item2), count in co_occurrence_counts.items():
            co_occurrence_matrix.loc[item1, item2] = count
            co_occurrence_matrix.loc[item2, item1] = count

        # 共起行列をCSVに保存
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], f"co_occurrence_matrix_{filename}")
        co_occurrence_matrix.to_csv(output_filepath, encoding="utf-8-sig")

    except Exception as e:
        print(f"エラー: {e}")


# 処理完了ページ
@app.route("/complete")
def complete():
    output_files = session.get("uploaded_files", [])
    available_files = os.listdir(app.config["OUTPUT_FOLDER"])
    return render_template("complete.html", output_files=available_files)


# ファイルのダウンロード
@app.route("/download/<filename>")
def download_file(filename):
    file_path = os.path.join(app.config["OUTPUT_FOLDER"], filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "ファイルが見つかりません", 404


# クリーンアップ処理
@app.route("/cleanup", methods=["POST"])
def cleanup():
    cleanup_files()
    session.pop("uploaded_files", None)
    return redirect(url_for("index"))


def cleanup_files():
    """一時フォルダ内のファイルを削除"""
    # アップロードフォルダのクリーンアップ
    for folder in [app.config["UPLOAD_FOLDER"], app.config["OUTPUT_FOLDER"]]:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            if os.path.exists(file_path):
                os.remove(file_path)


# アプリケーションの実行
if __name__ == "__main__":
    app.run(debug=True)
