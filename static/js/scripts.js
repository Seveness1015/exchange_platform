// 監聽 Offcanvas 開啟與關閉事件
var offcanvasElement = document.getElementById('offcanvasLeft');
var toggleButton = document.getElementById('toggleButton');

offcanvasElement.addEventListener('show.bs.offcanvas', function () {
    toggleButton.classList.add('hide-btn');
});

offcanvasElement.addEventListener('hidden.bs.offcanvas', function () {
    toggleButton.classList.remove('hide-btn');
});

// 動態顯示收藏項目
document.addEventListener("DOMContentLoaded", function() {
    fetch("/get_favorites")
        .then(response => response.json())
        .then(data => {
            const favoritesContainer = document.getElementById("favoritesContainer");
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