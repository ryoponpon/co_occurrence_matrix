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
CORS(app, supports_credentials=True)  # credentials サポートを追加

# セッションの設定
app.config.update(
    SECRET_KEY=os.urandom(24),
    SESSION_COOKIE_SECURE=True,  # 開発環境ではFalse
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)
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

ALLOWED_EXTENSIONS = {'csv', 'xlsx'}
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

def find_header_row(filepath, file_ext):
    """データフレームからヘッダー行を特定する"""
    target_columns = ['見込客/担当者ID18', 'キャンペーン名']
    
    # 最初の20行を確認
    for i in range(20):
        try:
            # 現在の行をヘッダーとして設定
            temp_df = pd.read_excel(filepath, header=i) if file_ext == 'xlsx' else pd.read_csv(filepath, encoding='utf-8-sig', header=i)
            
            # 列名を正規化（空白を削除し、大文字小文字を無視）
            normalized_columns = [str(col).strip().lower() for col in temp_df.columns]
            
            # 必要な列が含まれているかチェック
            found_columns = []
            for target in target_columns:
                for col in normalized_columns:
                    # 部分一致で検索（より柔軟な検索）
                    if ('id' in target.lower() and 'id' in col) or \
                       ('キャンペーン' in target and 'キャンペーン' in col):
                        found_columns.append(True)
                        break
                else:
                    found_columns.append(False)
            
            if all(found_columns):
                return i, temp_df
                
        except Exception as e:
            continue
            
    raise ValueError("必要な列が見つかりませんでした。")

def get_column_names(df):
    """必要なカラム名を特定する"""
    id_column = None
    campaign_column = None
    
    for col in df.columns:
        col_str = str(col).strip().lower()
        if 'id' in col_str:
            id_column = col
        elif 'キャンペーン' in col_str:
            campaign_column = col
            
    if not id_column or not campaign_column:
        raise ValueError("必要なカラムが見つかりません")
        
    return id_column, campaign_column

def process_cooccurrence_file(filepath, original_filename):
    try:
        # ファイルの拡張子を取得
        file_ext = original_filename.rsplit('.', 1)[1].lower()
        
        # ファイルの読み込みとヘッダー行の特定
        try:
            header_row, df = find_header_row(filepath, file_ext)
        except Exception as e:
            logger.error(f"ヘッダー行の特定に失敗: {str(e)}")
            raise ValueError("データ構造を認識できませんでした。ファイルを確認してください。")
        
        # 必要なカラム名を特定
        try:
            id_column, campaign_column = get_column_names(df)
        except Exception as e:
            logger.error(f"カラム名の特定に失敗: {str(e)}")
            raise ValueError("必要なカラムが見つかりません。")

        # 必要な列のみを抽出
        data = df[[id_column, campaign_column]].copy()
        
        # 列名を標準化
        data.columns = ["見込客/担当者ID18", "キャンペーン名"]
        
        # ここから共起行列生成の処理を改善
        # Step 1: キャンペーン名のユニーク化とソート
        unique_campaigns = sorted(data["キャンペーン名"].unique())
        
        # Step 2: 初期化時にIndexとColumnsを設定
        co_occurrence_matrix = pd.DataFrame(0, 
                                         index=unique_campaigns, 
                                         columns=unique_campaigns)
        
        # Step 3: ユーザーごとのグループ処理を改善
        for _, group in data.groupby("見込客/担当者ID18"):
            # 各ユーザーのユニークなキャンペーン
            campaigns = group["キャンペーン名"].unique()
            
            # 2つ以上のキャンペーンがある場合のみ処理
            if len(campaigns) >= 2:
                # すべての組み合わせについて処理
                for i in range(len(campaigns)):
                    for j in range(i + 1, len(campaigns)):
                        camp1, camp2 = campaigns[i], campaigns[j]
                        # 両方向に加算
                        co_occurrence_matrix.at[camp1, camp2] += 1
                        co_occurrence_matrix.at[camp2, camp1] += 1
        
        # Step 4: 合計行と列を追加
        co_occurrence_matrix['合計'] = co_occurrence_matrix.sum(axis=1)
        total_row = co_occurrence_matrix.sum()
        co_occurrence_matrix.loc['合計'] = total_row

        # 出力処理
        output_filename = f"共起行列-{os.path.splitext(original_filename)[0]}.{file_ext}"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)
        
        if file_ext == 'csv':
            co_occurrence_matrix.to_csv(output_filepath, encoding='utf-8-sig')
        else:  # xlsx
            co_occurrence_matrix.to_excel(output_filepath)

        return output_filename

    except Exception as e:
        logger.error(f"ファイル処理エラー: {str(e)}", exc_info=True)
        raise

def process_campaign_file(filepath, original_filename):
    try:
        # ファイルの拡張子を取得
        file_ext = original_filename.rsplit('.', 1)[1].lower()
        
        # ファイルの読み込みとヘッダー行の特定
        try:
            header_row, df = find_header_row(filepath, file_ext)
        except Exception as e:
            logger.error(f"ヘッダー行の特定に失敗: {str(e)}")
            raise ValueError("データ構造を認識できませんでした。ファイルを確認してください。")
        
        # 必要なカラム名を特定
        try:
            _, campaign_column = get_column_names(df)
        except Exception as e:
            logger.error(f"カラム名の特定に失敗: {str(e)}")
            raise ValueError("必要なカラムが見つかりません。")
        
        # キャンペーン名のクリーニング
        df[campaign_column] = df[campaign_column].apply(clean_campaign_name)
        
        # 入力ファイルと同じ拡張子で出力
        output_filename = f"cleaned_{sanitize_filename(original_filename)}"
        output_filepath = os.path.join(app.config["OUTPUT_FOLDER"], output_filename)
        
        if file_ext == 'csv':
            df.to_csv(output_filepath, encoding='utf-8-sig', index=False)
        else:  # xlsx
            df.to_excel(output_filepath, index=False)

        return output_filename

    except Exception as e:
        logger.error(f"ファイル処理エラー: {str(e)}", exc_info=True)
        raise

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
    try:
        if 'files[]' not in request.files:
            return jsonify({'error': 'ファイルがありません'}), 400
        
        files = request.files.getlist('files[]')
        uploaded_files = []
        
        for file in files:
            if file and allowed_file(file.filename):
                filename = sanitize_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                uploaded_files.append(filename)
        
        if not uploaded_files:
            return jsonify({'error': '有効なファイルがありません。CSVまたはXLSXファイルを選択してください。'}), 400
        
        return jsonify({
            'success': True,
            'files': uploaded_files
        })

    except Exception as e:
        logger.error(f"アップロードエラー: {str(e)}", exc_info=True)
        return jsonify({'error': f'ファイルアップロード中にエラーが発生しました: {str(e)}'}), 500

@app.route('/process_cooccurrence', methods=['POST'])
def process_cooccurrence_files():
    """共起行列生成処理"""
    try:
        filenames = request.json.get('files', [])
        if not filenames:
            return jsonify({'error': '処理するファイルがありません'}), 400

        output_files = []
        errors = []
        
        for filename in filenames:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(filepath):
                try:
                    future = executor.submit(process_cooccurrence_file, filepath, filename)
                    output_files.append(future)
                except Exception as e:
                    errors.append(f"{filename}: {str(e)}")
        
        results = []
        for future in output_files:
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                errors.append(str(e))

        if errors:
            return jsonify({
                'success': False,
                'errors': errors
            }), 400

        session['output_files'] = results
        
        return jsonify({
            'success': True,
            'redirect': url_for('complete_cooccurrence')
        })

    except Exception as e:
        logger.error(f"処理エラー: {str(e)}", exc_info=True)
        return jsonify({'error': f'処理中にエラーが発生しました: {str(e)}'}), 500

@app.route('/process_campaign', methods=['POST'])
def process_campaign_files():
    """キャンペーン名クリーニング処理"""
    try:
        filenames = request.json.get('files', [])
        if not filenames:
            return jsonify({'error': '処理するファイルがありません'}), 400

        output_files = []
        errors = []
        
        for filename in filenames:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(filepath):
                try:
                    future = executor.submit(process_campaign_file, filepath, filename)
                    output_files.append(future)
                except Exception as e:
                    errors.append(f"{filename}: {str(e)}")
        
        results = []
        for future in output_files:
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                errors.append(str(e))

        if errors:
            return jsonify({
                'success': False,
                'errors': errors
            }), 400

        session['output_files'] = results
        
        return jsonify({
            'success': True,
            'redirect': url_for('complete_campaign')
        })

    except Exception as e:
        logger.error(f"処理エラー: {str(e)}", exc_info=True)
        return jsonify({'error': f'処理中にエラーが発生しました: {str(e)}'}), 500

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

        # ファイルの種類に応じてMIMEタイプを設定
        file_ext = filename.rsplit('.', 1)[1].lower()
        if file_ext == 'xlsx':
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            mimetype = 'text/csv;charset=utf-8'

        response = send_file(
            filepath,
            as_attachment=True,
            mimetype=mimetype,
            download_name=filename
        )
        response.headers["Content-Disposition"] = \
            f"attachment; filename*=UTF-8''{quote(filename)}"
        
        return response

    except Exception as e:
        logger.error(f"ダウンロードエラー: {str(e)}", exc_info=True)
        return jsonify({'error': 'ダウンロードに失敗しました'}), 500

# エラーハンドラー
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'ページが見つかりません'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'サーバー内部エラーが発生しました'}), 500

if __name__ == "__main__":
    app.run(debug=False)