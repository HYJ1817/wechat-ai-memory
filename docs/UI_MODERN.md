# 现代化 UI 升级

## 概述

为微信 AI 记忆库添加了现代化的 Glassmorphism（毛玻璃）UI 设计，灵感来自智能家居界面风格。

## 视觉特性

### 🎨 设计元素

- **暖色渐变背景** - 从米色到浅橙色的柔和渐变
- **毛玻璃效果** - 半透明卡片配合背景模糊
- **圆角设计** - 更大的圆角半径（12-16px）
- **柔和阴影** - 多层次阴影增加深度感
- **渐变按钮** - 橙色系主操作按钮

### 🎯 核心改进

1. **侧边栏** - 半透明白色卡片，模糊背景
2. **表单控件** - 玻璃质感的输入框和下拉框
3. **统计面板** - 毛玻璃卡片展示数据
4. **按钮** - 渐变色主按钮，玻璃质感次要按钮
5. **表格** - 透明背景的现代化数据表格

## 使用方法

### 方法 1: 使用批处理脚本（推荐）

双击运行 `start_modern.cmd`：

```cmd
start_modern.cmd
```

### 方法 2: 命令行启动

使用 Python 直接启动：

```powershell
# 现代化 UI
.\.venv-gui\Scripts\python.exe app_modern.py --modern

# 或使用短参数
.\.venv-gui\Scripts\python.exe app_modern.py -m
```

### 方法 3: 经典 UI（默认）

不带参数启动则使用原始样式：

```powershell
.\.venv-gui\Scripts\python.exe app_modern.py
```

或继续使用原有的启动方式：

```cmd
start.cmd
```

## 文件说明

### 新增文件

```
src/wechat_context_exporter/ui/
├── modern_styles.py      # 现代化样式表定义
├── glass_effects.py      # 毛玻璃效果辅助函数（预留）
app_modern.py              # 支持主题切换的启动器
start_modern.cmd           # 快速启动现代UI的批处理脚本
docs/UI_MODERN.md          # 本文档
```

### 原有文件

所有原有文件保持不变，现代化UI通过样式表覆盖实现，不影响核心功能。

## 技术实现

### QSS 样式表

使用 Qt 样式表（QSS）实现所有视觉效果：

- **线性渐变**: `qlineargradient()` 实现背景和按钮渐变
- **半透明**: `rgba(r, g, b, a)` 控制透明度
- **圆角**: `border-radius` 设置圆角半径
- **阴影**: 通过 `QGraphicsDropShadowEffect` 实现（可选）

### 模糊效果说明

当前版本使用半透明颜色模拟毛玻璃效果。真正的背景模糊需要：

1. `QGraphicsBlurEffect` - 性能开销较大
2. 平台支持 - Windows 10+ 的 Acrylic 效果
3. 自定义绘图 - 更复杂的实现

由于性能考虑，当前采用纯 CSS 方案，在大多数场景下效果接近。

## 颜色方案

### 主色调

| 颜色 | 用途 | RGB |
|------|------|-----|
| 暖米色 | 背景起点 | `rgb(250, 237, 225)` |
| 浅橙色 | 背景终点 | `rgb(235, 215, 200)` |
| 橙色 | 主操作按钮 | `rgb(255, 170, 100)` ~ `rgb(255, 140, 80)` |
| 白色半透明 | 玻璃卡片 | `rgba(255, 255, 255, 0.7)` |

### 状态色

- **成功/已连接**: 绿色系 `rgba(200, 240, 220, 0.9)`
- **警告/忙碌**: 橙色系 `rgba(255, 237, 213, 0.9)`
- **错误**: 红色系 `rgba(255, 220, 210, 0.9)`

## 兼容性

### 支持平台

- ✅ Windows 10/11
- ✅ 所有支持 Qt6 的系统

### 浏览器对比

虽然这是桌面应用，但样式灵感来自 Web 的 Glassmorphism 设计：

- CSS `backdrop-filter: blur()` → QSS 半透明模拟
- CSS `box-shadow` → QGraphicsDropShadowEffect

## 性能

### 渲染性能

现代化 UI 主要使用静态样式表，性能影响极小：

- 无动态模糊效果
- 无实时计算
- 纯 CSS 渲染

### 内存占用

与原版相比，内存增加可忽略（仅多加载一个样式表文件）。

## 开发计划

### v1.0 - 当前版本 ✅

- [x] 暖色渐变背景
- [x] 半透明卡片
- [x] 现代化圆角和间距
- [x] 渐变按钮
- [x] 主题切换启动器

### v1.1 - 计划中

- [ ] 添加悬停动画效果
- [ ] 卡片展开/收起动画
- [ ] 按钮点击波纹效果
- [ ] 优化颜色对比度（提升可访问性）

### v1.2 - 实验性

- [ ] Windows Acrylic 真实模糊（Windows 10+）
- [ ] 自定义绘图实现真实毛玻璃
- [ ] 主题配置文件（支持用户自定义颜色）

## 自定义主题

如需调整颜色方案，编辑 `src/wechat_context_exporter/ui/modern_styles.py`：

```python
# 修改背景渐变
MODERN_STYLESHEET = """
QMainWindow, QWidget#appRoot {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(250, 237, 225, 255),  # 起点颜色
        stop:1 rgba(235, 215, 200, 255)   # 终点颜色
    );
}
"""
```

## 截图对比

### 原版 UI
- 传统工具风格
- 浅灰色背景
- 标准控件

### 现代版 UI
- 智能家居风格
- 暖色渐变背景
- 毛玻璃卡片
- 圆角设计

## 问题反馈

如遇到 UI 问题：

1. **颜色对比度低** - 部分显示器可能需要调整背景亮度
2. **字体模糊** - 检查系统 DPI 缩放设置
3. **性能问题** - 切换回经典 UI（不带 `--modern` 参数）

## 参考设计

设计灵感来源：

- Apple HomeKit 界面
- Google Home 应用
- 现代智能家居控制面板
- Glassmorphism 设计趋势

## 技术栈

- **PySide6** - Qt6 Python 绑定
- **QSS** - Qt 样式表
- **Fusion Style** - Qt 跨平台样式引擎

---

## 快速开始

1. 确保已安装依赖（使用 `start.cmd` 首次运行）
2. 双击 `start_modern.cmd`
3. 享受现代化界面！

**提示**: 第一次启动可能需要几秒钟加载。
