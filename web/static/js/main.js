document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('searchInput');
    const searchButton = document.getElementById('searchButton');
    const searchResults = document.getElementById('searchResults');
    const filterContainer = document.getElementById('filterContainer');
    const exportContainer = document.getElementById('exportContainer');
    const exportFolderPath = document.getElementById('exportFolderPath');
    const browseExportFolderBtn = document.getElementById('browseExportFolderBtn');
    const exportSelectedBtn = document.getElementById('exportSelectedBtn');
    const selectedCount = document.getElementById('selectedCount');
    const folderPathInput = document.getElementById('folderPath');
    const processButton = document.getElementById('processButton');
    const processLog = document.getElementById('processLog');
    const browseButton = document.getElementById('browseButton');
    const videoModal = new bootstrap.Modal(document.getElementById('videoModal'));
    const videoPlayer = document.getElementById('videoPlayer');
    const videoDetails = document.getElementById('videoDetails');
    const searchContainer = document.querySelector('.search-container');
    const searchBox = document.getElementById('searchBox');
    const pageContainer = document.querySelector('.page-container');
    
    // 确保搜索框在页面加载时可见
    searchBox.style.display = 'block';
    
    // 存储搜索结果和当前过滤条件
    let allSearchResults = [];
    let activeFilters = {};
    let selectedVideos = new Set(); // 存储选中的视频ID
    
    // 元数据字段中英文映射
    const metadataTranslation = {
        'color': '颜色',
        'date': '拍摄时间',
        'document_type': '描述类型',
        'duration': '时长',
        'location': '拍摄位置',
        'orientation': '屏幕方向',
        'people': '是否有人像',
        'scene': '拍摄场景',
        'time_of_day': '拍摄时间段',
        'sql_id': 'ID',
        'processed_at': '处理时间',
        'video_path': '视频路径',
        'camera_angle': '摄像机角度',
        'camera_movement': '摄像机运动',
        'camera_shot_type': '镜头类型',
        'star_rating': '评分'
    };
    
    // 需要过滤的字段
    const filterFields = ['location', 'orientation', 'people', 'scene', 'time_of_day', 'color', 'camera_angle', 'camera_movement', 'camera_shot_type'];

    // 初始化时清空搜索结果容器
    searchResults.innerHTML = '';
    
    // 过滤器切换按钮事件
    const filterToggleBtn = document.getElementById('filterToggleBtn');
    const filterToggleContainer = document.getElementById('filterToggleContainer');
    
    if (filterToggleBtn) {
        filterToggleBtn.addEventListener('click', function() {
            // 切换过滤器容器的显示状态
            filterContainer.classList.toggle('show');
            // 更新按钮的活动状态
            this.classList.toggle('active');
            
            // 更新箭头图标
            const chevronIcon = this.querySelector('.bi-chevron-down, .bi-chevron-up');
            if (chevronIcon) {
                if (filterContainer.classList.contains('show')) {
                    // 如果过滤器已展开，显示向上箭头
                    chevronIcon.classList.remove('bi-chevron-down');
                    chevronIcon.classList.add('bi-chevron-up');
                } else {
                    // 如果过滤器已收起，显示向下箭头
                    chevronIcon.classList.remove('bi-chevron-up');
                    chevronIcon.classList.add('bi-chevron-down');
                }
            }
        });
    }
    
    // 检查是否已经搜索过
    const hasSearched = !filterContainer.classList.contains('d-none') ||
                        !exportContainer.classList.contains('d-none') ||
                        searchResults.innerHTML.trim() !== '';
    
    // 如果已经搜索过，添加搜索激活样式
    if (hasSearched) {
        searchContainer.classList.add('search-active');
        pageContainer.classList.add('search-results-visible');
    } else {
        // 如果没有搜索过，确保页面处于初始状态
        searchContainer.classList.remove('search-active');
        pageContainer.classList.remove('search-results-visible');
    }

    // Handle search
    searchButton.addEventListener('click', async function() {
        const query = searchInput.value.trim();
        if (!query) return;

        searchButton.disabled = true;
        searchResults.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div></div>';
        filterContainer.classList.remove('show'); // 确保过滤器是隐藏的
        filterContainer.classList.add('d-none');
        filterToggleContainer.classList.add('d-none'); // 隐藏过滤器切换按钮
        exportContainer.classList.add('d-none');
        selectedVideos.clear();
        updateSelectedCount();
        
        // 添加搜索激活样式，改变布局
        searchContainer.classList.add('search-active');
        
        // 添加页面容器样式，使搜索框显示在顶部
        pageContainer.classList.add('search-results-visible');
        
        // 确保搜索框保持可见，并且显示当前搜索的关键词
        searchInput.value = query;
        
        // 确保搜索框不会被隐藏
        document.getElementById('searchBox').style.display = 'block';

        try {
            const response = await fetch('/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: query
                })
            });

            const data = await response.json();
            
            if (data.error) {
                searchResults.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
                return;
            }

            // 存储搜索结果
            allSearchResults = data.results;
            
            // 调试信息：打印搜索结果中的transcript内容
            console.log("搜索结果数量:", allSearchResults.length);
            allSearchResults.forEach((result, index) => {
                console.log(`结果 ${index + 1}:`);
                console.log(`- 视频ID: ${result.video_id}`);
                console.log(`- 描述长度: ${(result.description || '').length}`);
                console.log(`- 对话长度: ${(result.transcript || '').length}`);
                console.log(`- 对话内容: ${result.transcript ? result.transcript.substring(0, 50) + '...' : '无'}`);
                console.log(`- 分数: 描述=${result.scores.description.toFixed(4)}, 对话=${result.scores.transcript.toFixed(4)}`);
            });
            
            // 重置过滤条件
            activeFilters = {};
            
            // 生成过滤器
            generateFilters(allSearchResults);
            
            // 显示过滤器开关按钮，但确保它紧贴搜索框底部
            filterToggleContainer.classList.remove('d-none');
            
            // 显示导出面板，确保它与过滤切换按钮之间没有多余间距
            exportContainer.classList.remove('d-none');
            
            // 显示搜索结果
            displaySearchResults(allSearchResults);
        } catch (error) {
            searchResults.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
        } finally {
            searchButton.disabled = false;
        }
    });

    // 生成过滤器
    function generateFilters(results) {
        // 如果没有结果，不显示过滤器
        if (results.length === 0) {
            filterContainer.classList.add('d-none');
            filterToggleContainer.classList.add('d-none'); // 隐藏过滤器切换按钮
            return;
        }
        
        // 收集所有可能的过滤值
        const filterValues = {};
        
        // 初始化过滤字段
        filterFields.forEach(field => {
            filterValues[field] = new Set();
        });
        
        // 收集所有结果中的过滤值
        results.forEach(result => {
            filterFields.forEach(field => {
                if (result.metadata && result.metadata[field]) {
                    filterValues[field].add(result.metadata[field]);
                }
            });
        });
        
        // 创建过滤器UI
        filterContainer.innerHTML = '<h5>过滤选项</h5><div class="filter-groups"></div>';
        const filterGroupsContainer = filterContainer.querySelector('.filter-groups');
        
        // 创建主要过滤器容器（一行显示）
        const mainFiltersContainer = document.createElement('div');
        mainFiltersContainer.className = 'main-filters';
        filterGroupsContainer.appendChild(mainFiltersContainer);
        
        // 主要过滤器字段（一行显示）
        const mainFilterFields = ['color', 'time_of_day', 'orientation', 'people', 'scene', 'camera_angle', 'camera_movement', 'camera_shot_type'];
        
        // 为主要过滤字段创建过滤组
        mainFilterFields.forEach(field => {
            // 如果该字段有值
            if (filterValues[field].size > 0) {
                const fieldName = metadataTranslation[field] || field;
                
                // 创建过滤组
                const filterGroup = document.createElement('div');
                filterGroup.className = 'filter-group';
                filterGroup.innerHTML = `
                    <div class="filter-title">${fieldName}:</div>
                    <div class="filter-buttons" data-field="${field}"></div>
                `;
                
                const filterButtons = filterGroup.querySelector('.filter-buttons');
                
                // 添加"全部"按钮
                const allButton = document.createElement('button');
                allButton.className = 'btn btn-sm btn-outline-primary active';
                allButton.textContent = '全部';
                allButton.dataset.value = 'all';
                filterButtons.appendChild(allButton);
                
                // 获取排序后的值
                const sortedValues = Array.from(filterValues[field]).sort();
                
                // 添加每个值的按钮
                sortedValues.forEach(value => {
                    const button = document.createElement('button');
                    button.className = 'btn btn-sm btn-outline-primary';
                    
                    // 特殊处理人像字段
                    if (field === 'people') {
                        if (value === '有人像') {
                            button.textContent = '有';
                        } else if (value === '无人像') {
                            button.textContent = '无';
                        } else {
                            button.textContent = value;
                        }
                    } else {
                        button.textContent = value;
                    }
                    
                    button.dataset.value = value;
                    filterButtons.appendChild(button);
                });
                
                mainFiltersContainer.appendChild(filterGroup);
            }
        });
        
        // 单独处理拍摄位置字段（单独一行）
        if (filterValues['location'] && filterValues['location'].size > 0) {
            const locationGroup = document.createElement('div');
            locationGroup.className = 'location-filter-group';
            locationGroup.innerHTML = `
                <div class="filter-title">${metadataTranslation['location']}:</div>
                <div class="filter-buttons" data-field="location"></div>
            `;
            
            const locationButtons = locationGroup.querySelector('.filter-buttons');
            
            // 添加"全部"按钮
            const allButton = document.createElement('button');
            allButton.className = 'btn btn-sm btn-outline-primary active';
            allButton.textContent = '全部';
            allButton.dataset.value = 'all';
            locationButtons.appendChild(allButton);
            
            // 获取排序后的位置值
            const sortedLocations = Array.from(filterValues['location']).sort();
            
            // 添加每个位置的按钮
            sortedLocations.forEach(location => {
                const button = document.createElement('button');
                button.className = 'btn btn-sm btn-outline-primary';
                button.textContent = location;
                button.dataset.value = location;
                locationButtons.appendChild(button);
            });
            
            filterGroupsContainer.appendChild(locationGroup);
        }
        
        // 移除d-none类，但保持隐藏状态（通过CSS的max-height和opacity控制）
        filterContainer.classList.remove('d-none');
        // 初始状态不展开
        filterContainer.classList.remove('show');
        
        // 为所有过滤按钮添加点击事件
        document.querySelectorAll('.filter-buttons button').forEach(button => {
            button.addEventListener('click', handleFilterClick);
        });
    }
    
    // 过滤器按钮点击处理函数
    function handleFilterClick(e) {
        if (e.target.tagName === 'BUTTON') {
            const buttonGroup = e.target.closest('.filter-buttons');
            if (!buttonGroup) return;
            
            const field = buttonGroup.dataset.field;
            const value = e.target.dataset.value;
            
            // 更新按钮状态
            buttonGroup.querySelectorAll('button').forEach(btn => {
                btn.classList.remove('active');
            });
            e.target.classList.add('active');
            
            // 更新过滤条件
            if (value === 'all') {
                delete activeFilters[field];
            } else {
                activeFilters[field] = value;
            }
            
            // 应用过滤
            applyFilters();
        }
    }
    
    // 应用过滤条件
    function applyFilters() {
        // 如果没有活跃的过滤条件，显示所有结果
        if (Object.keys(activeFilters).length === 0) {
            displaySearchResults(allSearchResults);
            return;
        }
        
        // 过滤结果
        const filteredResults = allSearchResults.filter(result => {
            // 检查每个活跃的过滤条件
            for (const [field, value] of Object.entries(activeFilters)) {
                // 如果结果不满足过滤条件，排除它
                if (!result.metadata || result.metadata[field] !== value) {
                    return false;
                }
            }
            // 所有过滤条件都满足
            return true;
        });
        
        // 显示过滤后的结果
        displaySearchResults(filteredResults);
    }

    // Handle video processing
    processButton.addEventListener('click', async function() {
        const folderPath = folderPathInput.value.trim();
        if (!folderPath) {
            alert('请先选择视频文件夹');
            return;
        }

        processButton.disabled = true;
        processLog.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div></div>';

        try {
            const response = await fetch('/process_videos', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ folder_path: folderPath })
            });

            const data = await response.json();
            
            if (data.error) {
                processLog.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
                return;
            }

            // Display logs in real-time
            processLog.innerHTML = '';
            data.messages.forEach(message => {
                const logEntry = document.createElement('div');
                logEntry.className = 'log-entry';
                logEntry.textContent = message;
                processLog.appendChild(logEntry);
                processLog.scrollTop = processLog.scrollHeight;
            });
        } catch (error) {
            processLog.innerHTML = `<div class="alert alert-danger">Error: ${error.message}</div>`;
        } finally {
            processButton.disabled = false;
        }
    });

    // Function to play video in modal
    function playVideo(videoPath, videoId) {
        // 查找当前视频对象
        const videoResult = allSearchResults.find(v => v.video_id === videoId);
        if (!videoResult) return;
        
        // 准备显示内容 - 强制检查transcript字段
        const description = videoResult.description || '';
        const transcript = videoResult.transcript || '';
        
        const hasDescription = description.trim() !== '';
        const hasTranscript = transcript.trim() !== '';
        
        // 构建内容HTML
        let contentHTML = '';
        
        // 添加描述内容（如果有）
        if (hasDescription) {
            contentHTML += `
                <div class="mt-3">
                    <h6>视频描述：</h6>
                    <p class="description-text">${description}</p>
                </div>
            `;
        }
        
        // 添加对话内容（如果有）- 无论分数如何，只要有内容就显示
        if (hasTranscript) {
            contentHTML += `
                <div class="mt-3">
                    <h6>对话：</h6>
                    <p class="transcript-text">${transcript}</p>
                </div>
            `;
        }
        
        // 如果两者都没有，显示一个提示
        if (!hasDescription && !hasTranscript) {
            contentHTML = '<div class="text-muted mt-3">无可用内容</div>';
        }
        
        // Check if file exists
        fetch(`/check_file?path=${encodeURIComponent(videoPath)}`)
            .then(response => response.json())
            .then(data => {
                if (data.exists) {
                    // Set up video player
                    videoPlayer.src = `/stream_video/${data.video_id}?path=${encodeURIComponent(videoPath)}`;
                    videoPlayer.load();
                    
                    // Display video details
                    videoDetails.innerHTML = `
                        <h5>${data.file_info.filename}</h5>
                        <p class="text-muted">Path: ${videoPath}</p>
                        <p class="text-muted">Size: ${formatFileSize(data.file_info.size)}</p>
                        ${contentHTML}
                    `;
                    
                    // Show modal
                    videoModal.show();
                    
                    // Auto play
                    videoPlayer.play().catch(e => console.log('Auto-play prevented:', e));
                } else {
                    alert('Video file not found at the specified path');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error checking video file');
            });
    }
    
    // Format file size
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Generate star rating display
    function generateStarRating(rating, videoId) {
        // Ensure rating is between 0 and 5
        rating = Math.min(5, Math.max(0, parseInt(rating) || 0));
        
        // Generate HTML for stars
        let starsHTML = '';
        
        for (let i = 1; i <= 5; i++) {
            if (i <= rating) {
                // Full star
                starsHTML += '<i class="bi bi-star-fill" data-rating="' + i + '"></i>';
            } else {
                // Empty star
                starsHTML += '<i class="bi bi-star" data-rating="' + i + '"></i>';
            }
        }
        
        return `<div class="rating-stars" data-video-id="${videoId}">${starsHTML}</div>`;
    }

    // Display search results
    function displaySearchResults(results) {
        searchResults.innerHTML = '';
        
        // 确保搜索框可见
        document.getElementById('searchBox').style.display = 'block';
        
        // 确保页面容器有正确的样式
        pageContainer.classList.add('search-results-visible');
        
        if (results.length === 0) {
            searchResults.innerHTML = '<div class="alert alert-info">No results found</div>';
            return;
        }
        
        results.forEach(result => {
            const resultElement = document.createElement('div');
            resultElement.className = 'video-result';
            resultElement.dataset.videoId = result.video_id;
            
            // 如果视频已选中，添加选中样式
            if (selectedVideos.has(result.video_id)) {
                resultElement.classList.add('selected');
            }
            
            // Default thumbnail if none available
            const thumbnailSrc = result.thumbnail 
                ? `/static/${result.thumbnail}` 
                : 'https://via.placeholder.com/180x120?text=No+Thumbnail';
            
            // 创建元数据HTML
            const metadataHTML = Object.entries(result.metadata)
                .filter(([key, value]) => {
                    // 过滤掉不需要显示的字段
                    return value && 
                           value.toString().trim() !== '' && 
                           key !== 'video_path' && 
                           key !== 'processed_at' &&
                           key !== 'sql_id' &&
                           key !== 'document_type';
                })
                .map(([key, value]) => {
                    // 翻译字段名
                    const translatedKey = metadataTranslation[key] || key;
                    
                    // 处理特殊字段
                    let displayValue = value;
                    if (key === 'duration') {
                        displayValue = `${value} 秒`;
                    }
                    
                    return `<span class="metadata-item">${translatedKey}: ${displayValue}</span>`;
                })
                .join('');
            
            // 准备显示内容 - 强制检查transcript字段
            const description = result.description || '';
            const transcript = result.transcript || '';
            
            const hasDescription = description.trim() !== '';
            const hasTranscript = transcript.trim() !== '';
            
            // 构建内容HTML
            let contentHTML = '';
            
            // 添加描述内容（如果有）
            if (hasDescription) {
                contentHTML += `
                    <div class="content-block description-block">
                        <h6 class="content-title">视频描述：</h6>
                        <div class="content-text">${description}</div>
                    </div>
                `;
            }
            
            // 添加对话内容（如果有）- 无论分数如何，只要有内容就显示
            if (hasTranscript) {
                contentHTML += `
                    <div class="content-block transcript-block">
                        <h6 class="content-title">对话：</h6>
                        <div class="content-text">${transcript}</div>
                    </div>
                `;
            }
            
            // 如果两者都没有，显示一个提示
            if (!hasDescription && !hasTranscript) {
                contentHTML = '<div class="text-muted">无可用内容</div>';
            }
            
            // 确定搜索类型（用于标记）
            let searchTypeHTML = '';
            if (result.scores) {
                const descScore = result.scores.description || 0;
                const transScore = result.scores.transcript || 0;
                
                if (transScore > 0 && descScore > 0) {
                    searchTypeHTML = '<span class="metadata-item">搜索类型: 描述+对话</span>';
                } else if (transScore > descScore) {
                    searchTypeHTML = '<span class="metadata-item">搜索类型: 对话</span>';
                } else {
                    searchTypeHTML = '<span class="metadata-item">搜索类型: 描述</span>';
                }
            }
            
            resultElement.innerHTML = `
                <input type="checkbox" class="video-select-checkbox" ${selectedVideos.has(result.video_id) ? 'checked' : ''}>
                <div class="video-thumbnail-wrapper">
                    <div class="video-thumbnail-container">
                        <img src="${thumbnailSrc}" alt="Video thumbnail" class="video-thumbnail">
                    </div>
                    <div class="rating-box">
                        ${generateStarRating(result.metadata.star_rating || 0, result.video_id)}
                    </div>
                </div>
                <div class="video-info">
                    <div class="video-content">
                        ${contentHTML}
                    </div>
                    <div class="video-metadata">
                        ${searchTypeHTML}
                        ${metadataHTML}
                    </div>
                    <div class="scores">
                        <small>
                            Description Score: ${result.scores.description.toFixed(4)} |
                            Transcript Score: ${result.scores.transcript.toFixed(4)} |
                            Combined Score: ${result.scores.combined.toFixed(4)}
                        </small>
                    </div>
                </div>
            `;
            
            // 添加选择事件
            const checkbox = resultElement.querySelector('.video-select-checkbox');
            checkbox.addEventListener('change', function() {
                if (this.checked) {
                    resultElement.classList.add('selected');
                    selectedVideos.add(result.video_id);
                } else {
                    resultElement.classList.remove('selected');
                    selectedVideos.delete(result.video_id);
                }
                updateSelectedCount();
            });
            
            // Add click event for thumbnail
            const thumbnail = resultElement.querySelector('.video-thumbnail');
            thumbnail.addEventListener('click', () => {
                playVideo(result.video_path, result.video_id);
            });
            
            // Add click event for rating stars
            const ratingStars = resultElement.querySelector('.rating-stars');
            if (ratingStars) {
                ratingStars.addEventListener('click', function(e) {
                    if (e.target.tagName === 'I' && e.target.dataset.rating) {
                        const rating = parseInt(e.target.dataset.rating);
                        const videoId = this.dataset.videoId;
                        updateVideoRating(result.video_path, videoId, rating);
                    }
                });
            }
            
            searchResults.appendChild(resultElement);
        });
    }
    
    // 更新选中视频计数
    function updateSelectedCount() {
        const count = selectedVideos.size;
        selectedCount.textContent = `已选择: ${count} 个视频`;
        exportSelectedBtn.disabled = count === 0;
        
        // 根据选择的视频数量更新按钮文本
        if (count > 1) {
            exportSelectedBtn.innerHTML = '<i class="bi bi-download"></i> 批量导出';
        } else {
            exportSelectedBtn.innerHTML = '<i class="bi bi-download"></i> 导出选中视频';
        }
    }
    
    // 选择导出文件夹
    async function selectExportFolder() {
        try {
            // 显示加载状态
            browseExportFolderBtn.disabled = true;
            browseExportFolderBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
            
            const response = await fetch('/browse_folder');
            const data = await response.json();
            
            if (data.success && data.folder_path) {
                exportFolderPath.value = data.folder_path;
                return data.folder_path;
            }
            
            return null;
        } catch (error) {
            console.error('Error selecting folder:', error);
            alert('选择文件夹时发生错误');
            return null;
        } finally {
            // 恢复按钮状态
            browseExportFolderBtn.disabled = false;
            browseExportFolderBtn.innerHTML = '<i class="bi bi-folder2-open"></i> 浏览';
        }
    }
    
    // 选择视频文件夹
    async function selectVideoFolder() {
        try {
            // 显示加载状态
            browseButton.disabled = true;
            browseButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
            
            const response = await fetch('/browse_folder');
            const data = await response.json();
            
            if (data.success && data.folder_path) {
                folderPathInput.value = data.folder_path;
                return data.folder_path;
            }
            
            return null;
        } catch (error) {
            console.error('Error selecting folder:', error);
            alert('选择文件夹时发生错误');
            return null;
        } finally {
            // 恢复按钮状态
            browseButton.disabled = false;
            browseButton.innerHTML = '<i class="bi bi-folder2-open"></i>';
        }
    }
    
    // 浏览导出文件夹按钮
    browseExportFolderBtn.addEventListener('click', function() {
        selectExportFolder();
    });
    
    // 导出选中视频按钮
    exportSelectedBtn.addEventListener('click', function() {
        if (selectedVideos.size === 0) {
            alert('请先选择要导出的视频');
            return;
        }
        
        if (!exportFolderPath.value) {
            selectExportFolder().then(folder => {
                if (folder) {
                    const selectedVideoObjects = allSearchResults.filter(v => selectedVideos.has(v.video_id));
                    exportVideos(selectedVideoObjects);
                }
            });
        } else {
            const selectedVideoObjects = allSearchResults.filter(v => selectedVideos.has(v.video_id));
            exportVideos(selectedVideoObjects);
        }
    });
    
    // 导出视频
    async function exportVideos(videos) {
        if (!videos || videos.length === 0) {
            alert('未选择任何视频');
            return;
        }
        
        if (!exportFolderPath.value) {
            alert('请先选择导出文件夹');
            return;
        }
        
        try {
            // 显示加载状态
            const originalBtnText = exportSelectedBtn.innerHTML;
            exportSelectedBtn.disabled = true;
            exportSelectedBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 导出中...';
            
            const response = await fetch('/export_videos', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    export_folder: exportFolderPath.value,
                    videos: videos
                })
            });
            
            const data = await response.json();
            
            if (data.error) {
                alert(`导出失败: ${data.error}`);
                return;
            }
            
            // 统计成功和失败的数量
            const successCount = data.results.filter(r => r.success).length;
            const failCount = data.results.filter(r => !r.success).length;
            
            let message = `导出完成!\n成功: ${successCount} 个视频`;
            
            if (failCount > 0) {
                message += `\n失败: ${failCount} 个视频`;
            }
            
            if (data.description_file && data.description_file.success) {
                message += `\n\n视频描述已保存到: ${data.description_file.path}`;
            }
            
            alert(message);
            
        } catch (error) {
            alert(`导出过程中发生错误: ${error.message}`);
        } finally {
            // 恢复按钮状态
            exportSelectedBtn.disabled = selectedVideos.size === 0;
            updateSelectedCount();
        }
    }

    // Update video rating
    async function updateVideoRating(videoPath, videoId, rating) {
        try {
            const response = await fetch('/update_rating', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    video_path: videoPath,
                    rating: rating
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Update the UI to reflect the new rating
                const ratingElement = document.querySelector(`.rating-stars[data-video-id="${videoId}"]`);
                if (ratingElement) {
                    ratingElement.innerHTML = '';
                    for (let i = 1; i <= 5; i++) {
                        const star = document.createElement('i');
                        star.classList.add('bi');
                        star.classList.add(i <= rating ? 'bi-star-fill' : 'bi-star');
                        star.dataset.rating = i;
                        ratingElement.appendChild(star);
                    }
                }
                
                // Update the rating in our stored search results
                for (let i = 0; i < allSearchResults.length; i++) {
                    if (allSearchResults[i].video_id === videoId) {
                        if (!allSearchResults[i].metadata) {
                            allSearchResults[i].metadata = {};
                        }
                        allSearchResults[i].metadata.star_rating = rating;
                        break;
                    }
                }
            } else {
                console.error('Failed to update rating:', data.error);
            }
        } catch (error) {
            console.error('Error updating rating:', error);
        }
    }

    // Handle browse button for video folder
    browseButton.addEventListener('click', function() {
        selectVideoFolder();
    });
    
    // Add enter key support for search
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            searchButton.click();
        }
    });
    
    // Reset video player when modal is closed
    document.getElementById('videoModal').addEventListener('hidden.bs.modal', function () {
        videoPlayer.pause();
        videoPlayer.src = '';
    });
}); 