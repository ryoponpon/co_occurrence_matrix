document.addEventListener('DOMContentLoaded', () => {
    // 既存のDOM要素の参照
    const uploadForm = document.getElementById('upload-form');
    const fileInput = document.getElementById('files');
    const fileList = document.getElementById('file-names');
    const fileListContainer = document.getElementById('file-list');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.querySelector('.progress-bar');
    const uploadStatus = document.getElementById('upload-status');
    const processButton = document.getElementById('process-button');
    const processSection = document.getElementById('process-section');
    const processStatus = document.getElementById('process-status');
    const dropZone = document.querySelector('.custom-file-input');
    let uploadedFiles = [];

    window.addEventListener('error', function(event) {
        console.error('Script error:', event.error);
        // エラーが Chrome 拡張機能関連の場合は無視
        if (event.filename?.includes('chrome-extension://')) {
            event.preventDefault();
            return;
        }
    });


    // ユーティリティ関数
    const preventDefaults = (e) => {
        e.preventDefault();
        e.stopPropagation();
    };

    const highlight = () => dropZone?.classList.add('highlight');
    const unhighlight = () => dropZone?.classList.remove('highlight');

    const formatFileSize = (bytes) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
    };

    // UI更新関数
    const updateProgress = (percent) => {
        const roundedPercent = Math.round(percent);
        progressBar.style.width = `${roundedPercent}%`;
        progressBar.textContent = `${roundedPercent}%`;
        uploadStatus.textContent = 'アップロード中...';
    };

    const completeUpload = () => {
        uploadStatus.textContent = 'アップロード完了！';
        progressBar.style.width = '100%';
        progressBar.textContent = '100%';
        processSection.style.display = 'block';
    };

    const showError = (message) => {
        console.error('Error details:', message);
        if (uploadStatus) {
            uploadStatus.textContent = message;
            uploadStatus.style.color = 'red';
        }
        // エラーメッセージをより目立つように表示
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.style.color = 'red';
        errorDiv.style.padding = '10px';
        errorDiv.style.marginTop = '10px';
        errorDiv.style.border = '1px solid red';
        errorDiv.textContent = message;
        
        // 既存のエラーメッセージがあれば削除
        const existingError = document.querySelector('.error-message');
        if (existingError) {
            existingError.remove();
        }
        
        // 新しいエラーメッセージを追加
        processSection.parentNode.insertBefore(errorDiv, processSection);
    };

    const resetUI = () => {
        fileListContainer.style.display = 'none';
        progressContainer.style.display = 'none';
        processSection.style.display = 'none';
        fileList.innerHTML = '';
        progressBar.style.width = '0%';
        progressBar.textContent = '0%';
        uploadStatus.textContent = '';
        uploadStatus.style.color = '';
    };

    // ファイルリスト表示
    const displayFileList = (files) => {
        fileList.innerHTML = '';
        Array.from(files).forEach(file => {
            const li = document.createElement('li');
            li.textContent = `${file.name} (${formatFileSize(file.size)})`;
            fileList.appendChild(li);
        });
        fileListContainer.style.display = 'block';
    };

    // ファイルアップロード処理
    const uploadFiles = async (files) => {
        if (!files || files.length === 0) {
            showError('ファイルが選択されていません');
            return;
        }
    
        progressContainer.style.display = 'block';
        processSection.style.display = 'none';
        const formData = new FormData();
        
        // ファイルの検証
        for (let file of files) {
            if (!file.name.match(/\.(csv|xlsx)$/i)) {
                showError('未対応のファイル形式です。CSVまたはXLSXファイルを選択してください。');
                return;
            }
            formData.append('files[]', file);
        }
    
        try {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/upload', true);
    
            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    updateProgress((e.loaded / e.total) * 100);
                }
            };
    
            xhr.onload = () => {
                try {
                    const response = JSON.parse(xhr.responseText);
                    console.log('Upload response:', response);  // デバッグ用
    
                    if (xhr.status === 200 && response.success) {
                        uploadedFiles = response.files;
                        completeUpload();
                    } else {
                        showError(response.error || 'アップロードに失敗しました');
                    }
                } catch (e) {
                    console.error('Response parsing error:', e);
                    showError('レスポンスの解析に失敗しました');
                }
            };
    
            xhr.onerror = () => {
                console.error('XHR error:', xhr.statusText);
                showError('ネットワークエラーが発生しました');
            };
    
            xhr.send(formData);
        } catch (error) {
            console.error('Upload error:', error);
            showError(`エラーが発生しました: ${error.message}`);
        }
    };

    // ファイル処理
    const processFiles = async () => {
        if (!uploadedFiles || uploadedFiles.length === 0) {
            showError('処理するファイルがありません');
            return;
        }
    
        try {
            const isMatrixTool = document.title.includes('共起行列');
            const endpoint = isMatrixTool ? '/process_cooccurrence' : '/process_campaign';
    
            // 処理状態の更新
            if (processButton) {
                processButton.disabled = true;
            }
            if (processStatus) {
                processStatus.style.display = 'block';
            }
    
            console.log('Sending request:', {
                endpoint,
                files: uploadedFiles
            });
    
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                credentials: 'include',
                body: JSON.stringify({ files: uploadedFiles })
            });
    
            // レスポンスの内容をログ出力（デバッグ用）
            const responseText = await response.text();
            console.log('Raw response:', responseText);
    
            let data;
            try {
                data = JSON.parse(responseText);
            } catch (e) {
                console.error('JSON parse error:', e);
                throw new Error('サーバーからの応答を解析できませんでした');
            }
    
            if (!response.ok) {
                throw new Error(data.error || `サーバーエラー (${response.status})`);
            }
    
            if (data.success && data.redirect) {
                window.location.href = data.redirect;
            } else {
                throw new Error(data.error || '処理に失敗しました');
            }
    
        } catch (error) {
            console.error('Processing error:', error);
            showError(error.message || 'ファイルの処理中にエラーが発生しました');
        } finally {
            // UI状態のリセット
            if (processButton) {
                processButton.disabled = false;
            }
            if (processStatus) {
                processStatus.style.display = 'none';
            }
            if (processButton?.querySelector('.button-content')) {
                processButton.querySelector('.button-content').innerHTML = `
                    <span class="button-text">🚀 処理を開始</span>
                `;
            }
        }
    };
    
    // イベントリスナー
    fileInput?.addEventListener('change', (e) => {
        const selectedFiles = e.target.files;
        if (selectedFiles.length > 0) {
            displayFileList(selectedFiles);
            uploadFiles(selectedFiles);
        } else {
            resetUI();
        }
    });

    // ドラッグ＆ドロップイベント
    dropZone?.addEventListener('dragover', (e) => {
        preventDefaults(e);
        highlight();
    });

    dropZone?.addEventListener('dragleave', (e) => {
        preventDefaults(e);
        unhighlight();
    });

    dropZone?.addEventListener('drop', (e) => {
        preventDefaults(e);
        unhighlight();
        handleDrop(e);
    });

    // 処理ボタンのイベント
    processButton?.addEventListener('click', async () => {
        processButton.disabled = true;
        processStatus.style.display = 'block';
        processButton.querySelector('.button-content').innerHTML = `
            <div class="loading-spinner"></div>
            <span class="button-text">処理中...</span>
        `;
        await processFiles();
    });

    // ドロップ処理
    const handleDrop = (e) => {
        const dt = e.dataTransfer;
        const droppedFiles = dt.files;
        fileInput.files = droppedFiles;
        fileInput.dispatchEvent(new Event('change'));
    };
});