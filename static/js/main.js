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

    // ファイル選択時のイベント
    fileInput?.addEventListener('change', (e) => {
        const selectedFiles = e.target.files;
        if (selectedFiles.length > 0) {
            displayFileList(selectedFiles);
            uploadFiles(selectedFiles);
        } else {
            resetUI();
        }
    });

    // ドラッグ＆ドロップ関連
    const preventDefaults = (e) => {
        e.preventDefault();
        e.stopPropagation();
    };

    const highlight = () => dropZone.classList.add('highlight');
    const unhighlight = () => dropZone.classList.remove('highlight');

    const handleDrop = (e) => {
        const dt = e.dataTransfer;
        const droppedFiles = dt.files;
        fileInput.files = droppedFiles;
        fileInput.dispatchEvent(new Event('change'));
    };

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

    const formatFileSize = (bytes) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
    };

    // ファイルアップロード
    const uploadFiles = async (files) => {
        progressContainer.style.display = 'block';
        processSection.style.display = 'none';
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
                    const response = JSON.parse(xhr.responseText);
                    if (response.success) {
                        uploadedFiles = response.files;
                        completeUpload();
                    } else {
                        showError('アップロードに失敗しました');
                    }
                } else {
                    showError('サーバーエラーが発生しました');
                }
            };

            xhr.onerror = () => showError('ネットワークエラーが発生しました');
            xhr.send(formData);
        } catch (error) {
            showError(`エラーが発生しました: ${error.message}`);
        }
    };

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
        uploadStatus.textContent = message;
        uploadStatus.style.color = 'red';
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

    // 処理ボタンのクリックイベント
    processButton?.addEventListener('click', async () => {
        processButton.disabled = true;
        processStatus.style.display = 'block';
        processButton.querySelector('.button-content').innerHTML = `
            <div class="loading-spinner"></div>
            <span class="button-text">処理中...</span>
        `;
        try {
            const isMatrixTool = document.title.includes('共起行列');
            const endpoint = isMatrixTool ? '/process_cooccurrence' : '/process_campaign';
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: uploadedFiles }),
            });
            const data = await response.json();
            if (data.success && data.redirect) {
                window.location.href = data.redirect;
            } else {
                throw new Error('処理に失敗しました');
            }
        } catch (error) {
            showError(error.message);
            processButton.disabled = false;
            processStatus.style.display = 'none';
            processButton.querySelector('.button-content').innerHTML = `
                <span class="button-text">🚀 処理を開始</span>
            `;
        }
    });
});
