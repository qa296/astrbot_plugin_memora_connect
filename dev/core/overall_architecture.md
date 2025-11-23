---
outline: deep
---

# Astrbot 整体架构

![](../../source/images/dev/overall_structure.png)

# 目录大致结构

- `astrbot`：核心代码
  - `api`: 为开发插件设计的模块和工具, 方便插件进行导入和使用
  - `core`: 核心代码
  - `dashboard`: WebUI 后端代码
- `changelogs`: 更新日志
- `dashboard`: WebUI 前端代码
- `packages`: 保留插件
- `tests`: 测试代码
- `main.py`: 主程序入口
