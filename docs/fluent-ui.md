# WinUI 3 界面

现代面板的外观按 Windows 11 / WinUI 3 的规则做，不再自创材质。理由很实际：这是 Windows 独占工具，跟随系统能白拿 Snap、贴边、多显示器 DPI 和系统菜单，也省掉"像不像桌面应用"的争论。

## 两件事从系统读

| 来源 | 用途 |
|---|---|
| `HKCU\...\Themes\Personalize\AppsUseLightTheme` | 浅色 / 深色 |
| `HKCU\...\DWM\AccentColor`（ABGR） | 选中、焦点、主按钮 |

在 Windows 设置里改强调色或切深色，应用跟着变，不需要重启系统。`WAM_UI_THEME=light|dark` 可强制一套，供测试和离屏截图使用。

## 令牌

| 角色 | 浅色 | 深色 |
|---|---|---|
| window（Mica 底） | `#F3F3F3` | `#202020` |
| surface（内容层） | `#FFFFFF` | `#2B2B2B` |
| surface_alt（凹陷块） | `#F9F9F9` | `#323232` |
| border | `#E5E5E5` | `#3A3A3A` |
| border_strong（控件描边） | `#D6D6D6` | `#474747` |
| text / muted / faint | `#1B1B1B` / `#5D5D5D` / `#8A8A8A` | `#FFFFFF` / `#C5C5C5` / `#9A9A9A` |

圆角：卡片 8，控件 4。控件高度 32。分隔线一律 1px，不用阴影分层——Fluent 的层级靠描边和底色，不靠投影。

## 控件约定

| 控件 | 做法 |
|---|---|
| 卡片 | 白底 + 1px 描边，8px 角；**没有** elevation |
| 按钮 | 4px 角、1px 描边；主按钮填强调色，文字用 `accent_text`（自动取黑或白） |
| 输入框 | 白底 + 1px `border_strong`；聚焦时底部 2px 强调色线，不加外发光 |
| 会话行 | 选中：`hover` 底 + 左侧 3px 强调色胶囊；悬停：`surface_alt` 底 |
| 气泡 | 己方 `accent` 8% 底，对方 `surface_alt` 底 + 1px 描边 |

## 为什么删掉了新拟物

新拟物要求"元素与背景同色、只靠阴影分层"，这条约束在 Qt 里要靠 `QGraphicsDropShadowEffect` 硬凑（一个控件只能挂一个 effect），而且在深色下根本做不出来。WinUI 用描边 + 底色分层，Qt 原生支持，深色浅色各一套令牌就够。

`ui/fluent.py` 保留了旧的函数名（`apply_raised`、`paint_surface`），其中 elevation 相关的是空实现——这样重绘控件时不必改每个调用点。新代码请直接用 `paint_surface` / `paint_well`。
