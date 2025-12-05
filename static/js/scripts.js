// 執行 Google Books 搜尋（在首頁執行）
function performGoogleBooksSearch() {
    console.log('scripts.js performGoogleBooksSearch 被調用');
    const searchInput = document.getElementById('searchInput');
    if (!searchInput) {
        console.error('找不到搜尋輸入欄');
        return;
    }
    
    const searchQuery = searchInput.value.trim();
    console.log('搜尋關鍵字:', searchQuery);
    
    if (!searchQuery) {
        alert('請輸入搜尋關鍵字');
        return;
    }
    
    // 如果頁面有 window.performGoogleBooksSearchImpl 函數（在 index.html 中定義），使用它
    // 使用不同的函數名避免無限遞迴
    if (typeof window.performGoogleBooksSearchImpl === 'function') {
        console.log('調用 window.performGoogleBooksSearchImpl');
        window.performGoogleBooksSearchImpl();
    } else {
        console.log('window.performGoogleBooksSearchImpl 不存在，導航到首頁');
        // 如果不在首頁，導航到首頁並執行搜尋
        window.location.href = `/?q=${encodeURIComponent(searchQuery)}`;
    }
}

// 搜尋功能 - 使用 Google Books API
document.addEventListener("DOMContentLoaded", function() {
    console.log('scripts.js DOMContentLoaded 執行');
    const searchBtn = document.getElementById('searchBtn');
    const searchInput = document.getElementById('searchInput');
    const aiBtn = document.getElementById('aiBtn');
    
    console.log('searchBtn:', searchBtn);
    console.log('searchInput:', searchInput);
    console.log('window.performGoogleBooksSearchImpl:', typeof window.performGoogleBooksSearchImpl);
    
    // 搜尋按鈕點擊事件
    if (searchBtn) {
        searchBtn.addEventListener('click', function(e) {
            e.preventDefault();
            console.log('搜尋按鈕被點擊');
            performGoogleBooksSearch();
        });
    } else {
        console.error('找不到搜尋按鈕');
    }
    
    // 搜尋輸入欄 Enter 鍵事件
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                console.log('Enter 鍵被按下');
                performGoogleBooksSearch();
            }
        });
    } else {
        console.error('找不到搜尋輸入欄');
    }
    
    // AI 按鈕點擊事件
    if (aiBtn) {
        aiBtn.addEventListener('click', function() {
            // 導航到 AI 推薦頁面
            window.location.href = '/ai_recommend';
        });
    }
});

// 監聽 Offcanvas 開啟與關閉事件（如果存在）
var offcanvasElement = document.getElementById('offcanvasLeft');
var toggleButton = document.getElementById('toggleButton');

if (offcanvasElement && toggleButton) {
    offcanvasElement.addEventListener('show.bs.offcanvas', function () {
        if (toggleButton) {
            toggleButton.classList.add('hide-btn');
        }
    });

    offcanvasElement.addEventListener('hidden.bs.offcanvas', function () {
        if (toggleButton) {
            toggleButton.classList.remove('hide-btn');
        }
    });
}

// 動態顯示收藏項目（如果頁面有收藏容器）
document.addEventListener("DOMContentLoaded", function() {
    const favoritesContainer = document.getElementById("favoritesContainer");
    if (favoritesContainer) {
        fetch("/get_favorites")
            .then(response => response.json())
            .then(data => {
                favoritesContainer.innerHTML = ""; // 清空內容

                data.favorites.forEach(item => {
                    const itemElement = document.createElement("div");
                    itemElement.classList.add("col-md-4", "mb-4");
                    itemElement.innerHTML = `
                        <div class="card shadow-sm">
                            <img src="${item.image}" class="card-img-top" alt="${item.name}">
                            <div class="card-body">
                                <h5 class="card-title">${item.name}</h5>
                                <button class="btn btn-danger" onclick="removeFavorite('${item.id}')">
                                    <i class="fas fa-heart"></i>
                                </button>
                            </div>
                        </div>
                    `;
                    favoritesContainer.appendChild(itemElement);
                });
            })
            .catch(error => console.error("Error loading favorites:", error));
    }
});

function removeFavorite(itemId) {
    fetch(`/remove_favorite/${itemId}`, { method: "DELETE" })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload(); // 重新載入頁面以更新收藏列表
            }
        })
        .catch(error => console.error("Error removing favorite:", error));
}