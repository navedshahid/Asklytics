/**
 * Visual Canvas-Based Modeling UI - JavaScript
 * 
 * Handles interactive ERD canvas with drag-and-drop entity cards,
 * relationship lines, zoom/pan controls, and model management.
 */

// Global state
let entities = [];
let entityDetails = {}; // Full entity details with columns
let databaseTables = []; // Database tables from connected DB
let tableDetails = {}; // Full table details with columns
let relationships = [];
let entityCards = {}; // Map of entity name to card element
let selectedCard = null;
let viewMode = 'semantic'; // 'semantic' or 'database'
let canvasScale = 1;
let canvasOffset = { x: 0, y: 0 };
let isDragging = false;
let dragStart = { x: 0, y: 0 };
let currentEditingRelation = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    // Check semantic engine health first
    await checkSemanticHealth();
    await loadDatabaseTables();
    await loadEntities();
    await loadRelationships();
    setupCanvas();
    setupModal();
    setupViewModeToggle();
    
    // Handle window resize
    window.addEventListener('resize', () => {
        drawRelationshipLines();
    });
});

/**
 * Check semantic engine health
 */
async function checkSemanticHealth() {
    try {
        const response = await fetch('/semantic/health');
        if (!response.ok) {
            console.warn('Semantic engine health check failed:', response.status);
            return false;
        }
        const health = await response.json();
        if (health.status !== 'healthy') {
            console.warn('Semantic engine not healthy:', health);
            return false;
        }
        return true;
    } catch (error) {
        console.error('Failed to check semantic engine health:', error);
        return false;
    }
}

/**
 * Setup canvas event listeners
 */
function setupCanvas() {
    const canvas = document.getElementById('canvas');
    const container = document.getElementById('canvasContainer');
    
    // Pan with mouse drag
    let isPanning = false;
    let panStart = { x: 0, y: 0 };
    
    container.addEventListener('mousedown', (e) => {
        if (e.target === canvas || e.target === container || e.target.classList.contains('canvas-grid')) {
            isPanning = true;
            panStart = { x: e.clientX - canvasOffset.x, y: e.clientY - canvasOffset.y };
        }
    });
    
    container.addEventListener('mousemove', (e) => {
        if (isPanning) {
            canvasOffset.x = e.clientX - panStart.x;
            canvasOffset.y = e.clientY - panStart.y;
            updateCanvasTransform();
        }
    });
    
    container.addEventListener('mouseup', () => {
        isPanning = false;
    });
    
    container.addEventListener('mouseleave', () => {
        isPanning = false;
    });
    
    // Zoom with mouse wheel
    container.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        zoomAtPoint(e.clientX, e.clientY, delta);
    });
}

/**
 * Update canvas transform
 */
function updateCanvasTransform() {
    const canvas = document.getElementById('canvas');
    canvas.style.transform = `translate(${canvasOffset.x}px, ${canvasOffset.y}px) scale(${canvasScale})`;
    // SVG doesn't need transform as we calculate screen coordinates directly
    drawRelationshipLines();
}

/**
 * Zoom at specific point
 */
function zoomAtPoint(clientX, clientY, delta) {
    const container = document.getElementById('canvasContainer');
    const rect = container.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    
    const newScale = Math.max(0.5, Math.min(2, canvasScale * delta));
    const scaleChange = newScale / canvasScale;
    
    canvasOffset.x = x - (x - canvasOffset.x) * scaleChange;
    canvasOffset.y = y - (y - canvasOffset.y) * scaleChange;
    canvasScale = newScale;
    
    updateCanvasTransform();
}

/**
 * Load database tables from connected database
 */
async function loadDatabaseTables() {
    try {
        const response = await fetch('/semantic/db/tables?selected_only=1');
        
        if (!response.ok) {
            console.warn('Failed to load database tables:', response.status);
            return;
        }
        
        const data = await response.json();
        
        if (data.error) {
            console.warn('Error loading database tables:', data.error);
            return;
        }
        
        if (data.tables && Array.isArray(data.tables)) {
            databaseTables = data.tables;
            // Store table details
            databaseTables.forEach(table => {
                tableDetails[table.name] = table;
            });
            
            // Update UI if in database view mode
            if (viewMode === 'database') {
                renderModelList();
                renderEntityCards();
            }
        }
    } catch (error) {
        console.error('Failed to load database tables:', error);
    }
}

/**
 * Load entities from semantic catalog
 */
async function loadEntities() {
    try {
        const response = await fetch('/semantic/catalog?type=entity');
        
        // Check if response is ok
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: `HTTP ${response.status}: ${response.statusText}` }));
            throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        // Check for error in response
        if (data.error) {
            throw new Error(data.error);
        }
        
        // Check if entities exist in response
        if (data.entities && Array.isArray(data.entities)) {
            entities = data.entities;
            document.getElementById('modelCount').textContent = entities.length;
            
            // Load full details for each entity
            for (const entity of entities) {
                try {
                    const detailResponse = await fetch(`/semantic/entity/${entity.name}`);
                    if (detailResponse.ok) {
                        const detailData = await detailResponse.json();
                        if (detailData.error) {
                            console.warn(`Error loading details for ${entity.name}:`, detailData.error);
                        } else {
                            entityDetails[entity.name] = detailData;
                        }
                    } else {
                        console.warn(`Failed to load details for ${entity.name}: HTTP ${detailResponse.status}`);
                    }
                } catch (error) {
                    console.error(`Failed to load details for ${entity.name}:`, error);
                }
            }
            
            if (entities.length === 0) {
                showError('No entities found. Create entity definitions in semantic/mdl/entities/');
            } else {
                renderModelList();
                renderEntityCards();
            }
        } else {
            showError('No entities found. The semantic engine may not be initialized.');
        }
    } catch (error) {
        console.error('Failed to load entities:', error);
        const errorMessage = error.message || 'Failed to load entities. Check if the semantic engine is running.';
        showError(errorMessage);
    }
}

/**
 * Load relationships from semantic catalog
 */
async function loadRelationships() {
    try {
        const response = await fetch('/semantic/relations');
        
        if (!response.ok) {
            console.warn(`Failed to load relationships: HTTP ${response.status}`);
            return;
        }
        
        const data = await response.json();
        
        if (data.error) {
            console.warn('Error loading relationships:', data.error);
            return;
        }
        
        if (data.relations && Array.isArray(data.relations)) {
            relationships = data.relations;
            drawRelationshipLines();
        }
    } catch (error) {
        console.error('Failed to load relationships:', error);
    }
}

async function confirmDeleteEntity(entityName) {
    if (!entityName || !confirm(`Delete entity "${entityName}"? This removes the YAML definition.`)) {
        return;
    }
    try {
        const response = await fetch(`/semantic/entities/${encodeURIComponent(entityName)}`, {
            method: 'DELETE'
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            alert(result.error || 'Failed to delete entity.');
            return;
        }
        delete entityDetails[entityName];
        await loadEntities();
        await loadRelationships();
        renderModelList();
        renderEntityCards();
    } catch (error) {
        console.error('Failed to delete entity:', error);
        alert('Failed to delete entity. Check console for details.');
    }
}

async function confirmDeleteRelationship(name) {
    if (!name || !confirm(`Delete relationship "${name}"?`)) {
        return;
    }
    try {
        const response = await fetch(`/semantic/relations/${encodeURIComponent(name)}`, {
            method: 'DELETE'
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            alert(result.error || 'Failed to delete relationship.');
            return;
        }
        await loadRelationships();
        renderEntityCards();
    } catch (error) {
        console.error('Failed to delete relationship:', error);
        alert('Failed to delete relationship. Check console for details.');
    }
}

/**
 * Setup view mode toggle
 */
function setupViewModeToggle() {
    // Add view mode toggle to sidebar header
    const sidebarHeader = document.querySelector('.sidebar-header');
    if (sidebarHeader && !document.getElementById('viewModeToggle')) {
        const toggleDiv = document.createElement('div');
        toggleDiv.id = 'viewModeToggle';
        toggleDiv.style.cssText = 'display: flex; gap: 0.5rem; margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid #e2e8f0;';
        
        const semanticBtn = document.createElement('button');
        semanticBtn.textContent = 'Semantic Models';
        semanticBtn.className = 'view-mode-btn';
        semanticBtn.style.cssText = 'flex: 1; padding: 0.5rem; background: #667eea; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem;';
        semanticBtn.onclick = () => switchViewMode('semantic');
        
        const dbBtn = document.createElement('button');
        dbBtn.textContent = 'Database Tables';
        dbBtn.className = 'view-mode-btn';
        dbBtn.style.cssText = 'flex: 1; padding: 0.5rem; background: #edf2f7; color: #4a5568; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem;';
        dbBtn.onclick = () => switchViewMode('database');
        
        toggleDiv.appendChild(semanticBtn);
        toggleDiv.appendChild(dbBtn);
        sidebarHeader.appendChild(toggleDiv);
        
        updateViewModeButtons();
    }
}

/**
 * Switch view mode
 */
function switchViewMode(mode) {
    viewMode = mode;
    updateViewModeButtons();
    renderModelList();
    renderEntityCards();
    drawRelationshipLines();
}

/**
 * Update view mode buttons
 */
function updateViewModeButtons() {
    const buttons = document.querySelectorAll('.view-mode-btn');
    buttons.forEach(btn => {
        if (btn.textContent === 'Semantic Models') {
            btn.style.background = viewMode === 'semantic' ? '#667eea' : '#edf2f7';
            btn.style.color = viewMode === 'semantic' ? 'white' : '#4a5568';
        } else {
            btn.style.background = viewMode === 'database' ? '#667eea' : '#edf2f7';
            btn.style.color = viewMode === 'database' ? 'white' : '#4a5568';
        }
    });
    
    // Update model count
    const count = viewMode === 'semantic' ? entities.length : databaseTables.length;
    document.getElementById('modelCount').textContent = count;
}

/**
 * Render model list in sidebar
 */
function renderModelList() {
    const modelList = document.getElementById('modelList');
    modelList.innerHTML = '';
    
    const items = viewMode === 'semantic' ? entities : databaseTables;
    const count = items.length;
    
    if (!items || count === 0) {
        const message = viewMode === 'semantic' 
            ? 'No semantic models found. Create entity definitions in semantic/mdl/entities/'
            : 'No database tables found. Connect to a database in Settings.';
        modelList.innerHTML = `<li style="padding: 1rem; text-align: center; color: #718096; font-size: 0.9rem;">${message}</li>`;
        return;
    }
    
    items.forEach(item => {
        const li = document.createElement('li');
        li.className = 'model-item';
        const icon = viewMode === 'semantic' ? '📦' : '🗄️';
        const name = item.name || item.full_name || 'Unknown';
        li.innerHTML = `
            <span class="model-item-icon">${icon}</span>
            <span>${name}</span>
        `;
        li.onclick = () => {
            // Highlight model
            document.querySelectorAll('.model-item').forEach(modelItem => {
                modelItem.classList.remove('active');
            });
            li.classList.add('active');
            
            // Select and focus on entity card
            const card = entityCards[name];
            if (card) {
                selectCard(card);
                centerOnCard(card);
            }
        };
        modelList.appendChild(li);
    });
}

/**
 * Render entity cards on canvas
 */
function renderEntityCards() {
    const canvas = document.getElementById('canvas');
    canvas.innerHTML = '';
    entityCards = {};
    
    const items = viewMode === 'semantic' ? entities : databaseTables;
    
    if (!items || items.length === 0) {
        return;
    }
    
    // Calculate grid layout
    const cols = Math.ceil(Math.sqrt(items.length));
    const cardWidth = 300;
    const cardHeight = 200;
    const spacing = 50;
    
    items.forEach((item, index) => {
        let detail;
        let itemName;
        
        if (viewMode === 'semantic') {
            detail = entityDetails[item.name] || {};
            itemName = item.name;
        } else {
            // Database table
            detail = tableDetails[item.name] || item;
            itemName = item.name;
        }
        
        const col = index % cols;
        const row = Math.floor(index / cols);
        
        const x = col * (cardWidth + spacing) + 100;
        const y = row * (cardHeight + spacing) + 100;
        
        const card = createEntityCard(item, detail, x, y, itemName);
        canvas.appendChild(card);
        entityCards[itemName] = card;
    });
    
    drawRelationshipLines();
}

/**
 * Create entity card element
 */
function createEntityCard(entity, detail, x, y, itemName) {
    const card = document.createElement('div');
    card.className = 'entity-card';
    card.style.left = `${x}px`;
    card.style.top = `${y}px`;
    card.dataset.entityName = itemName;
    
    // Header
    const header = document.createElement('div');
    header.className = 'entity-card-header';
    const titleWrap = document.createElement('div');
    titleWrap.className = 'entity-card-title';
    const displayName = viewMode === 'database' && entity.schema 
        ? `${entity.schema}.${itemName}` 
        : itemName;
    titleWrap.textContent = displayName;
    
    if (viewMode === 'database') {
        const badge = document.createElement('span');
        badge.textContent = 'DB';
        badge.style.cssText = 'padding: 0.15rem 0.4rem; background: rgba(255,255,255,0.2); border-radius: 4px; font-size: 0.7rem;';
        titleWrap.appendChild(badge);
    }
    header.appendChild(titleWrap);
    
    const headerActions = document.createElement('div');
    headerActions.className = 'entity-actions';
    if (viewMode === 'semantic') {
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'entity-action-btn';
        deleteBtn.title = 'Delete entity';
        deleteBtn.innerHTML = '&times;';
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            confirmDeleteEntity(itemName);
        };
        headerActions.appendChild(deleteBtn);
    }
    if (headerActions.children.length > 0) {
        header.appendChild(headerActions);
    }
    
    card.appendChild(header);
    
    // Body
    const body = document.createElement('div');
    body.className = 'entity-card-body';
    
    // Columns section
    const columns = detail.columns || [];
    if (columns.length > 0) {
        const columnsSection = document.createElement('div');
        columnsSection.className = 'entity-section';
        
        const columnsTitle = document.createElement('div');
        columnsTitle.className = 'entity-section-title';
        columnsTitle.textContent = 'Columns';
        
        // Add create entity button for database tables
        if (viewMode === 'database') {
            const createBtn = document.createElement('button');
            createBtn.textContent = 'Create Entity';
            createBtn.style.cssText = 'margin-left: auto; padding: 0.25rem 0.5rem; background: #48bb78; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.7rem;';
            createBtn.onclick = (e) => {
                e.stopPropagation();
                createEntityFromTable(itemName, detail);
            };
            columnsTitle.style.display = 'flex';
            columnsTitle.appendChild(createBtn);
        }
        
        columnsSection.appendChild(columnsTitle);
        
        const columnsList = document.createElement('ul');
        columnsList.className = 'entity-column-list';
        
        columns.slice(0, 8).forEach(column => {
            const columnItem = document.createElement('li');
            columnItem.className = 'entity-column-item';
            
            // Column icon based on type
            const icon = getColumnIcon(column.dtype);
            const isPrimary = column.primary === true;
            const isPii = column.pii === true;
            
            if (isPrimary) columnItem.classList.add('column-primary');
            if (isPii) columnItem.classList.add('column-pii');
            
            columnItem.innerHTML = `
                <span class="column-icon">${icon}</span>
                <span class="column-name">${column.name}</span>
                <span class="column-type">${column.dtype || ''}</span>
            `;
            columnsList.appendChild(columnItem);
        });
        
        if (columns.length > 8) {
            const moreItem = document.createElement('li');
            moreItem.className = 'entity-column-item';
            moreItem.style.fontSize = '0.75rem';
            moreItem.style.color = '#a0aec0';
            moreItem.textContent = `+${columns.length - 8} more`;
            columnsList.appendChild(moreItem);
        }
        
        columnsSection.appendChild(columnsList);
        body.appendChild(columnsSection);
    }
    
    // Relationships section
    const entityRelations = relationships.filter(rel => {
        const fromModel = rel.from.split('.')[0];
        const toModel = rel.to.split('.')[0];
        return fromModel === entity.name || toModel === entity.name;
    });
    
    if (entityRelations.length > 0) {
        const relSection = document.createElement('div');
        relSection.className = 'entity-section relationship-section';
        
        const relTitle = document.createElement('div');
        relTitle.className = 'entity-section-title';
        relTitle.textContent = 'Relationships';
        relSection.appendChild(relTitle);
        
        entityRelations.slice(0, 3).forEach(rel => {
            const relItem = document.createElement('div');
            relItem.className = 'relationship-item';
            const fromModel = rel.from.split('.')[0];
            const toModel = rel.to.split('.')[0];
            const targetModel = fromModel === entity.name ? toModel : fromModel;
            const relText = document.createElement('span');
            relText.textContent = `→ ${targetModel}`;
            relItem.appendChild(relText);
            
            const relActions = document.createElement('div');
            relActions.className = 'entity-actions';
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'relationship-delete-btn';
            deleteBtn.title = 'Delete relationship';
            deleteBtn.textContent = '×';
            deleteBtn.onclick = (e) => {
                e.stopPropagation();
                confirmDeleteRelationship(rel.name);
            };
            relActions.appendChild(deleteBtn);
            relItem.appendChild(relActions);
            
            relItem.onclick = () => {
                const targetCard = entityCards[targetModel];
                if (targetCard) {
                    selectCard(targetCard);
                    centerOnCard(targetCard);
                }
            };
            relSection.appendChild(relItem);
        });
        
        if (entityRelations.length > 3) {
            const moreRel = document.createElement('div');
            moreRel.className = 'relationship-item';
            moreRel.style.fontSize = '0.75rem';
            moreRel.style.color = '#a0aec0';
            moreRel.textContent = `+${entityRelations.length - 3} more`;
            relSection.appendChild(moreRel);
        }
        
        body.appendChild(relSection);
    }
    
    card.appendChild(body);
    
    // Make card draggable
    makeCardDraggable(card);
    
    // Card click handler
    card.addEventListener('click', (e) => {
        if (e.target === card || card.contains(e.target)) {
            selectCard(card);
        }
    });
    
    return card;
}

/**
 * Get column icon based on data type
 */
function getColumnIcon(dtype) {
    if (!dtype) return '□';
    const type = dtype.toLowerCase();
    if (type.includes('int') || type.includes('number')) return '🔢';
    if (type.includes('string') || type.includes('text') || type.includes('varchar')) return '📝';
    if (type.includes('date') || type.includes('time') || type.includes('timestamp')) return '📅';
    if (type.includes('bool')) return '☑';
    if (type.includes('decimal') || type.includes('float') || type.includes('double')) return '💰';
    return '□';
}

/**
 * Make card draggable
 */
function makeCardDraggable(card) {
    let isDraggingCard = false;
    let dragOffset = { x: 0, y: 0 };
    
    card.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('entity-card-header') || e.target.closest('.entity-card-header')) {
            isDraggingCard = true;
            const rect = card.getBoundingClientRect();
            const canvasRect = document.getElementById('canvasContainer').getBoundingClientRect();
            dragOffset.x = (e.clientX - rect.left - canvasOffset.x) / canvasScale - parseFloat(card.style.left);
            dragOffset.y = (e.clientY - rect.top - canvasOffset.y) / canvasScale - parseFloat(card.style.top);
            card.style.cursor = 'grabbing';
            e.stopPropagation();
        }
    });
    
    document.addEventListener('mousemove', (e) => {
        if (isDraggingCard) {
            const container = document.getElementById('canvasContainer');
            const containerRect = container.getBoundingClientRect();
            const x = (e.clientX - containerRect.left - canvasOffset.x) / canvasScale - dragOffset.x;
            const y = (e.clientY - containerRect.top - canvasOffset.y) / canvasScale - dragOffset.y;
            card.style.left = `${Math.max(0, x)}px`;
            card.style.top = `${Math.max(0, y)}px`;
            drawRelationshipLines();
        }
    });
    
    document.addEventListener('mouseup', () => {
        if (isDraggingCard) {
            isDraggingCard = false;
            card.style.cursor = 'move';
        }
    });
}

/**
 * Select card
 */
function selectCard(card) {
    if (selectedCard) {
        selectedCard.classList.remove('selected');
    }
    selectedCard = card;
    card.classList.add('selected');
    
    // Update sidebar
    document.querySelectorAll('.model-item').forEach(item => {
        item.classList.remove('active');
    });
    const entityName = card.dataset.entityName;
    const modelItem = Array.from(document.querySelectorAll('.model-item')).find(item => 
        item.textContent.trim() === entityName
    );
    if (modelItem) {
        modelItem.classList.add('active');
    }
}

/**
 * Center canvas on card
 */
function centerOnCard(card) {
    const container = document.getElementById('canvasContainer');
    const containerRect = container.getBoundingClientRect();
    
    const cardX = parseFloat(card.style.left) || 0;
    const cardY = parseFloat(card.style.top) || 0;
    const cardWidth = card.offsetWidth || 280;
    const cardHeight = card.offsetHeight || 200;
    
    // Center the card in the viewport
    const cardCenterX = cardX + cardWidth / 2;
    const cardCenterY = cardY + cardHeight / 2;
    
    canvasOffset.x = containerRect.width / 2 - cardCenterX * canvasScale;
    canvasOffset.y = containerRect.height / 2 - cardCenterY * canvasScale;
    
    updateCanvasTransform();
}

/**
 * Draw relationship lines on SVG
 */
function drawRelationshipLines() {
    const svg = document.getElementById('relationshipSvg');
    const container = document.getElementById('canvasContainer');
    const containerRect = container.getBoundingClientRect();
    
    // Clear existing lines
    svg.innerHTML = '';
    svg.setAttribute('width', containerRect.width);
    svg.setAttribute('height', containerRect.height);
    
    relationships.forEach(rel => {
        const fromModel = rel.from.split('.')[0];
        const toModel = rel.to.split('.')[0];
        
        const fromCard = entityCards[fromModel];
        const toCard = entityCards[toModel];
        
        if (!fromCard || !toCard) return;
        
        // Get card positions in canvas coordinates
        const fromX = parseFloat(fromCard.style.left) || 0;
        const fromY = parseFloat(fromCard.style.top) || 0;
        const toX = parseFloat(toCard.style.left) || 0;
        const toY = parseFloat(toCard.style.top) || 0;
        
        // Calculate connection points (center-bottom of from card, center-top of to card)
        const fromCardWidth = fromCard.offsetWidth || 280;
        const fromCardHeight = fromCard.offsetHeight || 200;
        const toCardWidth = toCard.offsetWidth || 280;
        const toCardHeight = toCard.offsetHeight || 200;
        
        const fromPointX = fromX + fromCardWidth / 2;
        const fromPointY = fromY + fromCardHeight;
        const toPointX = toX + toCardWidth / 2;
        const toPointY = toY;
        
        // Transform to screen coordinates
        const screenFromX = fromPointX * canvasScale + canvasOffset.x;
        const screenFromY = fromPointY * canvasScale + canvasOffset.y;
        const screenToX = toPointX * canvasScale + canvasOffset.x;
        const screenToY = toPointY * canvasScale + canvasOffset.y;
        
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', screenFromX);
        line.setAttribute('y1', screenFromY);
        line.setAttribute('x2', screenToX);
        line.setAttribute('y2', screenToY);
        line.setAttribute('class', 'relationship-line');
        line.setAttribute('stroke-dasharray', rel.type === 'MANY_TO_MANY' ? '5,5' : '');
        line.setAttribute('stroke-width', '2');
        
        svg.appendChild(line);
    });
}

/**
 * Zoom in
 */
function zoomIn() {
    const container = document.getElementById('canvasContainer');
    const rect = container.getBoundingClientRect();
    zoomAtPoint(rect.width / 2, rect.height / 2, 1.2);
}

/**
 * Zoom out
 */
function zoomOut() {
    const container = document.getElementById('canvasContainer');
    const rect = container.getBoundingClientRect();
    zoomAtPoint(rect.width / 2, rect.height / 2, 0.8);
}

/**
 * Fit to screen
 */
function fitToScreen() {
    if (entities.length === 0) return;
    
    const container = document.getElementById('canvasContainer');
    const containerRect = container.getBoundingClientRect();
    
    // Calculate bounds of all cards
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    
    Object.values(entityCards).forEach(card => {
        const x = parseFloat(card.style.left);
        const y = parseFloat(card.style.top);
        const w = card.offsetWidth;
        const h = card.offsetHeight;
        
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x + w);
        maxY = Math.max(maxY, y + h);
    });
    
    const contentWidth = maxX - minX;
    const contentHeight = maxY - minY;
    const padding = 100;
    
    const scaleX = (containerRect.width - padding * 2) / contentWidth;
    const scaleY = (containerRect.height - padding * 2) / contentHeight;
    canvasScale = Math.min(scaleX, scaleY, 1);
    
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    
    canvasOffset.x = containerRect.width / 2 - centerX * canvasScale;
    canvasOffset.y = containerRect.height / 2 - centerY * canvasScale;
    
    updateCanvasTransform();
}

/**
 * Refresh canvas
 */
async function refreshCanvas() {
    await loadEntities();
    await loadRelationships();
}

/**
 * Refresh models
 */
async function refreshModels() {
    if (viewMode === 'database') {
        await loadDatabaseTables();
    } else {
        await loadEntities();
    }
    await loadRelationships();
}

/**
 * Create entity from database table
 */
async function createEntityFromTable(tableName, tableDetail) {
    if (!confirm(`Create semantic entity from database table "${tableName}"?`)) {
        return;
    }
    
    try {
        // Find primary key for grain
        const pkColumn = tableDetail.columns.find(col => col.primary === true);
        const grain = pkColumn ? pkColumn.name : tableDetail.columns[0]?.name || 'id';
        
        // Build entity definition
        const entityDef = {
            name: tableName.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
            grain: grain,
            description: `Entity mapped from database table ${tableDetail.full_name || tableName}`,
            reference: {
                table: tableDetail.full_name || tableName
            },
            columns: tableDetail.columns.map(col => ({
                name: col.name,
                dtype: col.dtype,
                primary: col.primary || false,
                description: col.description || `${col.dtype} column`
            })),
            tags: ['database_mapped'],
            properties: {}
        };
        
        // Send to backend
        const response = await fetch('/semantic/entities', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Role': 'admin'
            },
            body: JSON.stringify(entityDef)
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            alert(`Entity "${entityDef.name}" created successfully!`);
            // Reindex and reload
            await reindexSemantic();
            await loadEntities();
            // Switch to semantic view to see the new entity
            switchViewMode('semantic');
        } else {
            alert(`Failed to create entity: ${result.error || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Failed to create entity from table:', error);
        alert('Failed to create entity. Check console for details.');
    }
}

/**
 * Setup modal
 */
function setupModal() {
    // Close modal on backdrop click
    document.getElementById('relationshipModal').addEventListener('click', (e) => {
        if (e.target.id === 'relationshipModal') {
            closeRelationshipModal();
        }
    });
}

/**
 * Open create relationship modal
 */
function openCreateRelationshipModal() {
    if (!entities || entities.length === 0) {
        alert('No entities available. Please create entities first or wait for them to load.');
        return;
    }
    
    currentEditingRelation = null;
    document.getElementById('modalTitle').textContent = 'Create Relationship';
    document.getElementById('relationshipForm').reset();
    populateModelSelects();
    document.getElementById('relationshipModal').classList.add('active');
}

/**
 * Close relationship modal
 */
function closeRelationshipModal() {
    document.getElementById('relationshipModal').classList.remove('active');
    currentEditingRelation = null;
}

/**
 * Populate model select dropdowns
 */
function populateModelSelects() {
    const fromSelect = document.getElementById('fromModel');
    const toSelect = document.getElementById('toModel');
    
    fromSelect.innerHTML = '<option value="">Select model...</option>';
    toSelect.innerHTML = '<option value="">Select model...</option>';
    
    if (!entities || entities.length === 0) {
        const noModelsOption = document.createElement('option');
        noModelsOption.value = '';
        noModelsOption.textContent = 'No models available';
        noModelsOption.disabled = true;
        fromSelect.appendChild(noModelsOption);
        toSelect.appendChild(noModelsOption.cloneNode(true));
        return;
    }
    
    entities.forEach(entity => {
        const option1 = document.createElement('option');
        option1.value = entity.name;
        option1.textContent = entity.name;
        fromSelect.appendChild(option1);
        
        const option2 = document.createElement('option');
        option2.value = entity.name;
        option2.textContent = entity.name;
        toSelect.appendChild(option2);
    });
}

/**
 * Update from columns dropdown
 */
async function updateFromColumns() {
    const modelName = document.getElementById('fromModel').value;
    const columnSelect = document.getElementById('fromColumn');
    
    columnSelect.innerHTML = '<option value="">Select column...</option>';
    
    if (!modelName) return;
    
    const detail = entityDetails[modelName];
    if (detail && detail.columns) {
        detail.columns.forEach(column => {
            const option = document.createElement('option');
            option.value = column.name;
            option.textContent = `${column.name} (${column.dtype || ''})`;
            columnSelect.appendChild(option);
        });
    }
}

/**
 * Update to columns dropdown
 */
async function updateToColumns() {
    const modelName = document.getElementById('toModel').value;
    const columnSelect = document.getElementById('toColumn');
    
    columnSelect.innerHTML = '<option value="">Select column...</option>';
    
    if (!modelName) return;
    
    const detail = entityDetails[modelName];
    if (detail && detail.columns) {
        detail.columns.forEach(column => {
            const option = document.createElement('option');
            option.value = column.name;
            option.textContent = `${column.name} (${column.dtype || ''})`;
            columnSelect.appendChild(option);
        });
    }
}

/**
 * Handle relationship form submission
 */
document.getElementById('relationshipForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const name = document.getElementById('relationshipName').value;
    const fromModel = document.getElementById('fromModel').value;
    const fromColumn = document.getElementById('fromColumn').value;
    const toModel = document.getElementById('toModel').value;
    const toColumn = document.getElementById('toColumn').value;
    const type = document.getElementById('relationType').value;
    const description = document.getElementById('relationshipDescription').value;
    
    const relationshipData = {
        name: name,
        from: {
            model: fromModel,
            column: fromColumn
        },
        to: {
            model: toModel,
            column: toColumn
        },
        type: type,
        condition: `${fromModel}.${fromColumn} = ${toModel}.${toColumn}`,
        description: description,
        tags: ['user_defined']
    };
    
    try {
        const response = await fetch('/semantic/relations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Role': 'admin'
            },
            body: JSON.stringify(relationshipData)
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            closeRelationshipModal();
            await loadRelationships();
            await reindexSemantic();
            // Re-render cards to show new relationships
            renderEntityCards();
        } else {
            alert(`Failed to save relationship: ${result.error || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Failed to save relationship:', error);
        alert('Failed to save relationship. Check console for details.');
    }
});

/**
 * Reindex semantic layer
 */
async function reindexSemantic() {
    try {
        await fetch('/semantic/reindex', {
            method: 'POST',
            headers: {
                'X-Role': 'admin'
            }
        });
    } catch (error) {
        console.error('Failed to reindex:', error);
    }
}

/**
 * Show error
 */
function showError(message) {
    const modelList = document.getElementById('modelList');
    modelList.innerHTML = `
        <li style="padding: 2rem; text-align: center;">
            <div style="color: #fc8181; font-weight: 500; margin-bottom: 0.5rem;">⚠️ Error</div>
            <div style="color: #718096; font-size: 0.9rem;">${message}</div>
            <button 
                onclick="loadEntities()" 
                style="margin-top: 1rem; padding: 0.5rem 1rem; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9rem;"
            >
                Retry
            </button>
        </li>
    `;
    
    // Also show in canvas area
    const canvas = document.getElementById('canvas');
    if (canvas) {
        canvas.innerHTML = `
            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; padding: 2rem; background: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); max-width: 400px;">
                <div style="font-size: 3rem; margin-bottom: 1rem;">⚠️</div>
                <div style="color: #fc8181; font-weight: 500; margin-bottom: 0.5rem; font-size: 1.1rem;">Failed to Load Entities</div>
                <div style="color: #718096; font-size: 0.9rem; margin-bottom: 1rem;">${message}</div>
                <button 
                    onclick="loadEntities()" 
                    style="padding: 0.75rem 1.5rem; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9rem; font-weight: 500;"
                >
                    Retry Loading
                </button>
            </div>
        `;
    }
}
