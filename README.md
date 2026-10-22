# AutoLogin · 定时自动登录签到工具

一个运行在 Windows 桌面的小工具：按你设定的时间自动打开指定站点、完成登录，并按预设顺序点击页面菜单，用于每日签到、打卡、系统巡检等重复性操作。

底层用 [Playwright](https://playwright.dev/python/) 驱动浏览器（Chromium / Edge / Chrome 自动择优），
界面用 Tkinter，定时用 APScheduler。所有站点配置、登录会话都保存在本地，不上传任何服务器。

> 适用场景：企业内网门户、OA / 考勤系统、校园信息门户等"每天点一下"的页面。
> 工具只负责复现你自己的正常操作，请遵守目标站点的使用条款。

---

## 功能特性

| 能力 | 说明 |
| --- | --- |
| 多站点管理 | 图形界面新增 / 编辑 / 复制 / 删除站点，配置持久化到 `sites.json` |
| 表单自动登录 | 用 CSS 选择器定位用户名、密码、提交按钮，自动填写并提交 |
| 登录结果校验 | 以"URL 是否离开登录页"作为成功判据，避免把失败当成功 |
| 会话复用 | 首次登录后保存 cookie/localStorage，之后免登录直达；会话失效自动回退账号密码重登 |
| 验证码站点授权 | 带滑块/图形验证码的站点，点「授权」打开可见浏览器手动登录一次，之后复用该会话 |
| 菜单点击策略 | 每行一个 CSS 选择器，按顺序点击，间隔支持 ±30% 随机抖动 |
| 定时 + 随机抖动 | 每天在 `HH:MM ± N 分钟` 内随机选一个时刻执行，避免固定时间戳的机械行为 |
| 节假日跳过 | 依据 `holidays.json` 跳过法定节假日与普通周末，调休补班日仍正常执行 |
| 系统托盘 | 关闭 / 最小化窗口后定时任务继续在后台运行，托盘菜单可恢复窗口或彻底退出 |
| 单实例保护 | 重复启动只会唤起已有窗口，不会跑出两套定时任务 |
| 界面自动刷新 | 定时任务执行完毕后列表自动更新"上次运行 / 状态"，无需手动点刷新 |
| 运行日志 | 界面内实时日志 + 数据目录下 `auto_login.log` 文件日志 |

---

## 目录结构

```text
Automatic_site_checkin/
├── README.md                 项目说明（本文件）
├── pyproject.toml            包元数据、依赖、pytest / ruff 配置
├── requirements.txt          运行依赖
├── requirements-dev.txt      开发与打包依赖
├── run.py                    源码运行入口（等价于 python -m autologin）
├── .editorconfig             统一缩进与换行风格
├── .gitignore                忽略运行数据、缓存与打包产物
├── src/
│   └── autologin/            可安装的 Python 包
│       ├── __init__.py       版本号与模块导航
│       ├── __main__.py       程序入口：日志、单实例锁、启动 GUI
│       ├── paths.py          运行期数据目录解析
│       ├── config.py         站点配置模型与 JSON 持久化
│       ├── login_runner.py   Playwright 登录执行器（表单 / 会话 / 授权）
│       ├── scheduler.py      APScheduler 定时任务与排程计算
│       ├── holiday.py        工作日判断（节假日 + 调休）
│       ├── gui.py            Tkinter 主窗口与站点编辑对话框
│       ├── tray.py           Windows 系统托盘（ctypes 实现）
│       ├── single_instance.py 命名互斥量单实例锁
│       └── assets/           应用图标与第三方素材许可
├── tests/                    单元 / 界面回归测试（unittest）
├── packaging/
│   └── AutoLogin.spec        PyInstaller 打包配置
└── data/
    └── holidays.example.json 节假日配置示例
```

设计约定：

- **`src/` 布局**：源码与仓库根目录隔离，避免"在当前目录跑脚本"式的隐式导入；
- **包内相对导入**：模块之间一律 `from .xxx import ...`，可安装、可测试、可打包；
- **运行数据与代码分离**：`sites.json` 等不进仓库（已在 `.gitignore` 中排除）。

---

## 安装

要求 Windows 10/11 + Python 3.9 及以上。

```powershell
git clone <repo-url> Automatic_site_checkin
cd Automatic_site_checkin

# 建议使用虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# 首次使用前安装 Playwright 的 Chromium 内核（只需一次）
python run.py --install
```

如果本机已安装 Microsoft Edge 或 Chrome，即使不下载 Chromium 也能运行——
执行器会按 `Chromium → Edge → Chrome` 的顺序自动回退。

也可以把项目装成命令行工具：

```powershell
pip install -e .
autologin            # 启动界面
autologin --install  # 安装浏览器内核
autologin --version  # 查看版本
```

---

## 使用

1. **新增站点**：点击「新增」，填写名称、登录页地址、用户名、密码，以及三个选择器
   （用户名输入框、密码输入框、提交按钮）。选择器就是浏览器开发者工具里能直接用的 CSS 选择器，
   例如 `#username`、`input[name="password"]`、`button[type=submit]`。
2. **配置菜单点击**：在「菜单点击策略」里每行写一个选择器，工具会按顺序点击，
   用于进入签到页 / 打卡页等需要多步跳转的入口。
3. **设置定时**：`每天定时` 填 `HH:MM`；`随机抖动分钟` 填 `N` 表示每天在该时刻前后
   N 分钟内随机执行（填 0 则精确执行）。
4. **验证码站点**：选中站点点「授权」，在弹出的浏览器里手动完成登录（含滑块），
   成功后会话被保存，日常执行时直接复用。
5. **立即验证**：点「立即执行」，在下方日志区观察每一步结果；成功后列表会显示运行时间与状态。
6. **后台运行**：关闭或最小化窗口后程序缩到系统托盘，定时任务继续运行；
   需要彻底退出请用界面上的「退出」按钮或托盘右键菜单。

### 选择器怎么找

在浏览器里按 `F12` → 用"选择元素"箭头点中目标输入框 → 右键 `Copy` → `Copy selector`，
粘贴到对应字段即可。不同站点差异很大，建议先用「立即执行」验证一次再交给定时任务。

---

## 运行数据

以下文件都位于**数据目录**，首次运行自动创建：

| 文件 | 内容 |
| --- | --- |
| `sites.json` | 站点配置与最近一次运行状态 |
| `session_<站点id>.json` | 该站点的登录会话（cookie / localStorage） |
| `holidays.json` | 可选，法定节假日与调休补班日期 |
| `auto_login.log` | 运行日志 |

数据目录的确定顺序：

1. 环境变量 `AUTOLOGIN_DATA_DIR`；
2. 打包运行（PyInstaller）→ 可执行文件所在目录（便携模式，拷走文件夹即带走配置）；
3. 源码检出 → 仓库根目录；
4. 其它（`pip install` 安装到 site-packages）→ `%APPDATA%\AutoLogin`。

节假日文件格式（可参考 `data/holidays.example.json`）：

```json
{
  "holidays": ["2026-10-01", "2026-10-02"],
  "workdays": ["2026-10-10"]
}
```

- `holidays`：法定放假日期，即使是工作日也跳过；
- `workdays`：调休补班日期，即使是周末也照常执行；
- 文件缺失时退化为"仅跳过周六周日"。

---

## 打包为 exe

```powershell
pip install -r requirements-dev.txt
pyinstaller --clean --noconfirm packaging/AutoLogin.spec
```

产物在 `dist/AutoLogin/`（onedir 模式）。打包后 `sites.json`、`session_*.json`、
`holidays.json`、`auto_login.log` 都生成在 `AutoLogin.exe` 同级目录，便于整体拷贝分发。

---

## 开发与测试

```powershell
pip install -r requirements-dev.txt
$env:PYTHONPATH = "src"

python -m unittest discover -s tests -v     # 全部测试
python -m unittest tests.test_login_runner -v  # 单个模块
```

| 测试文件 | 覆盖内容 |
| --- | --- |
| `tests/test_login_runner.py` | 会话复用、会话过期回退、登录失败、会话保存失败（全程 mock，不访问网络） |
| `tests/test_auto_refresh.py` | 定时任务执行后界面列表自动刷新 |
| `tests/test_gui_password.py` | 密码显示 / 隐藏切换不丢字符 |
| `tests/test_tray.py` | 托盘图标注册与释放、最小化 / 关闭 / 恢复、资源管理器重启 |
| `tests/test_single_instance.py` | 跨进程单实例锁、重复启动不初始化界面 |
| `tests/test_holiday.py` | 节假日、调休、损坏配置文件的降级行为 |

> 界面与托盘相关测试会真实创建窗口，需要在有桌面会话的 Windows 上运行；
> 在无显示环境（如 CI 容器）中请跳过 `test_tray` / `test_auto_refresh` / `test_gui_password`。

常用环境变量：

| 变量 | 作用 |
| --- | --- |
| `AUTOLOGIN_DATA_DIR` | 覆盖数据目录，便于用隔离配置调试 |

---

## 安全提示

- `sites.json` 中的密码是**明文**存储的（本地文件），请自行控制该目录的访问权限；
- `session_*.json` 等同于登录凭据，泄露即可免密登录，切勿提交到仓库或分享；
- 本仓库的 `.gitignore` 已排除上述文件，提交前请确认 `git status` 干净；
- 建议为自动化单独设置一个专用账号，不要在公共电脑上保存凭据。

---

## 常见问题

**Q：提示"无可用浏览器（已尝试 chromium/msedge/chrome）"？**
执行 `python run.py --install` 安装 Chromium，或安装 Microsoft Edge / Chrome 后重试。

**Q：登录一直失败，日志显示"仍停留在登录页"？**
多半是选择器不匹配或站点有验证码。先用「立即执行」看日志，确认选择器；有验证码的站点请用「授权」。

**Q：会话过几天就失效？**
多数系统会定期让 token 过期。工具会自动回退到账号密码重新登录并刷新会话；
若站点还有验证码，则需要重新「授权」。

**Q：为什么执行时间每天不一样？**
这是"随机抖动"特性，在设定时刻前后随机取点，避免每天固定秒级时间戳的机械行为。填 0 可关闭。

---

## 第三方素材

应用图标基于 Twemoji 的 "Locked with key"（U+1F510）重新着色缩放，
遵循 CC BY 4.0。来源与完整许可见 `src/autologin/assets/ATTRIBUTION.txt`
与 `src/autologin/assets/TWEMOJI-LICENSE.txt`。

## 许可

本仓库未附带开源许可证；如需对外分发，请先补充 `LICENSE` 文件。
