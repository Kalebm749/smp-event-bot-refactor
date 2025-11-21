// Winners Page JavaScript
// Handles displaying event winners and their reward status

let allWinners = [];
let currentFilter = 'all';

// Load winners from API
async function loadWinners() {
    try {
        const response = await fetch('/api/winners');
        const data = await response.json();
        
        if (data.error) {
            showError('Failed to load winners: ' + data.error);
            return;
        }
        
        allWinners = data;
        updateStatistics();
        displayWinners();
    } catch (error) {
        showError('Error loading winners: ' + error.message);
    }
}

// Update statistics cards
function updateStatistics() {
    const stats = {
        total: allWinners.length,
        rewarded: 0,
        notRewarded: 0
    };

    allWinners.forEach(winner => {
        if (winner.was_online) {
            stats.rewarded++;
        } else {
            stats.notRewarded++;
        }
    });

    document.getElementById('stat-total-winners').textContent = stats.total;
    document.getElementById('stat-rewarded').textContent = stats.rewarded;
    document.getElementById('stat-not-rewarded').textContent = stats.notRewarded;
}

// Display winners in table
function displayWinners() {
    const tbody = document.getElementById('winners-tbody');
    tbody.innerHTML = '';

    // Filter winners based on current filter
    let filteredWinners = allWinners;
    if (currentFilter === 'online') {
        filteredWinners = allWinners.filter(w => w.was_online);
    } else if (currentFilter === 'offline') {
        filteredWinners = allWinners.filter(w => !w.was_online);
    }

    if (filteredWinners.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #888;">No winners found</td></tr>';
        return;
    }

    filteredWinners.forEach(winner => {
        const tr = document.createElement('tr');
        tr.className = winner.was_online ? 'winner-row rewarded' : 'winner-row not-rewarded';

        // Format date
        const rewardedAt = winner.rewarded_at ? new Date(winner.rewarded_at.replace('Z', '+00:00')).toLocaleString() : '-';
        
        // Status badge
        const statusBadge = winner.was_online 
            ? '<span class="status-badge online">✅ Rewarded</span>'
            : '<span class="status-badge offline">❌ Offline</span>';

        // Build reward command with copy button
        let rewardCommandHtml = '<span style="color: #888;">-</span>';
        if (winner.reward_cmd && winner.player_name) {
            const fullCommand = `/give ${winner.player_name} ${winner.reward_cmd}`;
            const commandId = `cmd-${winner.id}`;
            rewardCommandHtml = `
                <div style="display: flex; align-items: center;">
                    <code class="reward-command" id="${commandId}">${fullCommand}</code>
                    <button class="copy-btn" onclick="copyCommand('${commandId}', this)" title="Copy to clipboard">📋</button>
                </div>
            `;
        }

        tr.innerHTML = `
            <td><span class="event-name">${winner.event_name || winner.unique_event_name}</span></td>
            <td><span class="player-name">${winner.player_name}</span></td>
            <td><span class="score">${winner.final_score !== null ? winner.final_score : '-'}</span></td>
            <td>${statusBadge}</td>
            <td>${rewardCommandHtml}</td>
            <td>${rewardedAt}</td>
        `;

        tbody.appendChild(tr);
    });
}

// Copy command to clipboard
function copyCommand(elementId, button) {
    const element = document.getElementById(elementId);
    const text = element.textContent;
    
    navigator.clipboard.writeText(text).then(() => {
        // Visual feedback
        const originalText = button.textContent;
        button.textContent = '✅';
        button.classList.add('copied');
        
        setTimeout(() => {
            button.textContent = originalText;
            button.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy command');
    });
}

// Filter winners
function filterWinners(filter) {
    currentFilter = filter;
    
    // Update active button
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    displayWinners();
}

// Refresh winners data
function refreshWinners() {
    loadWinners();
}

// Show error message
function showError(message) {
    const tbody = document.getElementById('winners-tbody');
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #f44336;">${message}</td></tr>`;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadWinners();
    
    // Auto-refresh every 60 seconds
    setInterval(loadWinners, 60000);
});