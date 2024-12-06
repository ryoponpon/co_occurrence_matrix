from flask import Flask, request, render_template, send_file, redirect, url_for, session, jsonify
from flask_cors import CORS
import os
import pandas as pd
from itertools import combinations
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import logging
import mimetypes
import re

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask アプリケーションの設定
app = Flask(__name__)
CORS(app)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

# 一時ディレクトリの設定
UPLOAD_FOLDER = tempfile.mkdtemp()
OUTPUT_FOLDER = tempfile.mkdtemp()
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config.update(
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    OUTPUT_FOLDER=OUTPUT_FOLDER,
    MAX_CONTENT_LENGTH=32 * 1024 * 1024,  # 32MB
    TEMPLATES_AUTO_RELOAD=True
)

ALLOWED_EXTENSIONS = {'csv'}
executor = ThreadPoolExecutor(max_workers=4)

# ユーティリティ関数
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_filename(filename):
    """安全でない文字を削除しつつ、日本語や特定文字を許容"""
    invalid_chars = '<>:"/\\|?*\0'
    clean_name = ''.join(c for c in filename if c not in invalid_chars)
    clean_name = clean_name.strip()
    return clean_name

def clean_campaign_name(campaign_name):
    """キャンペーン名から先頭の数字と全角/半角スラッシュを削除"""
    if pd.isna(campaign_name):
        return campaign_name
    
    campaign_name = str(campaign_name)
    patterns = [
        r'^\d+[/／]',
        r'^\d+\s*[/／]',
        r'^[\d\s/／]+',
        r'^[/／]+',
        r'^\d+[/／]\d+[/／]',
    ]
    
    cleaned = campaign_name
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned)
    
    cleaned = re.sub(r'^[/／]+', '', cleaned)
    cleaned = cleaned.strip()
    
    return cleaned

# 共起行列生成処理
def process_cooccurrence_file(filepath, original_filename):
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

# キャンペーン名クリーニング処理
def process_campaign_file(filepath, original_filename):
    try:
        df = pd.read_csv(filepath, encoding='utf-8-sig')
        
        campaign_columns = [col for col in df.columns if 'キャンペーン' in col]
        if not campaign_columns:
            raise ValueError("キャンペーン名を含むカラムが見つかりません")
        
        campaign_col = campaign_columns[0]
        df[campaign_col] = df[campaign_col].apply(clean_campaign_name)
        
        output_filename = f"cleaned_{sanitize_filename(original_filename)}"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)
        
        df.to_csv(output_filepath, encoding='utf-8-sig', index=False)
        return output_filename

    except Exception as e:
        logger.error(f"ファイル処理エラー: {str(e)}", exc_info=True)
        return None
    
# ルート定義
@app.route("/")
def index():
    """トップページ（共起行列生成ツール）"""
    return render_template("co_matrix.html")

@app.route("/campaign")
def campaign():
    """キャンペーン名統合ツール"""
    return render_template("campaign_int.html")

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'files[]' not in request.files:
        return jsonify({'error': 'ファイルがありません'}), 400
    
    files = request.files.getlist('files[]')
    uploaded_files = []
    
    for file in files:
        if file and allowed_file(file.filename):
            # 日本語をそのまま許容
            filename = sanitize_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            uploaded_files.append(filename)
    
    return jsonify({
        'success': True,
        'files': uploaded_files
    })

@app.route('/process_cooccurrence', methods=['POST'])
def process_cooccurrence_files():
    """共起行列生成処理"""
    filenames = request.json.get('files', [])
    output_files = []
    
    for filename in filenames:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            future = executor.submit(process_cooccurrence_file, filepath, filename)
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
        'redirect': url_for('complete_cooccurrence')
    })

@app.route('/process_campaign', methods=['POST'])
def process_campaign_files():
    """キャンペーン名クリーニング処理"""
    filenames = request.json.get('files', [])
    output_files = []
    
    for filename in filenames:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            future = executor.submit(process_campaign_file, filepath, filename)
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
        'redirect': url_for('complete_campaign')
    })

@app.route("/complete_cooccurrence")
def complete_cooccurrence():
    """共起行列生成完了ページ"""
    output_files = session.get('output_files', [])
    return render_template("complete_top.html", output_files=output_files)

@app.route("/complete_campaign")
def complete_campaign():
    """キャンペーン名クリーニング完了ページ"""
    output_files = session.get('output_files', [])
    return render_template("complete_second.html", output_files=output_files)

@app.route("/download/<path:filename>")
def download_file(filename):
    try:
        filepath = os.path.join(app.config["OUTPUT_FOLDER"], filename)
        if not os.path.exists(filepath):
            return "ファイルが見つかりません", 404

        # 日本語ファイル名をそのままエンコード
        response = send_file(
            filepath,
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

if __name__ == "__main__":
    app.run(debug=False)
