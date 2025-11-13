// 搜尋功能
document.addEventListener("DOMContentLoaded", function() {
    const searchBtn = document.getElementById('searchBtn');
    const searchInput = document.getElementById('searchInput');
    const aiBtn = document.getElementById('aiBtn');
    
    // 搜尋按鈕點擊事件
    if (searchBtn) {
        searchBtn.addEventListener('click', function() {
            performSearch();
        });
    }
    
    // 搜尋輸入欄 Enter 鍵事件
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                performSearch();
            }
        });
    }
    
    // AI 按鈕點擊事件
    if (aiBtn) {
        aiBtn.addEventListener('click', function() {
            // AI 推薦功能（待實現）
            alert('AI 推薦功能即將推出！');
        });
    }
});

// 執行搜尋
function performSearch() {
    const searchType = document.getElementById('searchType').value;
    const searchQuery = document.getElementById('searchInput').value.trim();
    
    if (!searchQuery) {
        alert('請輸入搜尋關鍵字');
        return;
    }
    
    // 導航到搜尋結果頁面
    const searchUrl = `/search?type=${encodeURIComponent(searchType)}&q=${encodeURIComponent(searchQuery)}`;
    window.location.href = searchUrl;
}

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