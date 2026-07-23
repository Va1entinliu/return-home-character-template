# Return Home Character / 归航智能体

一个用于迁移 AI 陪伴角色的开源技术模板。

由于部分平台的智能体功能调整或下线，许多没有编程经验的用户难以继续使用自己长期交流的角色。本项目提供一条尽量简单的路线：保留原始人设和聊天历史，在手机上制作一个功能、界面布局和使用方式相近的独立 App，通过用户自己的 API Key 请求豆包 `Doubao-Seed-Character` 模型和火山语音合成服务，尽可能保留原来的角色语气、共同经历与音色体验。

它不能保证百分之百复刻原智能体，但希望用一种本地优先、可检查、可迁移的方式，帮助用户“挽回”自己的智能体。

## “完整版”指什么

本项目中的电脑网页和 `app/server.py` 只用于验证人设、上下文、记忆检索和
模型请求是否正确，**不属于最终交付物**。

一份完成迁移的完整版必须：

- 封装为可安装、可签名验证的 Android APK；
- APK 安装后直接在手机上运行，不依赖电脑、Python、局域网服务或
  `127.0.0.1`；
- 在手机本地保存聊天、记忆和加密后的 API Key；
- 由 Android 原生层完成 HTTPS 请求、录音权限和内存音频播放；
- 通过至少一台 Android 真机完成聊天、重启恢复、自动朗读、手动朗读和权限测试。

本仓库当前提供的是公开技术模板和基础代码，不附带任何人的人设、历史、密钥、
签名文件或通用成品 APK。为具体用户制作完整版时，还需要按照
`docs/ARCHITECTURE.md` 增加 Android 客户端、完成签名并输出最终 APK。

## 技术路线

```text
原始角色设定（不改写） + 三项手动记忆
                    │
                    ├── 最近 4～12 个完整对话轮
                    ├── 本地检索出的相关旧对话
                    └── 当前时间与可靠的历史时间
                                ↓
                 豆包 Doubao-Seed-Character
                                ↓
                            文字回复
                                ↓
                 火山 TTS / 私有复刻音色
                                ↓
                         手机内存播放后释放
```

完整历史保存在用户设备。日常聊天只把选中的近期对话、相关旧对话和手动记忆发送给模型服务。

## 当前技术基线

模板包含已经过测试的核心技术路线，不包含具体 UI：

- 本地历史按完整对话轮建立可重建索引，不调用额外模型；
- 只有检测到回忆意图时才检索旧对话，普通闲聊跳过检索；
- 近期上下文保留 4～12 个完整轮次，使用约 1600 Token 的软预算；
- 旧对话最多选 2 段，使用约 500 Token 的硬预算，并抑制高频和近似重复内容；
- 固定前缀生成 SHA-256 指纹，只用于判断前缀是否变化，不冒充服务端缓存；
- 读取供应商实际返回的 `cached_tokens`，计算最近 20 次的 token 加权命中率；供应商未返回时显示未知，不自行估算；
- Android 成品使用 `WebViewAssetLoader` 加载 APK 内置页面，由原生层完成 Keystore、HTTPS、录音和内存音频播放。

本模板保留额外的安全加固：检索旧聊天始终维持原始
`user` / `assistant` 权限，不把正文提升为 `system`；Character 请求按会话串行，
并对 Character 和 TTS 使用会话级幂等键。

## 与电脑常驻方案的区别

- 最终目标是 Android App 独立运行，电脑关机后仍可聊天。
- 人设原文保持完整，不让模型自动重写。
- 正式记忆只有“共同经历、关系、角色设定”，并由用户确认。
- 旧历史使用本地关键词索引检索，不额外请求模型。
- Character 或 TTS 失败时明确报错，不偷偷切换其他模型或声音。

## 快速开始：电脑技术验证

电脑服务只是方便开发和检查请求结构，不是最终手机运行条件。

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env

# 生成 APP_ACCESS_TOKEN，把输出粘贴到 .env
python -c "import secrets; print(secrets.token_urlsafe(32))"

python -m uvicorn app.server:app --host 127.0.0.1 --port 8434
```

然后打开 `http://127.0.0.1:8434`。

在 `.env` 中填写自己的火山 API Key 和至少 24 位的随机
`APP_ACCESS_TOKEN`。浏览器第一次打开时会要求输入这个访问令牌。
不要把 `.env`、真实人设、聊天记录、声音或 Android 签名文件提交到
GitHub。

## 角色资料

1. 把原始人设逐字放入 `private/role-setting.txt`。
2. 把聊天历史放入 `private/history.json`。
3. 把人工确认的三项记忆放入 `private/memories.json`。

公开仓库只包含 `examples/` 中的虚构样例。

## 核心代码入口

- `app/context.py`：稳定人设、手动记忆、时间、近期对话和检索历史的组装。
- `app/memory.py`：本地召回门控、关键词索引、预算和去重。
- `app/providers.py`：Character 和 TTS 的最小请求代码。
- `app/usage.py`：解析供应商真实 token/隐式缓存统计，不做虚构估算。
- `app/storage.py`：按会话保存消息和 Character 请求幂等状态的 SQLite 层。
- `app/server.py`：带访问令牌、会话隔离和付费请求防重的电脑端验证服务。
- `skill/return-home-character/`：可选的 Codex 安装与迁移引导 Skill。
- `docs/ARCHITECTURE.md`：手机正式实现与安全边界。

## 隐私边界

“本地保存”不等于“请求时完全不出设备”：

- 原始全量历史、数据库和正式记忆文件默认保存在本地。
- 使用云端 Character 时，本轮选中的人设、记忆和上下文会发送给火山方舟。
- 使用云端 TTS 时，待朗读文字会发送给语音服务。
- 用户应自行阅读并遵守模型服务的隐私政策、计费规则和内容规范。

电脑验证服务会把新聊天按 `session_id` 保存到
`private/conversations.sqlite3`。接口必须携带 `X-App-Token`，即使误绑定到
局域网地址，也不能在没有访问令牌的情况下调用 Character、TTS 或读取会话。

## 手机正式实现

示例服务使用环境变量保存开发密钥。正式 Android App 应改为：

- Android Keystore 保存密钥；
- IndexedDB 或加密 SQLite 保存聊天和记忆；
- 原生 HTTPS 客户端直接请求火山；
- 原生音频播放器播放内存中的 MP3；
- 播放结束后释放音频数据；
- 不依赖 Python、电脑 IP 或 `127.0.0.1`。

详见 `docs/ARCHITECTURE.md`。

## 不包含的内容

- 真实角色、人设、聊天记录、头像和声音；
- API Key、模型额度或声音授权；
- 实时端到端语音通话；
- 未经用户确认的自动记忆写入。

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
