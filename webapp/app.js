let tg = window.Telegram.WebApp;
tg.expand();

let session_id = new URLSearchParams(window.location.search).get('session_id');
let serverUrl = window.location.origin;

let rawCards = [];
let filterData = { 'country': [], 'bank': [], 'brand': [], 'type': [], 'level': [] };
let selectedFilters = { 'country': [], 'bank': [], 'brand': [], 'type': [], 'level': [] };
const categories = ['country', 'bank', 'brand', 'type', 'level'];

let currentModalCategory = null;

// Convert ISO-2 Code to Emoji Flag
function getFlagEmoji(countryCode) {
    if (!countryCode || countryCode.length !== 2) return '';
    const codePoints = countryCode
        .toUpperCase()
        .split('')
        .map(char => 127397 + char.charCodeAt());
    return String.fromCodePoint(...codePoints) + ' ';
}

document.addEventListener('DOMContentLoaded', () => {
    // Setup Welcome Screen User Data
    const user = tg.initDataUnsafe?.user;
    const welcomeText = document.getElementById('welcome-text');
    if (user) {
        welcomeText.innerText = `Welcome, ${user.first_name}! 🚀`;
        if (user.photo_url) {
            const img = document.getElementById('user-photo');
            img.src = user.photo_url;
            img.style.display = 'block';
        } else {
            const placeholder = document.getElementById('profile-placeholder');
            placeholder.innerText = user.first_name.charAt(0).toUpperCase();
            placeholder.style.display = 'flex';
        }
    }

    if (!session_id) {
        welcomeText.innerText = 'Error: No session ID';
        document.querySelector('.progress-container').style.display = 'none';
        document.getElementById('progress-text').style.display = 'none';
        return;
    }

    // Fetch data
    fetch(`${serverUrl}/api/get_data?session_id=${session_id}`)
        .then(res => res.json())
        .then(data => {
            if (data.error) throw new Error(data.error);
            rawCards = data.cards || [];
            
            computeFilters(); // Initialize counts
            renderMainFilters();
            
            // Simulate progress bar 
            let progress = 0;
            const progressEl = document.getElementById('progress-bar');
            const progressText = document.getElementById('progress-text');
            
            const interval = setInterval(() => {
                progress += Math.floor(Math.random() * 15) + 5;
                if (progress >= 100) {
                    progress = 100;
                    clearInterval(interval);
                    
                    setTimeout(() => {
                        document.getElementById('welcome-screen').classList.add('hide');
                        setTimeout(() => {
                            document.getElementById('welcome-screen').style.display = 'none';
                            document.getElementById('app').style.display = 'block';
                            
                            // Show Main Button ONLY after loading hits 100% and screen transitions
                            tg.MainButton.text = "APPLY FILTERS";
                            tg.MainButton.color = "#ff4d6d";
                            tg.MainButton.show();
                            tg.MainButton.onClick(submitFilters);
                        }, 600);
                    }, 400);
                }
                progressEl.style.width = progress + '%';
                progressText.innerText = progress + '%';
            }, 80);
        })
        .catch(err => {
            welcomeText.innerText = `Error: ${err.message}`;
            document.querySelector('.progress-container').style.display = 'none';
            document.getElementById('progress-text').style.display = 'none';
        });
});

function computeFilters() {
    let newFilterData = { country: {}, bank: {}, brand: {}, type: {}, level: {} };
    let matchCount = 0;

    // Pass 1: Global count of matching cards
    rawCards.forEach(card => {
        let matchesAll = true;
        for (let cat of categories) {
            if (selectedFilters[cat].length > 0 && !selectedFilters[cat].includes(card[cat])) {
                matchesAll = false; break;
            }
        }
        if (matchesAll) matchCount++;
    });

    // Pass 2: Faceted count per category
    for (let cat of categories) {
        rawCards.forEach(card => {
            let matchesOthers = true;
            for (let otherCat of categories) {
                if (otherCat === cat) continue;
                if (selectedFilters[otherCat].length > 0 && !selectedFilters[otherCat].includes(card[otherCat])) {
                    matchesOthers = false; break;
                }
            }
            if (matchesOthers) {
                const val = card[cat];
                if (!newFilterData[cat][val]) newFilterData[cat][val] = 0;
                newFilterData[cat][val]++;
            }
        });
        
        filterData[cat] = Object.keys(newFilterData[cat]).map(k => ({name: k, count: newFilterData[cat][k]}));
    }
    
    document.getElementById('total-cards').innerText = `${matchCount} cards`;
}

function parseItemName(category, rawName) {
    if (category === 'country') {
        const parts = rawName.split('|');
        const name = parts[0];
        const iso = parts.length > 1 ? parts[1] : '';
        return { display: getFlagEmoji(iso) + name, value: rawName };
    }
    return { display: rawName, value: rawName };
}

function renderMainFilters() {
    const container = document.getElementById('filters-container');
    container.innerHTML = '';
    
    const order = [
        { key: 'country', label: 'Country' },
        { key: 'bank', label: 'Bank' },
        { key: 'brand', label: 'Brand' },
        { key: 'type', label: 'Type' },
        { key: 'level', label: 'Level' }
    ];

    order.forEach(category => {
        if (!filterData[category.key] || filterData[category.key].length === 0) return;

        filterData[category.key].sort((a, b) => b.count - a.count);
        
        const section = document.createElement('div');
        section.className = 'filter-section';

        const header = document.createElement('div');
        header.className = 'filter-header';
        header.innerHTML = `<h3>${category.label}</h3> <button class="select-all" onclick="toggleSelectAll('${category.key}', true)">Select all</button>`;
        section.appendChild(header);

        const grid = document.createElement('div');
        grid.className = 'checkbox-grid';
        grid.id = `grid-${category.key}`;

        const items = filterData[category.key];
        const maxDisplay = 4;
        
        for (let i = 0; i < Math.min(items.length, maxDisplay); i++) {
            grid.appendChild(createMainCheckbox(category.key, items[i]));
        }

        if (items.length > maxDisplay) {
            const moreBtn = document.createElement('label');
            moreBtn.className = 'checkbox-label show-more-btn';
            moreBtn.innerHTML = `<span class="dot"></span>${items.length - maxDisplay} more...`;
            moreBtn.onclick = () => openModal(category.key, category.label);
            grid.appendChild(moreBtn);
        }

        section.appendChild(grid);
        container.appendChild(section);
    });
}

function createMainCheckbox(category, item) {
    const parsed = parseItemName(category, item.name || 'Unknown');
    const label = document.createElement('label');
    label.className = 'checkbox-label';
    if (selectedFilters[category].includes(parsed.value)) label.classList.add('active');
    
    label.onclick = (e) => {
        e.preventDefault();
        toggleFilter(category, parsed.value);
        computeFilters();
        renderMainFilters();
    };

    label.innerHTML = `<span class="dot"></span>${parsed.display} <span class="checkbox-count">(${item.count})</span>`;
    return label;
}

function toggleFilter(category, value) {
    const index = selectedFilters[category].indexOf(value);
    if (index === -1) selectedFilters[category].push(value);
    else selectedFilters[category].splice(index, 1);
}

function toggleSelectAll(category, fromMain = false) {
    const items = filterData[category];
    const allSelected = selectedFilters[category].length === items.length;
    
    selectedFilters[category] = [];
    if (!allSelected) {
        items.forEach(item => selectedFilters[category].push(item.name || 'Unknown'));
    }
    
    computeFilters();
    if (fromMain) renderMainFilters();
    else renderModalList();
}

function openModal(category, label) {
    currentModalCategory = category;
    document.getElementById('modal-title').innerText = label;
    document.getElementById('modal-search-input').value = '';
    document.getElementById('search-modal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
    tg.MainButton.hide(); 
    renderModalList();
}

function closeModal() {
    document.getElementById('search-modal').style.display = 'none';
    document.body.style.overflow = 'auto';
    currentModalCategory = null;
    computeFilters();
    renderMainFilters();
    tg.MainButton.show();
}

function filterModalItems() {
    renderModalList();
}

function renderModalList() {
    const list = document.getElementById('modal-list');
    list.innerHTML = '';
    
    const query = document.getElementById('modal-search-input').value.toLowerCase();
    let items = filterData[currentModalCategory];
    items.sort((a, b) => b.count - a.count); // sort by count in modal too
    
    const selectAllItem = document.createElement('div');
    selectAllItem.className = 'modal-item';
    selectAllItem.style.justifyContent = 'center';
    selectAllItem.style.color = 'var(--accent)';
    selectAllItem.style.fontWeight = 'bold';
    const allSelected = selectedFilters[currentModalCategory].length === items.length;
    selectAllItem.innerText = allSelected ? 'Deselect All' : 'Select All';
    selectAllItem.onclick = () => toggleSelectAll(currentModalCategory, false);
    list.appendChild(selectAllItem);

    items.forEach(item => {
        const parsed = parseItemName(currentModalCategory, item.name || 'Unknown');
        if (query && !parsed.display.toLowerCase().includes(query)) return;
        
        const div = document.createElement('div');
        div.className = 'modal-item';
        const isActive = selectedFilters[currentModalCategory].includes(parsed.value);
        if (isActive) div.classList.add('active');
        
        div.innerHTML = `
            <div class="modal-item-left">
                <div class="modal-item-dot"></div>
                <div class="modal-item-name">${parsed.display}</div>
            </div>
            <div class="modal-item-count">${item.count} cards</div>
        `;
        
        div.onclick = () => {
            toggleFilter(currentModalCategory, parsed.value);
            computeFilters(); // update counts dynamically inside modal!
            renderModalList(); 
        };
        
        list.appendChild(div);
    });
}

function submitFilters() {
    tg.MainButton.showProgress();
    fetch(`${serverUrl}/api/apply_filter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: session_id, filters: selectedFilters })
    })
    .then(res => res.json())
    .then(data => {
        if(data.success) tg.close();
        else {
            alert("Failed to apply filters: " + data.error);
            tg.MainButton.hideProgress();
        }
    })
    .catch(err => {
        alert("Error connecting to server.");
        tg.MainButton.hideProgress();
    });
}
