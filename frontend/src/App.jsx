import { useState } from 'react'
import './App.css'

function App() {
  const [formData, setFormData] = useState({
    title: '',
    subtitle: '',
    videoPath: '',
    imagePath: ''
  })

  const [platforms, setPlatforms] = useState({
    douyin: false,
    xiaohongshu: false,
    bilibili: false,
    kuaishou: false
  })

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
  }

  const handleFileDrop = (e, type) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) {
      setFormData(prev => ({
        ...prev,
        [type]: file.path || file.name
      }))
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
  }

  const handlePlatformToggle = (platform) => {
    setPlatforms(prev => ({
      ...prev,
      [platform]: !prev[platform]
    }))
  }

  const handleSelectAll = () => {
    const allSelected = Object.values(platforms).every(v => v)
    const newState = !allSelected
    setPlatforms({
      douyin: newState,
      xiaohongshu: newState,
      bilibili: newState,
      kuaishou: newState
    })
  }

  const handlePreview = () => {
    console.log('预览数据:', { formData, platforms })
    alert('一键填充功能：将数据填充到各平台预览')
  }

  const handlePublishAll = () => {
    const selectedPlatforms = Object.keys(platforms).filter(p => platforms[p])
    if (selectedPlatforms.length === 0) {
      alert('请至少选择一个发布平台')
      return
    }
    console.log('一键发布到:', selectedPlatforms, formData)
    alert(`正在发布到: ${selectedPlatforms.join(', ')}`)
  }

  const allSelected = Object.values(platforms).every(v => v)

  return (
    <div className="app-container">
      <div className="app-header">
        <h1>视频发布平台</h1>
      </div>

      <div className="content-wrapper">
        <div className="left-panel">
          <h2>发布信息</h2>

          <div className="form-group">
            <label>标题</label>
            <input
              type="text"
              name="title"
              value={formData.title}
              onChange={handleInputChange}
              placeholder="请输入视频标题"
            />
          </div>

          <div className="form-group">
            <label>副标题</label>
            <input
              type="text"
              name="subtitle"
              value={formData.subtitle}
              onChange={handleInputChange}
              placeholder="请输入视频副标题"
            />
          </div>

          <div className="form-group">
            <label>视频上传</label>
            <div
              className="drop-zone"
              onDrop={(e) => handleFileDrop(e, 'videoPath')}
              onDragOver={handleDragOver}
            >
              {formData.videoPath ? (
                <div className="file-info">
                  <span>📹 {formData.videoPath}</span>
                </div>
              ) : (
                <div className="drop-hint">
                  拖拽视频文件到此处
                </div>
              )}
            </div>
          </div>

          <div className="form-group">
            <label>标题图片上传</label>
            <div
              className="drop-zone"
              onDrop={(e) => handleFileDrop(e, 'imagePath')}
              onDragOver={handleDragOver}
            >
              {formData.imagePath ? (
                <div className="file-info">
                  <span>🖼️ {formData.imagePath}</span>
                </div>
              ) : (
                <div className="drop-hint">
                  拖拽图片文件到此处
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="right-panel">
          <div className="panel-header">
            <h2>发布设置</h2>
            <button className="select-all-btn" onClick={handleSelectAll}>
              {allSelected ? '全不选' : '全选'}
            </button>
          </div>

          <div className="platform-buttons">
            <button
              className={`platform-btn ${platforms.douyin ? 'active' : ''}`}
              onClick={() => handlePlatformToggle('douyin')}
            >
              {platforms.douyin ? '✓ ' : ''}抖音
            </button>

            <button
              className={`platform-btn ${platforms.xiaohongshu ? 'active' : ''}`}
              onClick={() => handlePlatformToggle('xiaohongshu')}
            >
              {platforms.xiaohongshu ? '✓ ' : ''}小红书
            </button>

            <button
              className={`platform-btn ${platforms.bilibili ? 'active' : ''}`}
              onClick={() => handlePlatformToggle('bilibili')}
            >
              {platforms.bilibili ? '✓ ' : ''}B站
            </button>

            <button
              className={`platform-btn ${platforms.kuaishou ? 'active' : ''}`}
              onClick={() => handlePlatformToggle('kuaishou')}
            >
              {platforms.kuaishou ? '✓ ' : ''}快手
            </button>
          </div>

          <div className="main-actions">
            <button className="action-btn preview-btn" onClick={handlePreview}>
              一键填充
            </button>
            <button className="action-btn publish-all-btn" onClick={handlePublishAll}>
              一键发布
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
