/**
 * Semantic Modeling UI - JavaScript
 * 
 * Handles ERD visualization and relationship management.
 */

let entities = [];
let relationships = [];
let currentEditingRelation = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadEntities();
    await loadRelationships();
});

/**
 * Load entities from semantic catalog
 */
async function loadEntities() {
    try {
        const response = await fetch('/semantic/catalog?type=entity');
        const data = await response.json();
        
        if (data.entities) {
            entities = data.entities;
            renderERD();
            populateModelSelects();
        } else {
            showEmptyState('erd-container', 'No entities found', 'Create entity definitions in semantic/mdl/entities/');
        }
    } catch (error) {
        console.error('Failed to load entities:', error);
        showError('erd-container', 'Failed to load entities');
    }
}

/**
 * Load relationships from semantic catalog
 */
async function loadRelationships() {
    try {
        const response = await fetch('/semantic/relations');
        const data = await response.json();
        
        if (data.relations) {
            relationships = data.relations;
            renderRelationships();
        } else {
            showEmptyState('relationships-container', 'No relationships defined', 'Click "+ Relationship" to create one');
        }
    } catch (error) {
        console.error('Failed to load relationships:', error);
        showError('relationships-container', 'Failed to load relationships');
    }
}

/**
 * Render ERD with entity cards
 */
function renderERD() {
    const container = document.getElementById('erd-container');
    
    if (entities.length === 0) {
        showEmptyState(container, 'No entities found', 'Add entity YAML files to semantic/mdl/entities/');
        return;
    }
    
    container.innerHTML = '';
    
    entities.forEach(entity => {
        const card = document.createElement('div');
        card.className = 'entity-card';
        
        // Entity header
        const header = document.createElement('div');
        header.className = 'entity-header';
        header.textContent = entity.name;
        card.appendChild(header);
        
        // Columns (fetch from catalog metadata if available)
        if (entity.columns && entity.columns > 0) {
            // If we have column count but not details, show placeholder
            const columnDiv = document.createElement('div');
            columnDiv.className = 'entity-column';
            columnDiv.innerHTML = `<span class="col-name">${entity.columns} columns</span>`;
            card.appendChild(columnDiv);
        }
        
        // Tags
        if (entity.tags && entity.tags.length > 0) {
            const tagsDiv = document.createElement('div');
            tagsDiv.style.marginTop = '0.75rem';
            tagsDiv.style.paddingTop = '0.75rem';
            tagsDiv.style.borderTop = '1px solid #e2e8f0';
            entity.tags.forEach(tag => {
                const badge = document.createElement('span');
                badge.style.cssText = 'display: inline-block; padding: 0.2rem 0.5rem; background: #edf2f7; color: #4a5568; border-radius: 4px; font-size: 0.75rem; margin-right: 0.5rem;';
                badge.textContent = tag;
                tagsDiv.appendChild(badge);
            });
            card.appendChild(tagsDiv);
        }
        
        container.appendChild(card);
    });
}

/**
 * Render relationships list
 */
function renderRelationships() {
    const container = document.getElementById('relationships-container');
    
    if (relationships.length === 0) {
        showEmptyState('relationships-container', 'No relationships defined', 'Click "+ Relationship" to create one');
        return;
    }
    
    container.innerHTML = '';
    
    relationships.forEach(rel => {
        const card = document.createElement('div');
        card.className = 'relationship-card';
        
        // Header with name and menu
        const header = document.createElement('div');
        header.className = 'relationship-header';
        
        const nameSpan = document.createElement('span');
        nameSpan.className = 'relationship-name';
        nameSpan.textContent = rel.name;
        
        const menuBtn = document.createElement('button');
        menuBtn.className = 'menu-btn';
        menuBtn.innerHTML = '⋮';
        menuBtn.onclick = () => showRelationshipMenu(rel, menuBtn);
        
        header.appendChild(nameSpan);
        header.appendChild(menuBtn);
        card.appendChild(header);
        
        // Type badge
        const typeBadge = document.createElement('div');
        typeBadge.className = 'relationship-type';
        typeBadge.textContent = rel.type;
        card.appendChild(typeBadge);
        
        // Details
        const details = document.createElement('div');
        details.className = 'relationship-details';
        details.innerHTML = `
            <strong>${rel.from}</strong>
            <span class="relationship-arrow">→</span>
            <strong>${rel.to}</strong>
        `;
        card.appendChild(details);
        
        // Description
        if (rel.description) {
            const desc = document.createElement('div');
            desc.style.marginTop = '0.5rem';
            desc.style.fontSize = '0.85rem';
            desc.style.color = '#718096';
            desc.textContent = rel.description;
            card.appendChild(desc);
        }
        
        container.appendChild(card);
    });
}

/**
 * Show relationship context menu
 */
function showRelationshipMenu(rel, button) {
    // Simple implementation - in production, use a proper dropdown
    const action = confirm(`Edit or Delete relationship "${rel.name}"?\n\nOK = Edit, Cancel = Delete`);
    
    if (action) {
        // Edit
        editRelationship(rel);
    } else {
        // Delete
        deleteRelationship(rel);
    }
}

/**
 * Open create relationship modal
 */
function openCreateRelationshipModal() {
    currentEditingRelation = null;
    document.getElementById('modalTitle').textContent = 'Create Relationship';
    document.getElementById('relationshipForm').reset();
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
 * Edit existing relationship
 */
function editRelationship(rel) {
    currentEditingRelation = rel;
    document.getElementById('modalTitle').textContent = 'Edit Relationship';
    
    // Parse from/to
    const fromParts = rel.from.split('.');
    const toParts = rel.to.split('.');
    
    // Populate form
    document.getElementById('relationshipName').value = rel.name;
    document.getElementById('fromModel').value = fromParts[0];
    updateFromColumns();
    document.getElementById('fromColumn').value = fromParts[1];
    document.getElementById('toModel').value = toParts[0];
    updateToColumns();
    document.getElementById('toColumn').value = toParts[1];
    document.getElementById('relationType').value = rel.type;
    document.getElementById('relationshipDescription').value = rel.description || '';
    
    document.getElementById('relationshipModal').classList.add('active');
}

/**
 * Delete relationship
 */
async function deleteRelationship(rel) {
    if (!confirm(`Are you sure you want to delete relationship "${rel.name}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/semantic/relations/${rel.name}`, {
            method: 'DELETE',
            headers: {
                'X-Role': 'admin'  // Set role header
            }
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            alert('Relationship deleted successfully!');
            await loadRelationships();
            await reindexSemantic();
        } else {
            alert(`Failed to delete relationship: ${result.error}`);
        }
    } catch (error) {
        console.error('Failed to delete relationship:', error);
        alert('Failed to delete relationship. Check console for details.');
    }
}

/**
 * Populate model select dropdowns
 */
function populateModelSelects() {
    const fromSelect = document.getElementById('fromModel');
    const toSelect = document.getElementById('toModel');
    
    // Clear existing options except first
    fromSelect.innerHTML = '<option value="">Select model...</option>';
    toSelect.innerHTML = '<option value="">Select model...</option>';
    
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
 * Update from columns dropdown based on selected model
 */
async function updateFromColumns() {
    const modelName = document.getElementById('fromModel').value;
    const columnSelect = document.getElementById('fromColumn');
    
    columnSelect.innerHTML = '<option value="">Select column...</option>';
    
    if (!modelName) return;
    
    // Fetch entity details
    const entity = entities.find(e => e.name === modelName);
    if (entity && entity.columns) {
        // If we have column details in metadata
        // For now, use generic column IDs
        ['id', 'customer_id', 'store_id', 'product_id', 'order_id'].forEach(col => {
            const option = document.createElement('option');
            option.value = col;
            option.textContent = col;
            columnSelect.appendChild(option);
        });
    } else {
        // Generic fallback
        const option = document.createElement('option');
        option.value = `${modelName}_id`;
        option.textContent = `${modelName}_id`;
        columnSelect.appendChild(option);
    }
}

/**
 * Update to columns dropdown based on selected model
 */
async function updateToColumns() {
    const modelName = document.getElementById('toModel').value;
    const columnSelect = document.getElementById('toColumn');
    
    columnSelect.innerHTML = '<option value="">Select column...</option>';
    
    if (!modelName) return;
    
    // Fetch entity details
    const entity = entities.find(e => e.name === modelName);
    if (entity && entity.columns) {
        // If we have column details in metadata
        ['id', 'customer_id', 'store_id', 'product_id', 'order_id'].forEach(col => {
            const option = document.createElement('option');
            option.value = col;
            option.textContent = col;
            columnSelect.appendChild(option);
        });
    } else {
        // Generic fallback
        const option = document.createElement('option');
        option.value = `${modelName}_id`;
        option.textContent = `${modelName}_id`;
        columnSelect.appendChild(option);
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
    
    // Build relationship object
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
                'X-Role': 'admin'  // Set role header
            },
            body: JSON.stringify(relationshipData)
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            alert('Relationship saved successfully!');
            closeRelationshipModal();
            await loadRelationships();
            await reindexSemantic();
        } else {
            alert(`Failed to save relationship: ${result.error}`);
        }
    } catch (error) {
        console.error('Failed to save relationship:', error);
        alert('Failed to save relationship. Check console for details.');
    }
});

/**
 * Reindex semantic layer after changes
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
 * Refresh ERD
 */
async function refreshERD() {
    await loadEntities();
    await loadRelationships();
}

/**
 * Show empty state
 */
function showEmptyState(containerId, title, message) {
    const container = typeof containerId === 'string' 
        ? document.getElementById(containerId) 
        : containerId;
    
    container.innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">📦</div>
            <h3>${title}</h3>
            <p>${message}</p>
        </div>
    `;
}

/**
 * Show error state
 */
function showError(containerId, message) {
    const container = typeof containerId === 'string' 
        ? document.getElementById(containerId) 
        : containerId;
    
    container.innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">⚠️</div>
            <h3>Error</h3>
            <p>${message}</p>
        </div>
    `;
}


