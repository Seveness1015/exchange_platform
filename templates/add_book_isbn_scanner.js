// ============================================================
// ISBN 掃描功能（獨立功能，用於快速填入書籍資訊）
// ============================================================

let isbnScannerStream = null;
let isbnScannerImageData = null;

// 開啟 ISBN 掃描器
async function openISBNScanner() {
    // 創建掃描器容器（如果不存在）
    let scannerContainer = document.getElementById('isbnScannerContainer');
    if (!scannerContainer) {
        scannerContainer = document.createElement('div');
        scannerContainer.id = 'isbnScannerContainer';
        scannerContainer.className = 'isbn-scanner-modal';
        scannerContainer.innerHTML = `
            <div class="isbn-scanner-content">
                <div class="isbn-scanner-header">
                    <h3>掃描 ISBN 條碼</h3>
                    <button type="button" class="scanner-close-btn" onclick="closeISBNScanner()">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="isbn-scanner-body">
                    <div id="isbn_scanner_camera_container" class="camera-container">
                        <div style="flex: 1; overflow: hidden; border-radius: 8px 8px 0 0;">
                            <video id="isbn_scanner_camera" autoplay playsinline style="width: 100%; height: 100%; object-fit: contain;"></video>
                        </div>
                        <canvas id="isbn_scanner_canvas" style="display: none;"></canvas>
                        <div class="camera-actions">
                            <button type="button" class="capture-btn" onclick="captureISBNPhoto()">
                                <i class="fas fa-camera"></i>
                                <span>拍照掃描</span>
                            </button>
                            <button type="button" class="cancel-btn" onclick="closeISBNScanner()">
                                <i class="fas fa-times"></i>
                                <span>取消</span>
                            </button>
                        </div>
                    </div>
                    <div id="isbn_scanner_preview" class="image-preview" style="display: none;"></div>
                </div>
            </div>
        `;
        document.body.appendChild(scannerContainer);
    }
    
    scannerContainer.style.display = 'flex';
    
    try {
        // 請求相機權限
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: 'environment', // 使用後置相機
                width: { ideal: 1280 },
                height: { ideal: 720 }
            }
        });
        
        isbnScannerStream = stream;
        const video = document.getElementById('isbn_scanner_camera');
        video.srcObject = stream;
    } catch (error) {
        console.error('無法開啟相機:', error);
        alert('無法開啟相機，請確認已授予相機權限');
        closeISBNScanner();
    }
}

// 關閉 ISBN 掃描器
function closeISBNScanner() {
    const scannerContainer = document.getElementById('isbnScannerContainer');
    if (scannerContainer) {
        scannerContainer.style.display = 'none';
    }
    
    // 關閉相機流
    if (isbnScannerStream) {
        isbnScannerStream.getTracks().forEach(track => track.stop());
        isbnScannerStream = null;
    }
    
    const video = document.getElementById('isbn_scanner_camera');
    if (video) {
        video.srcObject = null;
    }
}

// 拍攝 ISBN 條碼照片
function captureISBNPhoto() {
    const video = document.getElementById('isbn_scanner_camera');
    const canvas = document.getElementById('isbn_scanner_canvas');
    const preview = document.getElementById('isbn_scanner_preview');
    
    if (!video || !canvas) return;
    
    // 設置 canvas 尺寸
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    // 繪製當前畫面到 canvas
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    // 轉換為 blob 並顯示預覽
    canvas.toBlob(function(blob) {
        const imageUrl = URL.createObjectURL(blob);
        preview.innerHTML = `<img src="${imageUrl}" alt="預覽圖" class="preview-img">`;
        preview.style.display = 'block';
        
        // 儲存圖片數據用於條碼掃描
        isbnScannerImageData = imageUrl;
        
        // 關閉相機
        closeISBNScanner();
        
        // 自動掃描 ISBN
        setTimeout(() => scanISBNForQuickFill('isbn_scanner'), 500);
    }, 'image/jpeg', 0.9);
}

// 從圖片掃描 ISBN（用於快速填入）
async function scanISBNForQuickFill(type) {
    let img;
    
    if (type === 'isbn_scanner') {
        const preview = document.getElementById('isbn_scanner_preview');
        img = preview ? preview.querySelector('img') : null;
    } else {
        const preview = document.getElementById(`${type}_preview`);
        img = preview ? preview.querySelector('img') : null;
    }
    
    const isbnInput = document.getElementById('isbn');
    
    if (!img) {
        alert('請先拍攝條碼圖片');
        return;
    }
    
    try {
        // 顯示掃描中提示
        const originalText = isbnInput.placeholder || '';
        isbnInput.placeholder = '正在掃描條碼...';
        isbnInput.disabled = true;
        
        // 使用 ZXing 掃描條碼
        const codeReader = new ZXing.BrowserMultiFormatReader();
        
        // 創建新的圖片元素用於掃描
        const image = new Image();
        image.crossOrigin = 'anonymous';
        image.src = img.src;
        
        image.onload = async function() {
            try {
                // 使用 ZXing 掃描（支援多種條碼格式，包括 EAN-13、EAN-8、UPC-A 等）
                const result = await codeReader.decodeFromImageElement(image);
                
                if (result && result.text) {
                    // 清理條碼文字（移除非數字字元）
                    let isbn = result.text.replace(/[^0-9]/g, '');
                    
                    // 驗證是否為 ISBN（ISBN-10 或 ISBN-13）
                    // ISBN-13 通常以 978 或 979 開頭
                    if (isbn.length === 13 && (isbn.startsWith('978') || isbn.startsWith('979'))) {
                        // 找到 ISBN，自動填入並獲取書籍資訊
                        await fillBookInfoFromISBN(isbn);
                    } else if (isbn.length === 10) {
                        // ISBN-10，轉換為 ISBN-13 或直接使用
                        await fillBookInfoFromISBN(isbn);
                    } else if (isbn.length === 12) {
                        // 可能是 UPC-A，轉換為 ISBN-13（添加 978 前綴）
                        const isbn13 = '978' + isbn;
                        await fillBookInfoFromISBN(isbn13);
                    } else {
                        // 如果不是標準 ISBN，也嘗試查詢
                        isbnInput.value = result.text;
                        isbnInput.placeholder = '請確認 ISBN 是否正確';
                        alert(`掃描到條碼: ${result.text}\n正在查詢書籍資訊...`);
                        await fillBookInfoFromISBN(result.text);
                    }
                } else {
                    alert('無法從圖片中識別條碼，請確保條碼清晰可見');
                    isbnInput.disabled = false;
                    if (originalText) {
                        isbnInput.placeholder = originalText;
                    }
                }
            } catch (scanError) {
                console.error('條碼掃描失敗:', scanError);
                // 嘗試使用不同的掃描方法
                try {
                    // 使用 decodeFromImageUrl 作為備用方法
                    const result = await codeReader.decodeFromImageUrl(img.src);
                    if (result && result.text) {
                        const isbn = result.text.replace(/[^0-9]/g, '');
                        await fillBookInfoFromISBN(isbn.length === 10 || isbn.length === 13 ? isbn : result.text);
                    } else {
                        throw new Error('無法識別條碼');
                    }
                } catch (retryError) {
                    console.error('備用掃描方法也失敗:', retryError);
                    alert('無法掃描條碼，請確保條碼清晰可見，或手動輸入 ISBN');
                    isbnInput.disabled = false;
                    if (originalText) {
                        isbnInput.placeholder = originalText;
                    }
                }
            }
        };
        
        image.onerror = function() {
            isbnInput.disabled = false;
            if (originalText) {
                isbnInput.placeholder = originalText;
            }
            alert('圖片載入失敗，請重新拍攝');
        };
        
    } catch (error) {
        console.error('掃描錯誤:', error);
        alert('掃描功能發生錯誤，請手動輸入 ISBN');
        isbnInput.disabled = false;
        isbnInput.placeholder = '請手動輸入 ISBN';
    }
}

// 根據 ISBN 從 Google Books API 獲取書籍資訊並自動填入
async function fillBookInfoFromISBN(isbn) {
    const isbnInput = document.getElementById('isbn');
    const titleInput = document.getElementById('book_title');
    const authorInput = document.getElementById('author');
    
    if (!isbn) {
        alert('ISBN 不能為空');
        return;
    }
    
    try {
        // 先填入 ISBN
        isbnInput.value = isbn;
        isbnInput.placeholder = '正在查詢書籍資訊...';
        
        // 顯示載入提示
        const loadingMsg = document.createElement('div');
        loadingMsg.id = 'bookInfoLoading';
        loadingMsg.className = 'book-info-loading';
        loadingMsg.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在查詢書籍資訊...';
        const isbnGroup = document.querySelector('.isbn-input-group');
        if (isbnGroup && isbnGroup.parentElement) {
            isbnGroup.parentElement.insertBefore(loadingMsg, isbnGroup.nextSibling);
        }
        
        // 調用 Google Books API 查詢
        const response = await fetch(`/api/google_books/search?q=isbn:${encodeURIComponent(isbn)}`);
        const data = await response.json();
        
        // 移除載入提示
        if (loadingMsg.parentElement) {
            loadingMsg.remove();
        }
        
        if (data.success && data.books && data.books.length > 0) {
            // 找到書籍資訊，自動填入
            const book = data.books[0]; // 使用第一個結果
            
            if (titleInput && book.title) {
                titleInput.value = book.title;
            }
            
            if (authorInput && book.authors) {
                // authors 可能是陣列或字串
                if (Array.isArray(book.authors)) {
                    authorInput.value = book.authors.join(', ');
                } else {
                    authorInput.value = book.authors;
                }
            }
            
            isbnInput.placeholder = 'ISBN 已掃描並填入書籍資訊';
            
            // 顯示成功訊息
            showBookInfoMessage('書籍資訊已自動填入！', 'success');
        } else {
            // 未找到書籍資訊
            isbnInput.placeholder = '未找到書籍資訊，請手動填寫';
            showBookInfoMessage('未找到此 ISBN 的書籍資訊，請手動填寫書名和作者。', 'warning');
        }
        
        isbnInput.disabled = false;
        
    } catch (error) {
        console.error('查詢書籍資訊失敗:', error);
        isbnInput.disabled = false;
        isbnInput.placeholder = '查詢失敗，請手動填寫';
        showBookInfoMessage('查詢書籍資訊時發生錯誤，請手動填寫。', 'error');
    }
}

// 顯示書籍資訊訊息
function showBookInfoMessage(message, type) {
    // 移除舊的訊息
    const oldMsg = document.getElementById('bookInfoMessage');
    if (oldMsg) {
        oldMsg.remove();
    }
    
    // 創建新訊息
    const messageDiv = document.createElement('div');
    messageDiv.id = 'bookInfoMessage';
    messageDiv.className = `book-info-message ${type}`;
    messageDiv.innerHTML = `
        <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'warning' ? 'fa-exclamation-triangle' : 'fa-exclamation-circle'}"></i>
        <span>${message}</span>
        <button type="button" class="message-close" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    const isbnGroup = document.querySelector('.isbn-input-group');
    if (isbnGroup && isbnGroup.parentElement) {
        isbnGroup.parentElement.insertBefore(messageDiv, isbnGroup.nextSibling);
    }
    
    // 3 秒後自動隱藏成功訊息
    if (type === 'success') {
        setTimeout(() => {
            if (messageDiv && messageDiv.parentElement) {
                messageDiv.remove();
            }
        }, 3000);
    }
}


