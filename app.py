from flask import Flask, request, render_template, send_file, redirect, url_for
import pandas as pd
from itertools import combinations
import os

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        uploaded_files = request.files.getlist('files')  # 複数ファイル対応
        uploaded_filenames = []

        for file in uploaded_files:
            if file and file.filename != '':
                filepath = os.path.join(UPLOAD_FOLDER, file.filename)
                file.save(filepath)
                uploaded_filenames.append(file.filename)

                # ファイル処理
                process_file(filepath, file.filename)

        return redirect(url_for('complete', uploaded_files=uploaded_filenames))

    return render_template('index.html')

def process_file(filepath, filename):
    try:
        data = pd.read_csv(filepath)
        if 'メール' not in data.columns or 'キャンペーン名' not in data.columns:
            raise ValueError("CSVに必要な列が含まれていません: 'メール' と 'キャンペーン名'")

        # 共起行列生成
        data = data[['メール', 'キャンペーン名']]
        co_occurrence_counts = {}
        for _, group in data.groupby('メール'):
            campaign_names = group['キャンペーン名'].unique()
            for item1, item2 in combinations(campaign_names, 2):
                if item1 != item2:
                    if (item1, item2) in co_occurrence_counts:
                        co_occurrence_counts[(item1, item2)] += 1
                    elif (item2, item1) in co_occurrence_counts:
                        co_occurrence_counts[(item2, item1)] += 1
                    else:
                        co_occurrence_counts[(item1, item2)] = 1

        campaigns = sorted(data['キャンペーン名'].unique())
        co_occurrence_matrix = pd.DataFrame(0, index=campaigns, columns=campaigns)
        for (item1, item2), count in co_occurrence_counts.items():
            co_occurrence_matrix.loc[item1, item2] = count
            co_occurrence_matrix.loc[item2, item1] = count

        # ファイル保存
        output_filepath = os.path.join(OUTPUT_FOLDER, f"co_occurrence_matrix_{filename}")
        co_occurrence_matrix.to_csv(output_filepath, encoding='utf-8-sig')

    except Exception as e:
        print(f"エラー: {e}")

@app.route('/complete')
def complete():
    uploaded_files = request.args.getlist('uploaded_files')
    output_files = os.listdir(OUTPUT_FOLDER)
    return render_template('complete.html', uploaded_files=uploaded_files, output_files=output_files)

@app.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "ファイルが見つかりません", 404

if __name__ == '__main__':
    app.run(debug=True)
