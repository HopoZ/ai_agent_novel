将 PyInstaller 生成的 novel-backend.exe 放在此目录后，再执行 npm run dist，
安装包会把该文件复制到 resources/backend/，桌面应用将优先启动内置后端。

构建说明见仓库 packaging/pyinstaller/README.md。

若此目录为空，安装版将尝试使用本机 Python（需设置 NOVEL_AGENT_PROJECT_ROOT 指向完整源码树）。
