from flask import Flask, request, render_template, send_file, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import os
import pandas as pd
from itertools import combinations
import tempfile
from concurrent.futures import ThreadPoolExecutor

# Flask アプリケーションの設定
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

UPLOAD_FOLDER = tempfile.mkdtemp()
OUTPUT_FOLDER = tempfile.mkdtemp()
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 最大16MB

ALLOWED_EXTENSIONS = {'csv'}
executor = ThreadPoolExecutor(max_workers=4)


# ファイル拡張子の検証
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ファイル処理関数
def process_file(filepath, original_filename):
    try:
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
                    co_occurrence_counts[(item1, item2)] = co_occurrence_counts.get((item1, item2), 0) + 1

        # 共起行列データフレーム生成
        campaigns = sorted(data["キャンペーン名"].unique())
        co_occurrence_matrix = pd.DataFrame(0, index=campaigns, columns=campaigns)
        for (item1, item2), count in co_occurrence_counts.items():
            co_occurrence_matrix.loc[item1, item2] = count
            co_occurrence_matrix.loc[item2, item1] = count

        # ファイルを元の名前に基づいて保存
        output_filename = f"共起行列_{original_filename}"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)
        co_occurrence_matrix.to_csv(output_filepath, encoding="utf-8-sig")
        return output_filename
    except Exception as e:
        print(f"エラー: {e}")
        return None


# ルートページ
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        cleanup_files()
        uploaded_files = request.files.getlist("files")
        if not uploaded_files:
            flash("ファイルが選択されていません。")
            return redirect(request.url)

        # 並列処理でファイルを処理
        output_files = []
        for file in uploaded_files:
            if file and allowed_file(file.filename):
                original_filename = file.filename
                filename = secure_filename(original_filename)
                file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(file_path)
                future = executor.submit(process_file, file_path, original_filename)
                output_files.append(future)

        # 処理結果を取得
        session['output_files'] = [
            future.result() for future in output_files if future.result() is not None
        ]

        return redirect(url_for("complete"))

    return render_template("index.html")


# 完了ページ
@app.route("/complete")
def complete():
    output_files = session.get('output_files', [])
    return render_template("complete.html", output_files=output_files)


# ファイルのダウンロード
@app.route("/download/<filename>")
def download_file(filename):
    try:
        file_path = os.path.join(app.config["OUTPUT_FOLDER"], filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
    except Exception as e:
        print(f"ダウンロードエラー: {e}")
    return "ファイルが見つかりません", 404


# ファイルクリーンアップ
def cleanup_files():
    """一時フォルダ内のファイルを削除"""
    for folder in [app.config["UPLOAD_FOLDER"], app.config["OUTPUT_FOLDER"]]:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            if os.path.exists(file_path):
                os.remove(file_path)


# 実行
if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
