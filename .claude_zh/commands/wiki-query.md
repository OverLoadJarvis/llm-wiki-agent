查询 LLM Wiki 并综合答案。

用法：/wiki-query $ARGUMENTS

$ARGUMENTS 是要回答的问题，例如 `What are the main themes across all sources?`

按照 CLAUDE.md 中定义的查询工作流执行：
1. 读取 wiki/index.md 识别最相关的页面
2. 读取这些页面（最多约 10 个最相关的）
3. 使用 [[PageName]] wiki 链接引用综合详细的 markdown 答案
4. 在末尾包含 ## Sources 部分，列出您引用的页面
5. 询问用户是否要将答案保存为 wiki/syntheses/<slug>.md

如果 wiki 为空，说明这一点并建议先运行 /wiki-ingest。