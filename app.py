from flask import Flask, request, render_template, send_file, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
import os
import pandas as pd
from itertools import combinations
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import logging
import mimetypes

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask アプリケーションの設定
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

UPLOAD_FOLDER = tempfile.mkdtemp()
OUTPUT_FOLDER = tempfile.mkdtemp()
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 最大32MB

ALLOWED_EXTENSIONS = {'csv'}
executor = ThreadPoolExecutor(max_workers=4)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def sanitize_filename(filename):
    """ファイル名から不適切な文字を除去しつつ、日本語とハイフンを保持"""
    invalid_chars = '<>:"/\\|?*\0'
    clean_name = ''.join(c for c in filename if c not in invalid_chars)
    return clean_name.strip()


def process_file(filepath, original_filename):
    """CSVファイルを処理して共起行列を生成"""
    try:
        data = pd.read_csv(filepath, encoding='utf-8-sig')
        
        if "見込客/担当者ID18" not in data.columns or "キャンペーン名" not in data.columns:
            raise ValueError("CSVに必要な列が含まれていません: '見込客/担当者ID18' と 'キャンペーン名'")

        data = data[["見込客/担当者ID18", "キャンペーン名"]]
        co_occurrence_counts = {}
        for _, group in data.groupby("見込客/担当者ID18"):
            campaign_names = group["キャンペーン名"].unique()
            for item1, item2 in combinations(campaign_names, 2):
                if item1 != item2:
                    pair = tuple(sorted([item1, item2]))
                    co_occurrence_counts[pair] = co_occurrence_counts.get(pair, 0) + 1

        campaigns = sorted(data["キャンペーン名"].unique())
        co_occurrence_matrix = pd.DataFrame(0, index=campaigns, columns=campaigns)
        
        for (item1, item2), count in co_occurrence_counts.items():
            co_occurrence_matrix.loc[item1, item2] = count
            co_occurrence_matrix.loc[item2, item1] = count

        base_name = os.path.splitext(original_filename)[0]
        output_filename = f"共起行列-{base_name}.csv"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)
        
        co_occurrence_matrix.to_csv(output_filepath, encoding='utf-8-sig')
        return output_filename

    except Exception as e:
        logger.error(f"ファイル処理エラー: {str(e)}", exc_info=True)
        return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'files[]' not in request.files:
        return jsonify({'error': 'ファイルがありません'}), 400
    
    files = request.files.getlist('files[]')
    uploaded_files = []
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = sanitize_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            uploaded_files.append(filename)
    
    return jsonify({
        'success': True,
        'files': uploaded_files
    })


@app.route('/process', methods=['POST'])
def process_files():
    filenames = request.json.get('files', [])
    output_files = []
    
    for filename in filenames:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            future = executor.submit(process_file, file_path, filename)
            output_files.append(future)
    
    results = []
    for future in output_files:
        try:
            result = future.result()
            if result:
                results.append(result)
        except Exception as e:
            logger.error(f"処理エラー: {str(e)}", exc_info=True)

    session['output_files'] = results
    
    return jsonify({
        'success': True,
        'redirect': url_for('complete')
    })


@app.route("/complete")
def complete():
    output_files = session.get('output_files', [])
    return render_template("complete.html", output_files=output_files)


@app.route("/download/<path:filename>")
def download_file(filename):
    try:
        file_path = os.path.join(app.config["OUTPUT_FOLDER"], filename)
        if not os.path.exists(file_path):
            return "ファイルが見つかりません", 404

        response = send_file(
            file_path,
            as_attachment=True,
            mimetype='text/csv;charset=utf-8',
            download_name=filename
        )
        
        response.headers["Content-Disposition"] = \
            f"attachment; filename*=UTF-8''{quote(filename)}"
        
        return response

    except Exception as e:
        logger.error(f"ダウンロードエラー: {str(e)}", exc_info=True)
        return "ダウンロードに失敗しました", 500


def cleanup_files():
    """一時ファイルのクリーンアップ"""
    for folder in [app.config["UPLOAD_FOLDER"], app.config["OUTPUT_FOLDER"]]:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.error(f"ファイル削除エラー: {str(e)}", exc_info=True)


@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'error': 'ファイルサイズが大きすぎます'}), 413


if __name__ == "__main__":
    app.run(debug=True)