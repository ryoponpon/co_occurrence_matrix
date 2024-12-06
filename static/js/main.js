document.addEventListener('DOMContentLoaded', () => {
    // DOM要素の参照
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
        if (progressBar) {
            progressBar.style.width = `${roundedPercent}%`;
            progressBar.textContent = `${roundedPercent}%`;
        }
        if (uploadStatus) {
            uploadStatus.textContent = 'アップロード中...';
        }
    };

    const completeUpload = () => {
        if (uploadStatus) {
            uploadStatus.textContent = 'アップロード完了！';
            uploadStatus.style.color = 'red';
        }
        if (progressBar) {
            progressBar.style.width = '100%';
            progressBar.textContent = '100%';
        }
        if (processSection) {
            processSection.style.display = 'block';
        }
    };

    const showError = (message) => {
        console.error('Error:', message);
        
        // エラーメッセージの表示
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.style.cssText = `
            color: red;
            padding: 15px;
            margin: 10px 0;
            border: 1px solid red;
            border-radius: 4px;
            background-color: #fff3f3;
            font-weight: bold;
        `;
        errorDiv.textContent = `エラー: ${message}`;

        // 既存のエラーメッセージを削除
        const existingError = document.querySelector('.error-message');
        if (existingError) {
            existingError.remove();
        }

        // 新しいエラーメッセージを追加
        if (processSection && processSection.parentNode) {
            processSection.parentNode.insertBefore(errorDiv, processSection);
        }

        if (uploadStatus) {
            uploadStatus.textContent = message;
            uploadStatus.style.color = 'red';
        }
    };

    const resetUI = () => {
        if (fileListContainer) fileListContainer.style.display = 'none';
        if (progressContainer) progressContainer.style.display = 'none';
        if (processSection) processSection.style.display = 'none';
        if (fileList) fileList.innerHTML = '';
        if (progressBar) {
            progressBar.style.width = '0%';
            progressBar.textContent = '0%';
        }
        if (uploadStatus) {
            uploadStatus.textContent = '';
            uploadStatus.style.color = '';
        }
    };

    // ファイルリスト表示
    const displayFileList = (files) => {
        if (!fileList) return;
        
        fileList.innerHTML = '';
        Array.from(files).forEach(file => {
            const li = document.createElement('li');
            li.textContent = `${file.name} (${formatFileSize(file.size)})`;
            fileList.appendChild(li);
        });
        if (fileListContainer) {
            fileListContainer.style.display = 'block';
        }
    };

    // ファイルアップロード処理
    const uploadFiles = async (files) => {
        if (!files || files.length === 0) {
            showError('ファイルが選択されていません');
            return;
        }

        // ファイル形式の検証
        const invalidFiles = Array.from(files).filter(file => {
            const extension = file.name.split('.').pop().toLowerCase();
            return !['csv', 'xlsx'].includes(extension);
        });

        if (invalidFiles.length > 0) {
            showError('未対応のファイル形式が含まれています。CSVまたはXLSXファイルのみ処理できます。');
            return;
        }

        if (progressContainer) progressContainer.style.display = 'block';
        if (processSection) processSection.style.display = 'none';

        const formData = new FormData();
        Array.from(files).forEach(file => formData.append('files[]', file));

        try {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/upload', true);

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    updateProgress((e.loaded / e.total) * 100);
                }
            };

            xhr.onload = () => {
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.success) {
                            uploadedFiles = response.files;
                            completeUpload();
                        } else {
                            showError(response.error || 'アップロードに失敗しました');
                        }
                    } catch (e) {
                        showError('レスポンスの解析に失敗しました');
                    }
                } else {
                    showError(`サーバーエラー: ${xhr.status}`);
                }
            };

            xhr.onerror = () => showError('ネットワークエラーが発生しました');
            xhr.send(formData);

        } catch (error) {
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
            if (processButton) processButton.disabled = true;
            if (processStatus) processStatus.style.display = 'block';

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
        if (selectedFiles && selectedFiles.length > 0) {
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
        if (!processButton.disabled) {
            processButton.disabled = true;
            if (processStatus) {
                processStatus.style.display = 'block';
            }
            if (processButton.querySelector('.button-content')) {
                processButton.querySelector('.button-content').innerHTML = `
                    <div class="loading-spinner"></div>
                    <span class="button-text">処理中...</span>
                `;
            }
            try {
                await processFiles();
            } catch (error) {
                showError(error.message || '処理の開始に失敗しました');
                processButton.disabled = false;
                if (processStatus) {
                    processStatus.style.display = 'none';
                }
                if (processButton.querySelector('.button-content')) {
                    processButton.querySelector('.button-content').innerHTML = `
                        <span class="button-text">🚀 処理を開始</span>
                    `;
                }
            }
        }
    });

    // ドロップ処理
    const handleDrop = (e) => {
        const dt = e.dataTransfer;
        const droppedFiles = dt.files;
        if (fileInput) {
            fileInput.files = droppedFiles;
            fileInput.dispatchEvent(new Event('change'));
        }
    };

    // エラーイベントのグローバルハンドリング
    window.addEventListener('error', function(event) {
        console.error('Global error:', event.error);
        if (event.filename?.includes('chrome-extension://')) {
            event.preventDefault();
            return;
        }
        showError('予期せぬエラーが発生しました');
    });

    // Promiseエラーのグローバルハンドリング
    window.addEventListener('unhandledrejection', function(event) {
        console.error('Unhandled promise rejection:', event.reason);
        if (event.reason?.message?.includes('chrome-extension://')) {
            event.preventDefault();
            return;
        }
        showError('非同期処理でエラーが発生しました');
    });
});